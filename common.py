import dataclasses
import jinja2
import typing
import collections

from dataclasses import fields
from dataclasses import is_dataclass
from enum import Enum
from typing import Any
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import cast


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


def bool_to_str(val: bool, *, format: str = "true") -> str:
    if format == "true":
        return "true" if val else "false"
    if format == "yes":
        return "yes" if val else "no"
    raise ValueError(f'Invalid format "{format}"')


T1 = TypeVar("T1")
T2 = TypeVar("T2")


def str_to_bool(
    val: None | str | bool,
    on_error: T1 | _MISSING_TYPE = MISSING,
    *,
    on_default: T2 | _MISSING_TYPE = MISSING,
) -> bool | T1 | T2:

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


E = TypeVar("E", bound=Enum)


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


def j2_render(in_file_name: str, out_file_name: str, kwargs: dict[str, Any]) -> None:
    with open(in_file_name) as inFile:
        contents = inFile.read()
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)


def serialize_enum(
    data: Enum | dict[Any, Any] | list[Any] | Any
) -> str | dict[Any, Any] | list[Any] | Any:
    if isinstance(data, Enum):
        return data.name
    elif isinstance(data, dict):
        return {k: serialize_enum(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_enum(item) for item in data]
    else:
        return data


T = TypeVar("T")


# Takes a dataclass and the dict you want to convert from
# If your dataclass has a dataclass member, it handles that recursively
def dataclass_from_dict(cls: Type[T], data: dict[str, Any]) -> T:
    assert is_dataclass(
        cls
    ), "dataclass_from_dict() should only be used with dataclasses."
    field_values = {}
    for f in fields(cls):
        field_name = f.name
        field_type = f.type
        if is_dataclass(field_type) and field_name in data:
            field_values[field_name] = dataclass_from_dict(field_type, data[field_name])
        elif field_name in data:
            field_values[field_name] = data[field_name]
    return cast(T, cls(**field_values))


def check_type(value: typing.Any, type_hint: type[typing.Any]) -> bool:

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
        return isinstance(value, type_hint)

    if actual_type is typing.Union:
        args = typing.get_args(type_hint)
        return any(check_type(value, a) for a in args)

    if actual_type is list:
        args = typing.get_args(type_hint)
        (arg,) = args
        return isinstance(value, list) and all(check_type(v, arg) for v in value)

    if actual_type is dict or actual_type is collections.abc.Mapping:
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


if typing.TYPE_CHECKING:
    # https://github.com/python/typeshed/tree/main/stdlib/_typeshed#api-stability
    # https://github.com/python/typeshed/blob/6220c20d9360b12e2287511587825217eec3e5b5/stdlib/_typeshed/__init__.pyi#L349
    from _typeshed import DataclassInstance


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


TCallable = typing.TypeVar("TCallable", bound=typing.Callable[..., typing.Any])


def strict_dataclass(cls: TCallable) -> TCallable:

    init = getattr(cls, "__init__")

    def wrapped_init(self: Any, *args: Any, **argv: Any) -> None:
        init(self, *args, **argv)
        dataclass_check(self)

    setattr(cls, "__init__", wrapped_init)
    return cls
