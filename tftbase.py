import dataclasses
import functools
import json
import math
import os
import shlex
import typing

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Optional

import host
import common

from common import strict_dataclass
from logger import logger


ENV_TFT_TEST_IMAGE = "TFT_TEST_IMAGE"
ENV_TFT_IMAGE_PULL_POLICY = "TFT_IMAGE_PULL_POLICY"

ENV_TFT_TEST_IMAGE_DEFAULT = "quay.io/wizhao/tft-tools:latest"


def get_environ(name: str) -> Optional[str]:
    # Some environment variables are honored as configuration.
    # Which ones? Run `git grep -w get_environ`!
    return os.environ.get(name, None)


@functools.cache
def get_tft_test_image() -> str:
    s = get_environ(ENV_TFT_TEST_IMAGE) or ENV_TFT_TEST_IMAGE_DEFAULT
    logger.info(f"env: {ENV_TFT_TEST_IMAGE}={shlex.quote(s)}")
    return s


@functools.cache
def get_tft_image_pull_policy() -> str:
    s: Optional[str] = None
    s_env = get_environ(ENV_TFT_IMAGE_PULL_POLICY)
    if s_env is not None:
        s0 = s_env.strip().lower()
        if s0 == "always":
            s = "Always"
        if s0 == "ifnotpresent":
            s = "IfNotPresent"
        if s0 == "never":
            s = "Never"
        logger.error(
            f'env: invalid environment variable in {ENV_TFT_IMAGE_PULL_POLICY}="{shlex.quote(s_env)}". Set to one of "IfNotPresent", "Always", "Never"'
        )
    if s is None:
        if get_environ(ENV_TFT_TEST_IMAGE):
            s = "Always"
        else:
            s = "IfNotPresent"
    logger.info(f"env: {ENV_TFT_IMAGE_PULL_POLICY}={shlex.quote(s)}")
    return s


TFT_TESTS = "tft-tests"


class ClusterMode(Enum):
    SINGLE = 1
    DPU = 3


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


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class Bitrate:
    tx: Optional[float]
    rx: Optional[float]

    NA: typing.ClassVar["Bitrate"]

    def __init__(
        self,
        *,
        tx: None | int | float = None,
        rx: None | int | float = None,
    ) -> None:
        if isinstance(tx, int):
            tx = float(tx)
        if isinstance(rx, int):
            rx = float(rx)
        object.__setattr__(self, "tx", tx)
        object.__setattr__(self, "rx", rx)

    def _valid_x(self, f: Optional[float]) -> bool:
        return f is None or (f >= 0.0 and not math.isinf(f) and not math.isnan(f))

    def _post_init(self) -> None:
        if not self._valid_x(self.tx):
            raise ValueError("tx is not a valid bitrange")
        if not self._valid_x(self.rx):
            raise ValueError("rx is not a valid bitrange")

    def is_passing(
        self,
        threshold: Optional[float],
        *,
        tx: bool = False,
        rx: bool = False,
    ) -> bool:
        if threshold is None:
            return True
        if tx or not rx:
            if self.tx is not None and self.tx < threshold:
                return False
        if rx or not tx:
            if self.rx is not None and self.rx < threshold:
                return False
        return True


