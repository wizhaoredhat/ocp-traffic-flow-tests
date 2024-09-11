import abc
import dataclasses
import functools
import json
import os
import re
import time
import typing

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import is_dataclass
from enum import Enum
from typing import Any
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union
from typing import cast

if typing.TYPE_CHECKING:
    # https://github.com/python/typeshed/tree/main/stdlib/_typeshed#api-stability
    # https://github.com/python/typeshed/blob/6220c20d9360b12e2287511587825217eec3e5b5/stdlib/_typeshed/__init__.pyi#L349
    from _typeshed import DataclassInstance
    from types import TracebackType


PathType = Union[str, bytes, os.PathLike[str], os.PathLike[bytes]]

E = TypeVar("E", bound=Enum)
T = TypeVar("T")
T1 = TypeVar("T1")
T2 = TypeVar("T2")
TCallable = typing.TypeVar("TCallable", bound=typing.Callable[..., typing.Any])


# This is used as default value for some arguments, to recognize that the
# caller didn't specify the argument. This is useful, when we want to
# explicitly distinguish between having an argument unset or set to any value.
# The caller would never pass this value, but the implementation would check
# whether the argument is still left at the default.
#
# See also, dataclasses.MISSING and dataclasses._MISSING_TYPE
class _MISSING_TYPE:
    pass


MISSING = _MISSING_TYPE()

# kw_only is Python3.10+. This annotation is very useful, so make it available
# with 3.9 without breaking mypy.
#
# This silences up mypy while retaining the error checking at runtime. It however
# looses the ability for mypy to detect the error at lint time.
#
# So, using this acts as a comment to the reader that the code expects kw_only.
# It is also enforced at runtime. It also allows to find all the places where
# we would like to use kw_only=True but cannot due to Python 3.9 compatibility.
KW_ONLY_DATACLASS = {"kw_only": True} if "kw_only" in dataclass.__kwdefaults__ else {}


def bool_to_str(val: bool, *, format: str = "true") -> str:
    if format == "true":
        return "true" if val else "false"
    if format == "yes":
        return "yes" if val else "no"
    raise ValueError(f'Invalid format "{format}"')


def str_to_bool(
    val: Optional[Union[str, bool]],
    on_error: Union[T1, _MISSING_TYPE] = MISSING,
    *,
    on_default: Union[T2, _MISSING_TYPE] = MISSING,
) -> Union[bool, T1, T2]:

    is_default = False

    if isinstance(val, str):
        val2 = val.lower().strip()
        if val2 in ("1", "y", "yes", "true", "on"):
            return True
        if val2 in ("0", "n", "no", "false", "off"):
            return False
        if val2 in ("", "default", "-1"):
            is_default = True
    elif val is None:
        # None is (maybe) accepted as default value.
        is_default = True
    elif isinstance(val, bool):
        # For convenience, also accept that the value is already a boolean.
        return val

    if is_default and not isinstance(on_default, _MISSING_TYPE):
        # The value is explicitly set to one of the recognized default values
        # (None, "default", "-1" or "").
        #
        # By setting @on_default, the caller can use str_to_bool() to not only
        # parse boolean values, but ternary values.
        return on_default

    if not isinstance(on_error, _MISSING_TYPE):
        # On failure, we return the fallback value.
        return on_error

    raise ValueError(f"Value {val} is not a boolean")


def iter_get_first(
    lst: Iterable[T],
    *,
    unique: bool = False,
    force_unique: bool = False,
) -> Optional[T]:
    v0: Optional[T] = None
    for idx, v in enumerate(lst):
        if idx == 0:
            v0 = v
            continue
        if force_unique:
            raise RuntimeError("Iterable was expected to only contain one entry")
        if unique:
            # We have more than one entries. The caller requested to reject
            # that.
            return None
        return v0
    return v0


def iter_filter_none(lst: Iterable[Optional[T]]) -> Iterable[T]:
    for v in lst:
        if v is not None:
            yield v


def unwrap(val: Optional[T], *, or_else: Optional[T] = None) -> T:
    # Like Rust's unwrap. Get the value or die (with an exception).
    #
    # The error message here is not good, so this function
    # is more for asserting (and shutting up the type checker)
    # when we expect that the value is not set.
    if val is None:
        if or_else is not None:
            return or_else
        raise ValueError("Unexpected optional value unset")
    return val


