import dataclasses
import json
import pytest
import sys
import typing

from enum import Enum

from . import common

from .common import enum_convert
from .common import enum_convert_list
from .common import serialize_enum


class TstTestType(Enum):
    IPERF_TCP = 1
    IPERF_UDP = 2
    HTTP = 3
    NETPERF_TCP_STREAM = 4
    NETPERF_TCP_RR = 5


class TstPodType(Enum):
    NORMAL = 1
    SRIOV = 2
    HOSTBACKED = 3


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

    if sys.version_info >= (3, 10):
        typing.assert_type(common.str_to_bool("true"), bool)
        typing.assert_type(common.str_to_bool("true", on_error=None), bool | None)
        typing.assert_type(common.str_to_bool("true", on_default=None), bool | None)
        typing.assert_type(
            common.str_to_bool("true", on_error=None, on_default=1), bool | None | int
        )
        typing.assert_type(
            common.str_to_bool("true", on_error=2, on_default=1), bool | int
        )
        typing.assert_type(
            common.str_to_bool("true", on_error=True, on_default="1"), bool | str
        )
        typing.assert_type(
            common.str_to_bool("true", on_error=True, on_default="1"), bool | str
        )


def test_enum_convert() -> None:
    assert enum_convert(TstTestType, "IPERF_TCP") == TstTestType.IPERF_TCP
    assert enum_convert(TstPodType, 1) == TstPodType.NORMAL
    assert enum_convert(TstPodType, "1 ") == TstPodType.NORMAL
    assert enum_convert(TstPodType, " normal") == TstPodType.NORMAL
    with pytest.raises(ValueError):
        enum_convert(TstTestType, "Not_in_enum")
    with pytest.raises(ValueError):
        enum_convert(TstTestType, 10000)

    assert enum_convert_list(TstTestType, [1]) == [TstTestType.IPERF_TCP]
    assert enum_convert_list(TstTestType, [TstTestType.IPERF_TCP]) == [
        TstTestType.IPERF_TCP
    ]
    assert enum_convert_list(TstTestType, ["iperf-tcp"]) == [TstTestType.IPERF_TCP]
    assert enum_convert_list(TstTestType, ["iperf_tcp-1,3", 2]) == [
        TstTestType.IPERF_TCP,
        TstTestType.HTTP,
        TstTestType.IPERF_UDP,
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


def test_serialize_enum() -> None:
    # Test with enum value
    assert serialize_enum(TstTestType.IPERF_TCP) == "IPERF_TCP"

    # Test with a dictionary containing enum values
    data = {
        "test_type": TstTestType.IPERF_UDP,
        "pod_type": TstPodType.SRIOV,
        "other_key": "some_value",
    }
    serialized_data = serialize_enum(data)
    assert serialized_data == {
        "test_type": "IPERF_UDP",
        "pod_type": "SRIOV",
        "other_key": "some_value",
    }

    # Test with a list containing enum values
    data_list = [TstTestType.HTTP, TstPodType.HOSTBACKED]
    serialized_list = serialize_enum(data_list)
    assert serialized_list == ["HTTP", "HOSTBACKED"]

    class TstTestCaseType(Enum):
        POD_TO_HOST_SAME_NODE = 5

    class TstConnectionMode(Enum):
        EXTERNAL_IP = 1

    class TstNodeLocation(Enum):
        SAME_NODE = 1

    # Test with nested structures
    nested_data = {
        "nested_dict": {"test_case_id": TstTestCaseType.POD_TO_HOST_SAME_NODE},
        "nested_list": [TstConnectionMode.EXTERNAL_IP, TstNodeLocation.SAME_NODE],
    }
    serialized_nested_data = serialize_enum(nested_data)
    assert serialized_nested_data == {
        "nested_dict": {"test_case_id": "POD_TO_HOST_SAME_NODE"},
        "nested_list": ["EXTERNAL_IP", "SAME_NODE"],
    }

    # Test with non-enum value
    assert serialize_enum("some_string") == "some_string"
    assert serialize_enum(123) == 123


def test_strict_dataclass() -> None:
    @common.strict_dataclass
    @dataclasses.dataclass
    class C2:
        a: str
        b: int
        c: typing.Optional[str] = None

    C2("a", 5)
    C2("a", 5, None)
    C2("a", 5, "")
    with pytest.raises(TypeError):
        C2("a", "5")  # type: ignore
    with pytest.raises(TypeError):
        C2(3, 5)  # type: ignore
    with pytest.raises(TypeError):
        C2("a", 5, [])  # type: ignore

    @common.strict_dataclass
    @dataclasses.dataclass
    class C3:
        a: typing.List[str]

    C3([])
    C3([""])
    with pytest.raises(TypeError):
        C3(1)  # type: ignore
    with pytest.raises(TypeError):
        C3([1])  # type: ignore
    with pytest.raises(TypeError):
        C3(None)  # type: ignore

    @common.strict_dataclass
    @dataclasses.dataclass
    class C4:
        a: typing.Optional[typing.List[str]]

    C4(None)

    @common.strict_dataclass
    @dataclasses.dataclass
    class C5:
        a: typing.Optional[typing.List[typing.Dict[str, str]]] = None

    C5(None)
    C5([])
    with pytest.raises(TypeError):
        C5([1])  # type: ignore
    C5([{}])
    C5([{"a": "b"}])
    C5([{"a": "b"}, {}])
    C5([{"a": "b"}, {"c": "", "d": "x"}])
    with pytest.raises(TypeError):
        C5([{"a": None}])  # type: ignore

    @common.strict_dataclass
    @dataclasses.dataclass
    class C6:
        a: typing.Optional[typing.Tuple[str, str]] = None

    C6()
    C6(None)
    C6(("a", "b"))
    with pytest.raises(TypeError):
        C6(1)  # type: ignore
    with pytest.raises(TypeError):
        C6(("a",))  # type: ignore
    with pytest.raises(TypeError):
        C6(("a", "b", "c"))  # type: ignore
    with pytest.raises(TypeError):
        C6(("a", 1))  # type: ignore

    @common.strict_dataclass
    @dataclasses.dataclass(frozen=True)
    class TstPodInfo:
        name: str
        pod_type: TstPodType
        is_tenant: bool
        index: int

    @common.strict_dataclass
    @dataclasses.dataclass
    class C7:
        addr_info: typing.List[TstPodInfo]

        def _post_check(self) -> None:
            pass

    with pytest.raises(TypeError):
        C7(None)  # type: ignore
    C7([])
    C7([TstPodInfo("name", TstPodType.NORMAL, True, 5)])
    with pytest.raises(TypeError):
        C7([TstPodInfo("name", TstPodType.NORMAL, True, 5), None])  # type:ignore

    @common.strict_dataclass
    @dataclasses.dataclass
    class C8:
        a: str

        def _post_check(self) -> None:
            if self.a == "invalid":
                raise ValueError("_post_check() failed")

    with pytest.raises(TypeError):
        C8(None)  # type: ignore
    C8("hi")
    with pytest.raises(ValueError):
        C8("invalid")

    @common.strict_dataclass
    @dataclasses.dataclass
    class C9:
        a: "str"

    with pytest.raises(NotImplementedError):
        C9("foo")

    @common.strict_dataclass
    @dataclasses.dataclass
    class C10:
        x: float

    C10(1.0)
    with pytest.raises(TypeError):
        C10(1)


def test_dataclass_tofrom_dict() -> None:
    @common.strict_dataclass
    @dataclasses.dataclass
    class C1:
        foo: int
        str: typing.Optional[str]

    c1 = C1(1, "str")
    d1 = common.dataclass_to_dict(c1)
    assert c1 == common.dataclass_from_dict(C1, d1)

    @common.strict_dataclass
    @dataclasses.dataclass
    class C2:
        enum_val: TstTestType
        c1_opt: typing.Optional[C1]
        c1_opt_2: typing.Optional[C1]
        c1_list: list[C1]

    c2 = C2(TstTestType.IPERF_UDP, C1(2, "2"), None, [C1(3, "3"), C1(4, "4")])
    d2 = common.dataclass_to_dict(c2)
    assert (
        json.dumps(d2)
        == '{"enum_val": "IPERF_UDP", "c1_opt": {"foo": 2, "str": "2"}, "c1_opt_2": null, "c1_list": [{"foo": 3, "str": "3"}, {"foo": 4, "str": "4"}]}'
    )
    assert c2 == common.dataclass_from_dict(C2, d2)

    @common.strict_dataclass
    @dataclasses.dataclass
    class C10:
        x: float

    assert common.dataclass_to_dict(C10(1.0)) == {"x": 1.0}

    c10 = C10(1.0)
    assert type(c10.x) is float
    common.dataclass_check(c10)
    c10.x = 1
    assert type(c10.x) is int
    with pytest.raises(TypeError):
        common.dataclass_check(c10)
    assert common.dataclass_to_dict(c10) == {"x": 1}

    assert common.dataclass_from_dict(C10, {"x": 1.0}) == c10
    assert common.dataclass_from_dict(C10, {"x": 1.0}) == C10(1.0)
    assert common.dataclass_from_dict(C10, {"x": 1}) == c10
    assert common.dataclass_from_dict(C10, {"x": 1}) == C10(1.0)
    assert type(common.dataclass_from_dict(C10, {"x": 1}).x) is float
    assert type(common.dataclass_from_dict(C10, {"x": 1.0}).x) is float
    assert type(c10.x) is int
    assert type(C10(1.0).x) is float


def test_kw_only() -> None:
    common.StructParseBaseNamed(yamlpath="yamlpath", yamlidx=0, name="name")
    if sys.version_info >= (3, 10):
        assert common.KW_ONLY_DATACLASS == {"kw_only": True}
        with pytest.raises(TypeError):
            common.StructParseBaseNamed("yamlpath", yamlidx=0, name="name")
        with pytest.raises(TypeError):
            common.StructParseBaseNamed("yamlpath", 0, "name")
    else:
        assert common.KW_ONLY_DATACLASS == {}
        common.StructParseBaseNamed("yamlpath", yamlidx=0, name="name")
        common.StructParseBaseNamed("yamlpath", 0, "name")
