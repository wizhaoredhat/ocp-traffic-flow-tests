import jinja2
from dataclasses import dataclass, fields, field, is_dataclass
from enum import Enum
from typing import Optional, Any, Type, TypeVar, cast
from typing import Mapping

TFT_TOOLS_IMG = "quay.io/wizhao/tft-tools:latest"
TFT_TESTS = "tft-tests"

MEASURE_POWER_PLUGIN = "measure_power"
MEASURE_CPU_PLUGIN = "measure_cpu"
VALIDATE_OFFLOAD_PLUGIN = "validate_offload"


@dataclass
class Result:
    out: str
    err: str
    returncode: int


E = TypeVar("E", bound=Enum)


def enum_convert(enum_type: Type[E], value: E | str | int) -> E:
    if isinstance(value, enum_type):
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

        # Finally, try again with all upper case.
        v2 = v.upper()
        for e in enum_type:
            if e.name.upper() == v2:
                return e

        raise ValueError(f"Cannot convert {value} to {enum_type}")

    raise ValueError(f"Invalid type for conversion to {enum_type}")


def enum_convert_list(enum_type: Type[E], input_str: str) -> list[E]:
    output: list[E] = []

    for part in input_str.split(","):
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

    return output


class TestType(Enum):
    IPERF_TCP = 1
    IPERF_UDP = 2
    HTTP = 3
    NETPERF_TCP_STREAM = 4
    NETPERF_TCP_RR = 5


class PodType(Enum):
    NORMAL = 1
    SRIOV = 2
    HOSTBACKED = 3


class TestCaseType(Enum):
    POD_TO_POD_SAME_NODE = 1
    POD_TO_POD_DIFF_NODE = 2
    POD_TO_HOST_SAME_NODE = 3
    POD_TO_HOST_DIFF_NODE = 4
    POD_TO_CLUSTER_IP_TO_POD_SAME_NODE = 5
    POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE = 6
    POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE = 7
    POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE = 8
    POD_TO_NODE_PORT_TO_POD_SAME_NODE = 9
    POD_TO_NODE_PORT_TO_POD_DIFF_NODE = 10
    POD_TO_NODE_PORT_TO_HOST_SAME_NODE = 11
    POD_TO_NODE_PORT_TO_HOST_DIFF_NODE = 12
    HOST_TO_HOST_SAME_NODE = 13
    HOST_TO_HOST_DIFF_NODE = 14
    HOST_TO_POD_SAME_NODE = 15
    HOST_TO_POD_DIFF_NODE = 16
    HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE = 17
    HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE = 18
    HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE = 19
    HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE = 20
    HOST_TO_NODE_PORT_TO_POD_SAME_NODE = 21
    HOST_TO_NODE_PORT_TO_POD_DIFF_NODE = 22
    HOST_TO_NODE_PORT_TO_HOST_SAME_NODE = 23
    HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE = 24
    POD_TO_EXTERNAL = 25
    HOST_TO_EXTERNAL = 26


class ConnectionMode(Enum):
    POD_IP = 1
    CLUSTER_IP = 2
    NODE_PORT_IP = 3
    EXTERNAL_IP = 4


class NodeLocation(Enum):
    SAME_NODE = 1
    DIFF_NODE = 2


@dataclass
class PodInfo:
    name: str
    pod_type: PodType
    is_tenant: bool
    index: int


@dataclass
class TestMetadata:
    reverse: bool
    test_case_id: TestCaseType
    test_type: TestType
    server: PodInfo
    client: PodInfo

    def __init__(
        self,
        reverse: bool,
        test_case_id: TestCaseType | str | int,
        test_type: TestType | str | int,
        server: PodInfo | dict[str, Any],
        client: PodInfo | dict[str, Any],
    ):
        if isinstance(server, dict):
            server = dataclass_from_dict(PodInfo, server)
        if isinstance(client, dict):
            client = dataclass_from_dict(PodInfo, client)
        self.reverse = reverse
        self.test_case_id = enum_convert(TestCaseType, test_case_id)
        self.test_type = enum_convert(TestType, test_type)
        self.server = server
        self.client = client


@dataclass
class BaseOutput:
    command: str
    result: dict[str, str | int]

    def __init__(self, command: str, result: Mapping[str, str | int]):
        if not isinstance(result, dict):
            result = dict(result)
        self.command = command
        self.result = result


@dataclass
class IperfOutput(BaseOutput):
    tft_metadata: TestMetadata

    def __init__(
        self,
        command: str,
        result: Mapping[str, str | int],
        tft_metadata: TestMetadata | dict[str, Any],
    ):
        if isinstance(tft_metadata, dict):
            tft_metadata = dataclass_from_dict(TestMetadata, tft_metadata)
        elif not isinstance(tft_metadata, TestMetadata):
            raise ValueError("tft_metadata must be a TestMetadata instance or a dict")
        super().__init__(command, result)
        self.tft_metadata = tft_metadata


@dataclass
class PluginOutput(BaseOutput):
    plugin_metadata: dict[str, str]
    name: str


@dataclass
class TftAggregateOutput:
    """Aggregated output of a single tft run. A single run of a trafficFlowTests._run_tests() will
    pass a reference to an instance of TftAggregateOutput to each task to which the task will append
    it's respective output. A list of this class will be the expected format of input provided to
    evaluator.py.

    Attributes:
        flow_test: an object of type IperfOutput containing the results of a flow test run
        plugins: a list of objects derivated from type PluginOutput for each optional plugin to append
        resulting output to."""

    flow_test: Optional[IperfOutput] = None
    plugins: list[PluginOutput] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.flow_test, dict):
            self.flow_test = dataclass_from_dict(IperfOutput, self.flow_test)
        elif self.flow_test is not None and not isinstance(self.flow_test, IperfOutput):
            raise ValueError("flow_test must be an IperfOutput instance or a dict")

        self.plugins = [
            (
                dataclass_from_dict(PluginOutput, plugin)
                if isinstance(plugin, dict)
                else plugin
            )
            for plugin in self.plugins
        ]


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
