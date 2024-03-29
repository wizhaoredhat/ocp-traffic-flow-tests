import jinja2
from dataclasses import dataclass, fields, field, is_dataclass
from enum import Enum
from typing import List, Optional, Any, Dict, List, Union, Type, TypeVar, Generic, cast

FT_BASE_IMG = "quay.io/wizhao/ft-base-image:0.9"
TFT_TOOLS_IMG = "quay.io/wizhao/tft-tools:latest"
TFT_TESTS = "tft-tests"


@dataclass
class Result:
    out: str
    err: str
    returncode: int

E = TypeVar("E", bound=Enum)


def enum_convert(enum_type: Type[E], value: Union[E, str, int]) -> E:
    if isinstance(value, enum_type):
        return value
    elif isinstance(value, str):
        try:
            return enum_type[value]
        except KeyError:
            raise ValueError(f"Cannot convert {value} to {enum_type}")
    elif isinstance(value, int):
        try:
            return enum_type(value)
        except ValueError:
            raise ValueError(f"Cannot convert {value} to {enum_type}")
    else:
        raise ValueError(f"Invalid type for conversion to {enum_type}")


class TestType(Enum):
    IPERF_TCP = 1
    IPERF_UDP = 2
    HTTP = 3


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
    test_case_id: TestCaseType = field(default_factory=enum_factory(TestCaseType))
    test_type: TestType = field(default_factory=enum_factory(TestType))
    server: PodInfo = field(default_factory=lambda: from_dict(PodInfo, {}))
    client: PodInfo = field(default_factory=lambda: from_dict(PodInfo, {}))

    def __post_init__(self) -> None:
        self.test_case_id = enum_convert(TestCaseType, self.test_case_id)
        self.test_type = enum_convert(TestType, self.test_type)
        if isinstance(self.server, dict):
            self.server = dataclass_from_dict(PodInfo, self.server)
        if isinstance(self.client, dict):
            self.client = dataclass_from_dict(PodInfo, self.client)


@dataclass
class BaseOutput:
    command: str
    result: dict

@dataclass
class IperfOutput(BaseOutput):
    tft_metadata: TestMetadata

    def __post_init__(self) -> None:
        if isinstance(self.tft_metadata, dict):
            self.tft_metadata = dataclass_from_dict(TestMetadata, self.tft_metadata)
        elif not isinstance(self.tft_metadata, TestMetadata):
            raise ValueError("tft_metadata must be a TestMetadata instance or a dict")


@dataclass
class PluginOutput(BaseOutput):
    plugin_metadata: dict
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

    flow_test: Optional[IperfOutput] = field(
        default_factory=lambda: from_dict(IperfOutput, {})
    )
    plugins: List[PluginOutput] = field(default_factory=list)

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


def j2_render(in_file_name: str, out_file_name: str, kwargs: Dict[str, Any]) -> None:
    with open(in_file_name) as inFile:
        contents = inFile.read()
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)


def serialize_enum(
    data: Union[Enum, Dict[Any, Any], List[Any], Any]
) -> Union[str, Dict[Any, Any], List[Any], Any]:
    if isinstance(data, Enum):
        return data.name
    elif isinstance(data, dict):
        return {k: serialize_enum(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_enum(item) for item in data]
    else:
        return data


T = TypeVar("T")


def dataclass_from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
    assert is_dataclass(
        cls
    ), "dataclass_from_dict() should only be used with dataclasses."
    field_values = {}
    for field in fields(cls):
        field_name = field.name
        field_type = field.type
        if is_dataclass(field_type) and field_name in data:
            field_values[field_name] = dataclass_from_dict(field_type, data[field_name])
        elif field_name in data:
            field_values[field_name] = data[field_name]
    return cls(**field_values)
