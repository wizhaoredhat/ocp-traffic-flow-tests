from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ktoolbox import common
from ktoolbox.common import StructParseBase
from ktoolbox.common import strict_dataclass
from ktoolbox.common import structparse_check_empty_dict
from ktoolbox.common import structparse_check_strdict

import testType

from tftbase import TestCaseType
from tftbase import TestType


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class TestItem(StructParseBase):
    threshold: float

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "TestItem":
        vdict = structparse_check_strdict(arg, yamlpath)

        v = vdict.pop("threshold", None)
        try:
            threshold = float(v)
        except ValueError:
            raise ValueError(f"{yamlpath}.threshold: expected a number but got {v}")

        structparse_check_empty_dict(vdict, yamlpath)

        return TestItem(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            threshold=threshold,
        )

    def serialize(self) -> dict[str, Any]:
        return {"threshold": self.threshold}


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class TestCaseData(StructParseBase):
    test_case_type: TestCaseType
    normal: TestItem
    reverse: TestItem

    def get_threshold(self, *, is_reverse: bool) -> float:
        if is_reverse:
            return self.reverse.threshold
        return self.normal.threshold

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "TestCaseData":
        vdict = structparse_check_strdict(arg, yamlpath)

        v = vdict.pop("id", None)
        try:
            test_case_type = common.enum_convert(TestCaseType, v)
        except ValueError:
            raise ValueError(f'{yamlpath}.id: invalid value "{v}"')

        normal = TestItem.parse(0, f"{yamlpath}.Normal", vdict.pop("Normal", None))
        reverse = TestItem.parse(0, f"{yamlpath}.Reverse", vdict.pop("Reverse", None))

        structparse_check_empty_dict(vdict, yamlpath)

        return TestCaseData(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            test_case_type=test_case_type,
            normal=normal,
            reverse=reverse,
        )

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.test_case_type.name,
            "Normal": self.normal.serialize(),
            "Reverse": self.reverse.serialize(),
        }


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class TestTypeData(StructParseBase):
    test_type: TestType
    test_cases: Mapping[TestCaseType, TestCaseData]
    test_type_handler: testType.TestTypeHandler

    @staticmethod
    def parse(yamlidx: int, yamlpath_base: str, key: Any, arg: Any) -> "TestTypeData":
        try:
            test_type = common.enum_convert(TestType, key)
        except Exception:
            raise ValueError(
                f"{yamlpath_base}.[{yamlidx}].: expects a test type as key like iperf-tcp but got {key}"
            )

        yamlpath = f"{yamlpath_base}.{test_type.name}"

        try:
            test_type_handler = testType.TestTypeHandler.get(test_type)
        except Exception:
            raise ValueError(
                f'{yamlpath}: test type "{test_type}" has no handler implementation'
            )

        if not isinstance(arg, list):
            raise ValueError(f'"{yamlpath}": expects a list of test cases')
        test_cases = {}
        for yamlidx2, arg in enumerate(arg):
            c = TestCaseData.parse(yamlidx2, f"{yamlpath}[{yamlidx}]", arg)
            if c.test_case_type in test_cases:
                raise ValueError(
                    f"{yamlpath}[{yamlidx2}]: duplicate key {c.test_case_type.name}"
                )
            test_cases[c.test_case_type] = c

        return TestTypeData(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            test_type=test_type,
            test_type_handler=test_type_handler,
            test_cases=test_cases,
        )

    def serialize(self) -> list[Any]:
        return [v.serialize() for k, v in self.test_cases.items()]


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class Config(StructParseBase):
    configs: Mapping[TestType, TestTypeData]

    @staticmethod
    def parse(arg: Any) -> "Config":
        yamlpath = ""
        vdict = structparse_check_strdict(arg, yamlpath)

        configs = {}

        for yamlidx2, key in enumerate(vdict):
            c = TestTypeData.parse(
                yamlidx=yamlidx2,
                yamlpath_base=yamlpath,
                key=key,
                arg=vdict[key],
            )
            if c.test_type in configs:
                raise ValueError(
                    f"{yamlpath}.[{yamlidx2}]: duplicate key {c.test_type.name}"
                )
            configs[c.test_type] = c

        return Config(
            yamlidx=0,
            yamlpath=yamlpath,
            configs=configs,
        )

    def serialize(self) -> dict[str, Any]:
        return {k.name: v.serialize() for k, v in self.configs.items()}
