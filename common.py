import jinja2
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import List

FT_BASE_IMG = "quay.io/wizhao/ft-base-image:0.9"
TFT_TOOLS_IMG = "quay.io/wizhao/tft-tools:latest"
TFT_TESTS = "tft-tests"

class TestType(Enum):
    IPERF_TCP  = 1
    IPERF_UDP  = 2
    HTTP       = 3

class PodType(Enum):
    NORMAL     = 1
    SRIOV      = 2
    HOSTBACKED = 3

class TestCaseType(Enum):
    POD_TO_POD_SAME_NODE                 = 1
    POD_TO_POD_DIFF_NODE                 = 2
    POD_TO_HOST_SAME_NODE                = 3
    POD_TO_HOST_DIFF_NODE                = 4
    POD_TO_CLUSTER_IP_TO_POD_SAME_NODE   = 5
    POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE   = 6
    POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE  = 7
    POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE  = 8
    POD_TO_NODE_PORT_TO_POD_SAME_NODE    = 9
    POD_TO_NODE_PORT_TO_POD_DIFF_NODE    = 10
    POD_TO_NODE_PORT_TO_HOST_SAME_NODE   = 11
    POD_TO_NODE_PORT_TO_HOST_DIFF_NODE   = 12
    HOST_TO_HOST_SAME_NODE               = 13
    HOST_TO_HOST_DIFF_NODE               = 14
    HOST_TO_POD_SAME_NODE                = 15
    HOST_TO_POD_DIFF_NODE                = 16
    HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE  = 17
    HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE  = 18
    HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE = 19
    HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE = 20
    HOST_TO_NODE_PORT_TO_POD_SAME_NODE   = 21
    HOST_TO_NODE_PORT_TO_POD_DIFF_NODE   = 22
    HOST_TO_NODE_PORT_TO_HOST_SAME_NODE  = 23
    HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE  = 24
    POD_TO_EXTERNAL                      = 25
    HOST_TO_EXTERNAL                     = 26

class ConnectionMode(Enum):
    POD_IP                               = 1
    CLUSTER_IP                           = 2
    NODE_PORT_IP                         = 3
    EXTERNAL_IP                          = 4

class NodeLocation(Enum):
    SAME_NODE                            = 1
    DIFF_NODE                            = 2


@dataclass
class PodInfo():
    name: str
    pod_type: str
    is_tenant: bool
    index: int

@dataclass
class TestMetadata():
    test_case_id: str
    test_type: str
    reverse: bool
    server: PodInfo
    client: PodInfo

@dataclass
class IperfOutput():
    tft_metadata: TestMetadata
    command: str
    result: dict

@dataclass
class PluginOutput():
    plugin_metadata: dict
    command: str
    result: dict
    name: str

@dataclass
class RxTxData():
    rx_start: int
    tx_start: int
    rx_end: int
    tx_end: int

@dataclass
class TftAggregateOutput():
    '''Aggregated output of a single tft run. A single run of a trafficFlowTests._run_tests() will
    pass a reference to an instance of TftAggregateOutput to each task to which the task will append
    it's respective output. A list of this class will be the expected format of input provided to
    evaluator.py.

    Attributes:
        flow_test: an object of type IperfOutput containing the results of a flow test run
        plugins: a list of objects derivated from type PluginOutput for each optional plugin to append
        resulting output to.'''
    flow_test: IperfOutput = None
    plugins: List[PluginOutput] = field(default_factory=list)


def j2_render(in_file_name, out_file_name, kwargs):
    with open(in_file_name) as inFile:
        contents = inFile.read()
    template = jinja2.Template(contents)
    rendered = template.render(**kwargs)
    with open(out_file_name, "w") as outFile:
        outFile.write(rendered)