def enum_convert(
    enum_type: Type[E],
    value: Any,
    default: Optional[E] = None,
) -> E:

    if value is None:
        # We only allow None, if the caller also specified a default value.
        if default is not None:
            return default
    elif isinstance(value, enum_type):
        return value
    elif isinstance(value, int):
        try:
            return enum_type(value)
        except ValueError:
            raise ValueError(f"Cannot convert {value} to {enum_type}")
    elif isinstance(value, str):
        v = value.strip()

        # Try lookup by name.
        try:
            return enum_type[v]
        except KeyError:
            pass

        # Try the string as integer value.
        try:
            return enum_type(int(v))
        except Exception:
            pass

        # Finally, try again with all upper case. Also, all "-" are replaced
        # with "_", but only if the result is unique.
        v2 = v.upper().replace("-", "_")
        matches = [e for e in enum_type if e.name.upper() == v2]
        if len(matches) == 1:
            return matches[0]

        raise ValueError(f"Cannot convert {value} to {enum_type}")

    raise ValueError(f"Invalid type for conversion to {enum_type}")


def enum_convert_list(enum_type: Type[E], value: Any) -> list[E]:
    output: list[E] = []

    if isinstance(value, str):
        for part in value.split(","):
            part = part.strip()
            if not part:
                # Empty words are silently skipped.
                continue

            cases: Optional[list[E]] = None

            # Try to parse as a single enum value.
            try:
                cases = [enum_convert(enum_type, part)]
            except Exception:
                cases = None

            if part == "*":
                # Shorthand for the entire range (sorted by numeric values)
                cases = sorted(enum_type, key=lambda e: e.value)

            if cases is None:
                # Could not be parsed as single entry. Try to parse as range.

                def _range_endpoint(s: str) -> int:
                    try:
                        return int(s)
                    except Exception:
                        pass
                    return cast(int, enum_convert(enum_type, s).value)

                try:
                    # Try to detect this as range. Both end points may either by
                    # an integer or an enum name.
                    #
                    # Note that since we use "-" to denote the range, we cannot have
                    # a range that involves negative enum values (otherwise, enum_convert()
                    # is fine to parse a single enum from a negative number in a string).
                    start, end = [_range_endpoint(s) for s in part.split("-")]
                except Exception:
                    # Couldn't parse as range.
                    pass
                else:
                    # We have a range.
                    cases = None
                    for i in range(start, end + 1):
                        try:
                            e = enum_convert(enum_type, i)
                        except Exception:
                            # When specifying a range, then missing enum values are
                            # silently ignored. Note that as a whole, the range may
                            # still not be empty.
                            continue
                        if cases is None:
                            cases = []
                        cases.append(e)

            if cases is None:
                raise ValueError(f"Invalid test case id: {part}")

            output.extend(cases)
    elif isinstance(value, list):
        for idx, part in enumerate(value):
            # First, try to parse the list entry with plain enum_convert.
            cases = None
            try:
                cases = [enum_convert(enum_type, part)]
            except Exception:
                # Now, try to parse as a list (but only if we have a string, no lists in lists).
                if isinstance(part, str):
                    try:
                        cases = enum_convert_list(enum_type, part)
                    except Exception:
                        pass
            if not cases:
                raise ValueError(
                    f'list at index {idx} contains invalid value "{part}" for enum {enum_type}'
                )
            output.extend(cases)
    else:
        raise ValueError(f"Invalid {enum_type} value of type {type(value)}")

    return output


def json_parse_list(jstr: str, *, strict_parsing: bool = False) -> list[Any]:
    try:
        lst = json.loads(jstr)
    except ValueError:
        if strict_parsing:
            raise
        return []

    if not isinstance(lst, list):
        if strict_parsing:
            raise ValueError("JSON data does not contain a list")
        return []

    return lst


def dict_add_optional(vdict: dict[T1, T2], key: T1, val: Optional[T2]) -> None:
    if val is not None:
        vdict[key] = val


@typing.overload
def dict_get_typed(
    d: Mapping[Any, Any],
    key: Any,
    vtype: type[T],
    *,
    allow_missing: typing.Literal[False] = False,
) -> T:
    pass


@typing.overload
def dict_get_typed(
    d: Mapping[Any, Any],
    key: Any,
    vtype: type[T],
    *,
    allow_missing: bool = False,
) -> Optional[T]:
    pass


def dict_get_typed(
    d: Mapping[Any, Any],
    key: Any,
    vtype: type[T],
    *,
    allow_missing: bool = False,
) -> Optional[T]:
    try:
        v = d[key]
    except KeyError:
        if allow_missing:
            return None
        raise KeyError(f'missing key "{key}"')
    if not isinstance(v, vtype):
        raise TypeError(f'key "{key}" expected type {vtype} but has value "{v}"')
    return v