Bitrate.NA = Bitrate()


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class PodInfo:
    name: str
    pod_type: PodType
    is_tenant: bool
    index: int


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class PluginResult:
    """Result of a single plugin from a given run

    Attributes:
        test_id: TestCaseType enum representing the type of traffic test (i.e. POD_TO_POD_SAME_NODE <1> )
        test_type: TestType enum representing the traffic protocol (i.e. iperf_tcp)
        reverse: Specify whether test is client->server or reversed server->client
        success: boolean representing whether the test passed or failed
    """

    test_id: TestCaseType
    test_type: TestType
    reverse: bool
    success: bool


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class TestMetadata:
    reverse: bool
    test_case_id: TestCaseType
    test_type: TestType
    server: PodInfo
    client: PodInfo


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class BaseOutput:
    success: bool = True
    msg: Optional[str] = None

    @property
    def err_msg(self) -> Optional[str]:
        if self.success:
            return None
        if self.msg is not None:
            return self.msg
        return "unspecified failure"

    @staticmethod
    def from_cmd(
        result: host.Result, *, success: Optional[bool] = None
    ) -> "BaseOutput":
        if success is None:
            success = result.success
        return BaseOutput(
            success=success,
            msg=result.debug_msg(),
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class AggregatableOutput(BaseOutput):
    pass


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class IperfOutput(AggregatableOutput):
    command: str
    result: dict[str, Any]
    tft_metadata: TestMetadata


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class PluginOutput(AggregatableOutput):
    command: str
    result: dict[str, Any]
    plugin_metadata: dict[str, str]
    name: str

    @property
    def plugin(self) -> "Plugin":
        import pluginbase

        return pluginbase.get_by_name(self.name)


@strict_dataclass
@dataclass(kw_only=True)
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
    plugins: list[PluginOutput] = dataclasses.field(default_factory=list)


class TestCaseTypInfo(typing.NamedTuple):
    connection_mode: ConnectionMode
    is_same_node: bool
    is_server_hostbacked: bool
    is_client_hostbacked: bool


_test_case_typ_infos = {
    TestCaseType.POD_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=True,
        is_server_hostbacked=True,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=False,
        is_server_hostbacked=True,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_CLUSTER_IP_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=True,
        is_server_hostbacked=True,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=False,
        is_server_hostbacked=True,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_NODE_PORT_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_NODE_PORT_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_NODE_PORT_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.POD_TO_NODE_PORT_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=False,
    ),
    TestCaseType.HOST_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.POD_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=True,
        is_server_hostbacked=True,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.CLUSTER_IP,
        is_same_node=False,
        is_server_hostbacked=True,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_NODE_PORT_TO_POD_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=True,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_NODE_PORT_TO_POD_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_NODE_PORT_TO_HOST_SAME_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=True,
        is_server_hostbacked=True,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE: TestCaseTypInfo(
        connection_mode=ConnectionMode.NODE_PORT_IP,
        is_same_node=False,
        is_server_hostbacked=True,
        is_client_hostbacked=True,
    ),
    TestCaseType.POD_TO_EXTERNAL: TestCaseTypInfo(
        connection_mode=ConnectionMode.EXTERNAL_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
    TestCaseType.HOST_TO_EXTERNAL: TestCaseTypInfo(
        connection_mode=ConnectionMode.EXTERNAL_IP,
        is_same_node=False,
        is_server_hostbacked=False,
        is_client_hostbacked=True,
    ),
}


def test_case_type_to_connection_mode(test_case_type: TestCaseType) -> ConnectionMode:
    return _test_case_typ_infos[test_case_type].connection_mode


def test_case_type_is_same_node(test_case_type: TestCaseType) -> bool:
    return _test_case_typ_infos[test_case_type].is_same_node


def test_case_type_get_node_location(test_case_type: TestCaseType) -> NodeLocation:
    if test_case_type_is_same_node(test_case_type):
        return NodeLocation.SAME_NODE
    return NodeLocation.DIFF_NODE


def test_case_type_to_server_pod_type(
    test_case_type: TestCaseType,
    pod_type: PodType,
) -> PodType:
    if _test_case_typ_infos[test_case_type].is_server_hostbacked:
        return PodType.HOSTBACKED

    if pod_type == PodType.SRIOV:
        return PodType.SRIOV

    return PodType.NORMAL


def test_case_type_to_client_pod_type(
    test_case_type: TestCaseType,
    pod_type: PodType,
) -> PodType:
    if _test_case_typ_infos[test_case_type].is_client_hostbacked:
        return PodType.HOSTBACKED

    if pod_type == PodType.SRIOV:
        return PodType.SRIOV

    return PodType.NORMAL


def output_list_serialize(
    tft_output: Iterable[TftAggregateOutput],
) -> dict[str, Any]:
    return {
        TFT_TESTS: [common.dataclass_to_dict(o) for o in tft_output],
    }


def output_list_parse_file(filename: str | Path) -> list[TftAggregateOutput]:
    try:
        f = open(filename, "r")
    except Exception as e:
        raise RuntimeError(f"cannot load file {filename}: {e}")
    try:
        data = json.load(f)
    except Exception:
        raise RuntimeError(f"File {filename} does not contain valid JSON")
    finally:
        f.close()

    return output_list_parse(data, filename=filename)


def output_list_parse(
    data: Any,
    *,
    filename: Optional[str | Path] = None,
) -> list[TftAggregateOutput]:

    err = "data"
    if filename is not None:
        err = f'file "{filename}'

    if not isinstance(data, dict):
        raise RuntimeError(f"{err} needs to contain a dictionary")

    if TFT_TESTS not in data:
        raise RuntimeError(f'{err} needs a top level key "{TFT_TESTS}"')

    k = list(data)
    k.remove(TFT_TESTS)
    if k:
        raise RuntimeError(f'{err} has unknown top level key "{k}"')

    data_tft_tests = data[TFT_TESTS]

    if not isinstance(data_tft_tests, list):
        raise RuntimeError(
            f'{err} needs a list at top level key "{k}" but has {type(data)}'
        )

    output_list: list[TftAggregateOutput] = []
    for data_tft_test in data_tft_tests:
        try:
            result = common.dataclass_from_dict(TftAggregateOutput, data_tft_test)
        except Exception as e:
            raise RuntimeError(f"{err} has invalid data: {e}")
        output_list.append(result)

    for r_idx, result in enumerate(output_list):
        for plugin_output in result.plugins:
            try:
                plugin_output.plugin
            except ValueError:
                raise RuntimeError(
                    f'{err} has invalid plugin name "{plugin_output.name}" in result #{r_idx}'
                )

    return output_list


if typing.TYPE_CHECKING:
    from pluginbase import Plugin
