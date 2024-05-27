# Hack to import stuff from parent directory
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from common import *


def test_enum_convert() -> None:
    assert enum_convert(TestType, "IPERF_TCP") == TestType.IPERF_TCP
    assert enum_convert(PodType, 1) == PodType.NORMAL
    with pytest.raises(ValueError):
        enum_convert(TestType, "Not_in_enum")
    with pytest.raises(ValueError):
        enum_convert(TestType, 10000)


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

    # Test with dictionary input
    metadata_dict = TestMetadata(
        reverse=True,
        test_case_id="POD_TO_POD_DIFF_NODE",
        test_type="IPERF_UDP",
        server=server.__dict__,
        client=client.__dict__,
    )
    assert metadata_dict.reverse is True
    assert metadata_dict.test_case_id == TestCaseType.POD_TO_POD_DIFF_NODE
    assert metadata_dict.test_type == TestType.IPERF_UDP
    assert isinstance(metadata_dict.server, PodInfo)
    assert isinstance(metadata_dict.client, PodInfo)


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
    IperfOutput(command="command", result=dict(), tft_metadata=metadata)

    with pytest.raises(ValueError):
        IperfOutput(command="command", result=dict(), tft_metadata="string")


def test_serialize_enum() -> None:
    # Test with enum value
    assert serialize_enum(TestType.IPERF_TCP) == "IPERF_TCP"

    # Test with a dictionary containing enum values
    data = {
        "test_type": TestType.IPERF_UDP,
        "pod_type": PodType.SRIOV,
        "other_key": "some_value",
    }
    serialized_data = serialize_enum(data)
    assert serialized_data == {
        "test_type": "IPERF_UDP",
        "pod_type": "SRIOV",
        "other_key": "some_value",
    }

    # Test with a list containing enum values
    data_list = [TestType.HTTP, PodType.HOSTBACKED]
    serialized_list = serialize_enum(data_list)
    assert serialized_list == ["HTTP", "HOSTBACKED"]

    # Test with nested structures
    nested_data = {
        "nested_dict": {"test_case_id": TestCaseType.POD_TO_HOST_SAME_NODE},
        "nested_list": [ConnectionMode.EXTERNAL_IP, NodeLocation.SAME_NODE],
    }
    serialized_nested_data = serialize_enum(nested_data)
    assert serialized_nested_data == {
        "nested_dict": {"test_case_id": "POD_TO_HOST_SAME_NODE"},
        "nested_list": ["EXTERNAL_IP", "SAME_NODE"],
    }

    # Test with non-enum value
    assert serialize_enum("some_string") == "some_string"
    assert serialize_enum(123) == 123