def serialize_enum(
    data: Union[Enum, dict[Any, Any], list[Any], Any]
) -> Union[str, dict[Any, Any], list[Any], Any]:
    if isinstance(data, Enum):
        return data.name
    elif isinstance(data, dict):
        return {k: serialize_enum(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_enum(item) for item in data]
    else:
        return data


def dataclass_to_dict(obj: "DataclassInstance") -> dict[str, Any]:
    d = dataclasses.asdict(obj)
    return typing.cast(dict[str, Any], serialize_enum(d))


def dataclass_to_json(obj: "DataclassInstance") -> str:
    d = dataclass_to_dict(obj)
    return json.dumps(d)


# Takes a dataclass and the dict you want to convert from
# If your dataclass has a dataclass member, it handles that recursively
def dataclass_from_dict(cls: Type[T], data: dict[str, Any]) -> T:
    if not is_dataclass(cls):
        raise ValueError(
            f"dataclass_from_dict() should only be used with dataclasses but is called with {cls}"
        )
    if not isinstance(data, dict):
        raise ValueError(
            f"requires a dictionary to in initialize dataclass {cls} but got {type(data)}"
        )
    for k in data:
        if not isinstance(k, str):
            raise ValueError(
                f"requires a strdict to in initialize dataclass {cls} but has key {type(k)}"
            )
    data = dict(data)
    create_kwargs = {}
    for field in fields(cls):
        if field.name not in data:
            if (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            ):
                raise ValueError(
                    f'Missing mandatory argument "{field.name}" for dataclass {cls}'
                )
            continue

        if not field.init:
            continue

        def convert_simple(ck_type: Any, value: Any) -> Any:
            if is_dataclass(ck_type) and isinstance(value, dict):
                return dataclass_from_dict(ck_type, value)
            if actual_type is None and issubclass(ck_type, Enum):
                return enum_convert(ck_type, value)
            if ck_type is float and isinstance(value, int):
                return float(value)
            return value

        actual_type = typing.get_origin(field.type)

        value = data.pop(field.name)

        converted = False

        if actual_type is typing.Union:
            # This is an Optional[]. We already have a value, we check for the requested
            # type. check_type() already implements this, but we need to also check
            # it here, for the dataclass/enum handling below.
            args = typing.get_args(field.type)
            ck_type = None
            if len(args) == 2:
                NoneType = type(None)
                if args[0] is NoneType:
                    ck_type = args[1]
                elif args[1] is NoneType:
                    ck_type = args[0]
            if ck_type is not None:
                value_converted = convert_simple(ck_type, value)
                converted = True
        elif actual_type is list:
            args = typing.get_args(field.type)
            if isinstance(value, list) and len(args) == 1:
                value_converted = [convert_simple(args[0], v) for v in value]
                converted = True

        if not converted:
            value_converted = convert_simple(field.type, value)

        if not check_type(value_converted, field.type):
            raise TypeError(
                f"Expected type '{field.type}' for attribute '{field.name}' but received type '{type(value)}' ({value})"
            )

        create_kwargs[field.name] = value_converted

    if data:
        raise ValueError(
            f"There are left over keys {list(data)} to create dataclass {cls}"
        )

    return cast(T, cls(**create_kwargs))


def check_type(
    value: typing.Any,
    type_hint: Union[type[typing.Any], typing._SpecialForm],
) -> bool:

    # Some naive type checking. This is used for ensuring that data classes
    # contain the expected types (see @strict_dataclass).
    #
    # That is most interesting, when we initialize the data class with
    # data from an untrusted source (like elements from a JSON parser).

    actual_type = typing.get_origin(type_hint)
    if actual_type is None:
        if isinstance(type_hint, str):
            raise NotImplementedError(
                f'Type hint "{type_hint}" as string is not implemented by check_type()'
            )

        if type_hint is typing.Any:
            return True
        return isinstance(value, typing.cast(Any, type_hint))

    if actual_type is typing.Union:
        args = typing.get_args(type_hint)
        return any(check_type(value, a) for a in args)

    if actual_type is list:
        args = typing.get_args(type_hint)
        (arg,) = args
        return isinstance(value, list) and all(check_type(v, arg) for v in value)

    if actual_type is dict or actual_type is Mapping:
        args = typing.get_args(type_hint)
        (arg_key, arg_val) = args
        return isinstance(value, dict) and all(
            check_type(k, arg_key) and check_type(v, arg_val) for k, v in value.items()
        )

    if actual_type is tuple:
        # https://docs.python.org/3/library/typing.html#annotating-tuples
        if not isinstance(value, tuple):
            return False
        args = typing.get_args(type_hint)
        if len(args) == 1 and args[0] == ():
            # This is an empty tuple tuple[()].
            return len(value) == 0
        if len(args) == 2 and args[1] is ...:
            # This is a tuple[T, ...].
            return all(check_type(v, args[0]) for v in value)
        return len(value) == len(args) and all(
            check_type(v, args[idx]) for idx, v in enumerate(value)
        )

    raise NotImplementedError(
        f'Type hint "{type_hint}" with origin type "{actual_type}" is not implemented by check_type()'
    )


def dataclass_check(
    instance: "DataclassInstance",
    *,
    with_post_check: bool = True,
) -> None:

    for field in dataclasses.fields(instance):
        value = getattr(instance, field.name)
        if not check_type(value, field.type):
            raise TypeError(
                f"Expected type '{field.type}' for attribute '{field.name}' but received type '{type(value)}' ({value})"
            )

    if with_post_check:
        # Normally, data classes support __post_init__(), which is called by __init__()
        # already. Add a way for a @strict_dataclass to add additional validation *after*
        # the original check.
        _post_check = getattr(type(instance), "_post_check", None)
        if _post_check is not None:
            _post_check(instance)


def strict_dataclass(cls: TCallable) -> TCallable:

    init = getattr(cls, "__init__")

    def wrapped_init(self: Any, *args: Any, **argv: Any) -> None:
        init(self, *args, **argv)
        dataclass_check(self)

    setattr(cls, "__init__", wrapped_init)
    return cls


def structparse_check_strdict(arg: Any, yamlpath: str) -> dict[str, Any]:
    if not isinstance(arg, dict):
        raise ValueError(f'"{yamlpath}": expects a dictionary but got {type(arg)}')
    for k, v in arg.items():
        if not isinstance(k, str):
            raise ValueError(
                f'"{yamlpath}": expects all dictionary keys to be strings but got {type(k)}'
            )

    # We shallow-copy the dictionary, because the caller will remove entries
    # to find unknown entries (see _check_empty_dict()).
    return dict(arg)


def structparse_check_empty_dict(vdict: dict[str, Any], yamlpath: str) -> None:
    length = len(vdict)
    if length == 1:
        raise ValueError(f'"{yamlpath}": unknown key "{list(vdict)[0]}"')
    if length > 1:
        raise ValueError(f'"{yamlpath}": unknown keys {list(vdict)}')


def structparse_check_and_pop_name(
    vdict: dict[str, Any], yamlpath: str, *, required: bool = False
) -> Optional[str]:
    name = vdict.pop("name", None)
    if name is None:
        if required:
            raise ValueError(f'"{yamlpath}.name": mandatory key missing')
        return None
    if not isinstance(name, str):
        raise ValueError(f'"{yamlpath}.name": expects a string but got {name}')
    return name


def structparse_check_and_pop_name_required(
    vdict: dict[str, Any], yamlpath: str
) -> str:
    return typing.cast(
        str, structparse_check_and_pop_name(vdict, yamlpath, required=True)
    )


@strict_dataclass
@dataclass(frozen=True, **KW_ONLY_DATACLASS)
class StructParseBase(abc.ABC):
    yamlpath: str
    yamlidx: int

    @abc.abstractmethod
    def serialize(self) -> Union[dict[str, Any], list[Any]]:
        pass

    def serialize_json(self) -> str:
        return json.dumps(self.serialize())


@strict_dataclass
@dataclass(frozen=True, **KW_ONLY_DATACLASS)
class StructParseBaseNamed(StructParseBase, abc.ABC):
    name: str

    def serialize(self) -> dict[str, Any]:
        return {
            "name": self.name,
        }


def repeat_for_same_result(fcn: TCallable) -> TCallable:
    # This decorator wraps @fcn and will call it (up to 10 times) until the
    # same result was returned twice in a row. The purpose is when we fetch
    # several pieces of information form the system, that can change at any
    # time. We would like to get a stable, self-consistent result.
    @functools.wraps(fcn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = None
        for i in range(10):
            new_result = fcn(*args, **kwargs)
            if i != 0 and result == new_result:
                return new_result
            result = new_result
        return result

    return typing.cast(TCallable, wrapped)


def etc_hosts_update_data(
    content: str,
    new_entries: Mapping[str, tuple[str, Optional[Iterable[str]]]],
) -> str:

    lineregex = re.compile(r"^\s*[a-fA-F0-9:.]+\s+([-a-zA-Z0-9_.]+)(\s+.*)?$")

    def _unpack(
        v: tuple[str, Optional[Iterable[str]]]
    ) -> Union[typing.Literal[False], tuple[str, tuple[str, ...]]]:
        n, a = v
        if a is None:
            a = ()
        else:
            a = tuple(a)
        return n, a

    entries = {k: _unpack(v) for k, v in new_entries.items()}

    def _build_line(name: str, ipaddr: str, aliases: tuple[str, ...]) -> str:
        if aliases:
            s_aliases = f" {' '.join(aliases)}"
        else:
            s_aliases = ""
        return f"{ipaddr} {name}{s_aliases}"

    result = []
    for line in content.splitlines():
        m = lineregex.search(line)
        if m:
            name = m.group(1)
            entry = entries.get(name)
            if entry is None:
                pass
            elif entry is False:
                continue
            else:
                line = _build_line(name, *entry)
                entries[name] = False
        result.append(line)

    entries2 = [(k, v) for k, v in entries.items() if v is not False]
    if entries2:
        if result and result[-1] != "":
            result.append("")
        for name, entry in entries2:
            result.append(_build_line(name, *entry))

    if not result:
        return ""

    result.append("")
    return "\n".join(result)


def etc_hosts_update_file(
    new_entries: Mapping[str, tuple[str, Optional[Iterable[str]]]],
    filename: PathType = "/etc/hosts",
) -> str:
    try:
        with open(filename, "rb") as f:
            b_content = f.read()
    except Exception:
        b_content = b""

    new_content = etc_hosts_update_data(
        b_content.decode("utf-8", errors="surrogateescape"),
        new_entries,
    )

    with open(filename, "wb") as f:
        f.write(new_content.encode("utf-8", errors="surrogateescape"))

    return new_content


class Serial:
    def __init__(self, port: str, baudrate: int = 115200):
        import serial
        from .logger import logger

        self.port = port
        self._ser = serial.Serial(port, baudrate=baudrate, timeout=0)
        self._logger = logger
        self._buffer = ""

    @property
    def buffer(self) -> str:
        return self._buffer

    def close(self) -> None:
        self._ser.close()

    def send(self, msg: str, *, sleep: float = 1) -> None:
        self._logger.debug(f"serial[{self.port}]: send {repr(msg)}")
        self._ser.write(msg.encode("utf-8", errors="surrogateescape"))
        time.sleep(sleep)

    def read_all(self) -> str:
        maxsize = 1000000
        while True:
            buf: bytes = self._ser.read(maxsize)
            self._buffer += buf.decode("utf-8", errors="surrogateescape")
            if len(buf) < maxsize:
                return self._buffer

    def expect(
        self,
        pattern: Union[str, re.Pattern[str]],
        timeout: float = 30,
    ) -> str:
        import select

        end_timestamp = time.monotonic() + timeout
        first_run = True

        self._logger.debug(f"serial[{self.port}]: expect message {repr(pattern)}")

        if isinstance(pattern, str):
            # We use DOTALL like pexpect does.
            # If you need something else, compile the pattern yourself.
            #
            # See also https://pexpect.readthedocs.io/en/stable/overview.html#find-the-end-of-line-cr-lf-conventions
            pattern_re = re.compile(pattern, re.DOTALL)
        else:
            pattern_re = pattern

        while True:

            # First, read all data from the serial port that is currently available.
            while True:
                b: bytes = self._ser.read(100)
                if not b:
                    break
                s = b.decode("utf-8", errors="surrogateescape")
                self._logger.debug(
                    f"serial[{self.port}]: read buffer ({len(self._buffer)} + {len(s)} unicode characters): {repr(s)}"
                )
                self._buffer += s

            matches = re.finditer(pattern_re, self._buffer)
            for match in matches:
                end_idx = match.end()
                self._logger.debug(
                    f"serial[{self.port}]: found expected message {end_idx} unicode characters, {len(self._buffer) - end_idx} remaning"
                )
                self._buffer = self._buffer[end_idx:]
                return self._buffer

            if first_run:
                first_run = False
            else:
                remaining_time = end_timestamp - time.monotonic()
                if remaining_time <= 0:
                    self._logger.debug(
                        f"serial[{self.port}]: did not find expected message {repr(pattern)} (buffer content is {repr(self._buffer)})"
                    )
                    raise RuntimeError(
                        f"Did not receive expected message {repr(pattern)} within timeout (buffer content is {repr(self._buffer)})"
                    )
                _, _, _ = select.select([self._ser], [], [], remaining_time)

    def __enter__(self) -> "Serial":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional["TracebackType"],
    ) -> None:
        self._ser.close()
