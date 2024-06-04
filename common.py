import jinja2

from dataclasses import fields
from dataclasses import is_dataclass
from enum import Enum
from typing import Any
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import cast


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
