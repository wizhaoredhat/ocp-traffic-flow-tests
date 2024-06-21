import os
import pytest
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import common  # noqa: E402
import tftbase  # noqa: E402

from tftbase import ConnectionMode  # noqa: E402
from tftbase import IperfOutput  # noqa: E402
from tftbase import PodInfo  # noqa: E402
from tftbase import PodType  # noqa: E402
from tftbase import TestCaseType  # noqa: E402
from tftbase import TestMetadata  # noqa: E402
from tftbase import TestType  # noqa: E402


def test_pod_info() -> None:
    pod = PodInfo(name="test_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0)
    assert pod.name == "test_pod"
    assert pod.pod_type == PodType.NORMAL
    assert pod.is_tenant is True
    assert pod.index == 0


def test_test_metadata() -> None:
    server = PodInfo(
        name="server_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0
    )
    client = PodInfo(
        name="client_pod", pod_type=PodType.NORMAL, is_tenant=False, index=1
    )
    metadata = TestMetadata(
        reverse=False,
        test_case_id=TestCaseType.POD_TO_POD_SAME_NODE,
        test_type=TestType.IPERF_TCP,
        server=server,
        client=client,
    )
    assert metadata.reverse is False
    assert metadata.test_case_id == TestCaseType.POD_TO_POD_SAME_NODE
    assert metadata.test_type == TestType.IPERF_TCP
    assert metadata.server == server
    assert metadata.client == client


def test_iperf_output() -> None:
    server = PodInfo(
        name="server_pod", pod_type=PodType.NORMAL, is_tenant=True, index=0
    )
    client = PodInfo(
        name="client_pod", pod_type=PodType.NORMAL, is_tenant=False, index=1
    )
    metadata = TestMetadata(
        reverse=False,
        test_case_id=TestCaseType.POD_TO_POD_SAME_NODE,
        test_type=TestType.IPERF_TCP,
        server=server,
        client=client,
    )
    IperfOutput(
        command="command",
        result={},
        tft_metadata=metadata,
        bitrate_gbps=tftbase.Bitrate.NA,
    )

    common.dataclass_from_dict(
        IperfOutput,
        {
            "command": "command",
            "result": {},
            "tft_metadata": metadata,
            "bitrate_gbps": {"tx": 0.0, "rx": 0.0},
        },
    )

    o = common.dataclass_from_dict(
        IperfOutput,
        {
            "command": "command",
            "result": {},
            "tft_metadata": metadata,
            "bitrate_gbps": {"tx": None, "rx": 0},
        },
    )
    assert o.bitrate_gbps.tx is None
    assert o.bitrate_gbps.rx == 0.0

    with pytest.raises(ValueError):
        common.dataclass_from_dict(
            IperfOutput,
            {
                "command": "command",
                "result": {},
                "tft_metadata": metadata,
            },
        )
    with pytest.raises(TypeError):
        common.dataclass_from_dict(
            IperfOutput,
            {
                "command": "command",
                "result": {},
                "tft_metadata": "string",
                "bitrate_gbps": {"tx": 0.0, "rx": 0.0},
            },
        )


def test_test_case_typ_infos() -> None:
    assert list(tftbase._test_case_typ_infos) == list(TestCaseType)


def test_test_case_type_to_connection_mode() -> None:
    def _alternative(test_case_id: TestCaseType) -> ConnectionMode:
        if test_case_id.value in (5, 6, 7, 8, 17, 18, 19, 20):
            return ConnectionMode.CLUSTER_IP
        if test_case_id.value in (9, 10, 11, 12, 21, 22, 23, 24):
            return ConnectionMode.NODE_PORT_IP
        if test_case_id.value in (25, 26):
            return ConnectionMode.EXTERNAL_IP
        return ConnectionMode.POD_IP

    for test_case_type in TestCaseType:
        assert _alternative(
            test_case_type
        ) == tftbase.test_case_type_to_connection_mode(test_case_type)


def test_test_case_type_is_same_node() -> None:
    def _alternative(test_id: TestCaseType) -> bool:
        return test_id.value in (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23)

    for test_case_type in TestCaseType:
        assert _alternative(test_case_type) == tftbase.test_case_type_is_same_node(
            test_case_type
        )


def test_test_case_type_to_server_pod_type() -> None:
    def _alternative(
        test_id: TestCaseType,
        cfg_pod_type: PodType,
    ) -> PodType:
        if test_id.value in (3, 4, 7, 8, 19, 20, 23, 24):
            return PodType.HOSTBACKED

        if cfg_pod_type == PodType.SRIOV:
            return PodType.SRIOV

        return PodType.NORMAL

    for pod_type in PodType:
        for test_case_type in TestCaseType:
            assert _alternative(
                test_case_type, pod_type
            ) == tftbase.test_case_type_to_server_pod_type(test_case_type, pod_type)


def test_test_case_type_to_client_pod_type() -> None:
    def _alternative(
        test_id: TestCaseType,
        cfg_pod_type: PodType,
    ) -> PodType:
        if (
            test_id.value >= TestCaseType.HOST_TO_HOST_SAME_NODE.value
            and test_id.value <= TestCaseType.HOST_TO_EXTERNAL.value
        ):
            return PodType.HOSTBACKED

        if cfg_pod_type == PodType.SRIOV:
            return PodType.SRIOV

        return PodType.NORMAL

    for pod_type in PodType:
        for test_case_type in TestCaseType:
            assert _alternative(
                test_case_type, pod_type
            ) == tftbase.test_case_type_to_client_pod_type(test_case_type, pod_type)
