import sys
import os
import pytest
import typing

from enum import Enum

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import common  # noqa: E402
import tftbase  # noqa: E402

from common import enum_convert  # noqa: E402
from common import enum_convert_list  # noqa: E402
from common import serialize_enum  # noqa: E402
from tftbase import ConnectionMode  # noqa: E402
from tftbase import IperfOutput  # noqa: E402
from tftbase import NodeLocation  # noqa: E402
from tftbase import PodInfo  # noqa: E402
from tftbase import PodType  # noqa: E402
from tftbase import TestCaseType  # noqa: E402
from tftbase import TestMetadata  # noqa: E402
from tftbase import TestType  # noqa: E402


def test_str_to_bool() -> None:
    assert common.str_to_bool(True) is True
    assert common.str_to_bool(False) is False

    ERR = object()
    DEF = object()

    # falsy
    assert common.str_to_bool("0") is False
    assert common.str_to_bool("n") is False
    assert common.str_to_bool("no") is False
    assert common.str_to_bool("false") is False

    # truthy
    assert common.str_to_bool("1") is True
    assert common.str_to_bool("y") is True
    assert common.str_to_bool("yes") is True
    assert common.str_to_bool("true") is True

    assert common.str_to_bool("bogus", None) is None
    assert common.str_to_bool("default", None) is None
    assert common.str_to_bool("bogus", ERR) is ERR
    assert common.str_to_bool("default", ERR) is ERR

    assert common.str_to_bool("bogus", ERR, on_default=DEF) is ERR
    assert common.str_to_bool("default", ERR, on_default=DEF) is DEF

    with pytest.raises(TypeError):
        common.str_to_bool("default", ERR, on_error=DEF)  # type: ignore

    with pytest.raises(ValueError):
        assert common.str_to_bool("bogus", on_default=DEF)
    assert common.str_to_bool("bogus", on_default=DEF, on_error=ERR) is ERR
    assert common.str_to_bool("bogus", on_error=ERR) is ERR
    assert common.str_to_bool("default", on_default=DEF) is DEF
    assert common.str_to_bool("default", on_default=DEF, on_error=ERR) is DEF
    assert common.str_to_bool("default", on_error=ERR) is ERR

    # edge cases
    with pytest.raises(ValueError):
        common.str_to_bool(None)
    assert common.str_to_bool(None, on_default=DEF) is DEF
    with pytest.raises(ValueError):
        common.str_to_bool(0, on_default=DEF)  # type: ignore

    obj = object()

    assert common.str_to_bool("True", on_default=False) is True

    assert common.str_to_bool("", on_default=obj) is obj

    with pytest.raises(ValueError):
        common.str_to_bool("")

    assert common.str_to_bool(None, on_default=obj) is obj
    assert common.str_to_bool("", on_default=obj) is obj
    assert common.str_to_bool(" DEFAULT ", on_default=obj) is obj
    assert common.str_to_bool(" -1 ", on_default=obj) is obj

    assert common.str_to_bool(" -1 ", on_default=DEF) is DEF
    assert common.str_to_bool(" -1 ", on_error=ERR) is ERR

    assert common.str_to_bool("", on_default=DEF, on_error=ERR) is DEF
    assert common.str_to_bool("", on_error=ERR) is ERR

    with pytest.raises(ValueError):
        common.str_to_bool("bogus")

    assert common.str_to_bool("bogus", on_error=ERR) is ERR
    assert common.str_to_bool("bogus", on_default=DEF, on_error=obj) is obj

    assert common.bool_to_str(True) == "true"
    assert common.bool_to_str(False) == "false"
    assert common.bool_to_str(True, format="true") == "true"
    assert common.bool_to_str(False, format="true") == "false"
    assert common.bool_to_str(True, format="yes") == "yes"
    assert common.bool_to_str(False, format="yes") == "no"
    with pytest.raises(ValueError):
        common.bool_to_str(False, format="bogus")

    typing.assert_type(common.str_to_bool("true"), bool)
    typing.assert_type(common.str_to_bool("true", on_error=None), bool | None)
    typing.assert_type(common.str_to_bool("true", on_default=None), bool | None)
    typing.assert_type(
        common.str_to_bool("true", on_error=None, on_default=1), bool | None | int
    )
    typing.assert_type(common.str_to_bool("true", on_error=2, on_default=1), bool | int)
    typing.assert_type(
        common.str_to_bool("true", on_error=True, on_default="1"), bool | str
    )
    typing.assert_type(
        common.str_to_bool("true", on_error=True, on_default="1"), bool | str
    )


def test_enum_convert() -> None:
    assert enum_convert(TestType, "IPERF_TCP") == TestType.IPERF_TCP
    assert enum_convert(PodType, 1) == PodType.NORMAL
    assert enum_convert(PodType, "1 ") == PodType.NORMAL
    assert enum_convert(PodType, " normal") == PodType.NORMAL
    with pytest.raises(ValueError):
        enum_convert(TestType, "Not_in_enum")
    with pytest.raises(ValueError):
        enum_convert(TestType, 10000)

    assert enum_convert_list(TestType, [1]) == [TestType.IPERF_TCP]
    assert enum_convert_list(TestType, [TestType.IPERF_TCP]) == [TestType.IPERF_TCP]
    assert enum_convert_list(TestType, ["iperf-tcp"]) == [TestType.IPERF_TCP]
    assert enum_convert_list(TestType, ["iperf_tcp-1,3", 2]) == [
        TestType.IPERF_TCP,
        TestType.HTTP,
        TestType.IPERF_UDP,
    ]

    class E1(Enum):
        Vm4 = -4
        V1 = 1
        V1b = 1
        v2 = 2
        V2 = 3
        V_7 = 10
        V_3 = 6
        v_3 = 7
        V5 = 5

    assert enum_convert(E1, "v5") == E1.V5
    assert enum_convert(E1, "v2") == E1.v2
    assert enum_convert(E1, "V2") == E1.V2
    assert enum_convert(E1, "v_3") == E1.v_3
    assert enum_convert(E1, "V_3") == E1.V_3
    assert enum_convert(E1, "V_7") == E1.V_7
    assert enum_convert(E1, "V-7") == E1.V_7
    with pytest.raises(ValueError):
        assert enum_convert(E1, "v-3") == E1.v_3
    with pytest.raises(ValueError):
        assert enum_convert(E1, "V-3") == E1.V_3
    assert enum_convert(E1, "10") == E1.V_7
    assert enum_convert(E1, "-4") == E1.Vm4
    assert enum_convert(E1, "1") == E1.V1


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
        test_case_id=TestCaseType.POD_TO_POD_DIFF_NODE,
        test_type=TestType.IPERF_UDP,
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
        test_case_id="POD_TO_POD_SAME_NODE",
        test_type="IPERF_TCP",
        server=server.__dict__,
        client=client.__dict__,
    )
    IperfOutput(command="command", result={}, tft_metadata=metadata)

    with pytest.raises(ValueError):
        IperfOutput(command="command", result={}, tft_metadata="string")  # type: ignore


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
