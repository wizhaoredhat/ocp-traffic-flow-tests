import dataclasses
import filecmp
import json
import os
import pytest
import subprocess
import sys
import yaml

from pathlib import Path
from typing import Any
from typing import Optional

from ktoolbox import common

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import evalConfig  # noqa: E402
import evaluator  # noqa: E402
import tftbase  # noqa: E402

Evaluator = evaluator.Evaluator
TestType = tftbase.TestType
TestCaseType = tftbase.TestCaseType


test_dir = os.path.dirname(__file__)
source_dir = os.path.dirname(test_dir)


def _test_file(filename: str) -> str:
    return os.path.join(test_dir, filename)


def _source_file(filename: str) -> str:
    return os.path.join(source_dir, filename)


EVAL_CONFIG_FILE = _source_file("eval-config.yaml")

EVALUATOR_EXEC = _source_file("evaluator.py")
PRINT_RESULTS_EXEC = _source_file("print_results.py")


@dataclasses.dataclass(frozen=True)
class TestConfigFile:
    filename: str
    is_valid: bool = dataclasses.field(default=True)
    expected_outputfile: Optional[str] = dataclasses.field(default=None)


TEST_CONFIG_FILES = [
    TestConfigFile(_test_file("input1.json"), expected_outputfile="input1-RESULTS"),
    TestConfigFile(_test_file("input2.json"), is_valid=False),
    TestConfigFile(_test_file("input3.json"), is_valid=False),
    TestConfigFile(_test_file("input4.json"), is_valid=False),
    TestConfigFile(_test_file("input5.json")),
    TestConfigFile(_test_file("input6.json"), expected_outputfile="input6-RESULTS"),
]

TEST_EVAL_CONFIG_FILES = [
    EVAL_CONFIG_FILE,
    _test_file("eval-config-2.yaml"),
]


def _run_subprocess(
    command: list[str],
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    if "check" not in kwargs:
        kwargs["check"] = True
    result = subprocess.run(command, text=True, **kwargs)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    return result


def _run_evaluator(filename: str, outfile: str) -> subprocess.CompletedProcess[str]:
    return _run_subprocess(
        [
            sys.executable,
            EVALUATOR_EXEC,
            EVAL_CONFIG_FILE,
            filename,
            outfile,
        ]
    )


def _run_print_results(filename: str) -> subprocess.CompletedProcess[str]:
    return _run_subprocess(
        [
            sys.executable,
            PRINT_RESULTS_EXEC,
            filename,
        ],
        check=False,
    )


@pytest.mark.parametrize("test_eval_config", TEST_EVAL_CONFIG_FILES)
def test_eval_config(test_eval_config: str) -> None:
    filename = test_eval_config
    assert os.path.exists(filename)

    with open(filename, encoding="utf-8") as file:
        conf_dict = yaml.safe_load(file)

    c = evalConfig.Config.parse(conf_dict)

    assert (
        c.configs[TestType.IPERF_UDP]
        .test_cases[TestCaseType.HOST_TO_NODE_PORT_TO_HOST_SAME_NODE]
        .normal.threshold
        == 5
    )

    for test_type in TestType:
        if test_type not in c.configs:
            continue

        assert test_type in (
            TestType.IPERF_UDP,
            TestType.IPERF_TCP,
        )

        d = c.configs[test_type].test_cases

        for test_case_type in TestCaseType:
            assert test_case_type in d

    dump = c.serialize()
    assert c == evalConfig.Config.parse(dump)

    c2 = c.configs[TestType.IPERF_UDP]
    assert c2.test_type == TestType.IPERF_UDP
    assert isinstance(c2.serialize(), list)
    assert c2 == evalConfig.TestTypeData.parse(
        1, "", TestType.IPERF_UDP, c2.serialize()
    )

    c3 = c2.test_cases[TestCaseType.POD_TO_HOST_DIFF_NODE]
    assert c3.test_case_type == TestCaseType.POD_TO_HOST_DIFF_NODE
    assert c3.serialize_json() == json.dumps(
        {
            "id": "POD_TO_HOST_DIFF_NODE",
            "Normal": {"threshold": 5.0},
            "Reverse": {"threshold": 5.0},
        }
    )
    assert c3.yamlpath == ".IPERF_UDP[3]"
    assert c3.normal.yamlpath == ".IPERF_UDP[3].Normal"


@pytest.mark.parametrize("test_input_file", TEST_CONFIG_FILES)
def test_output_list_parse(
    test_input_file: TestConfigFile,
    tmp_path: Path,
) -> None:
    filename = test_input_file.filename
    assert os.path.isfile(filename)

    with open(filename, "r") as f:
        data = f.read()

    if not test_input_file.is_valid:
        with pytest.raises(RuntimeError):
            tftbase.output_list_parse_file(filename)
        # The file is invalid, but we can patch the content to make it valid.
        data = data.replace('"invalid_test_case_id"', '"POD_TO_POD_SAME_NODE"')
        data = data.replace('"invalid_test_type"', '"IPERF_TCP"')
        data = data.replace('"invalid_pod_type"', '"SRIOV"')

    def _check(output: list[tftbase.TftAggregateOutput]) -> None:
        assert isinstance(output, list)
        assert output

    jdata = json.loads(data)

    output = tftbase.output_list_parse(jdata, filename=filename)
    _check(output)

    if test_input_file.is_valid:
        output = tftbase.output_list_parse_file(filename)
        _check(output)

    data2 = tftbase.output_list_serialize(output)
    output2 = tftbase.output_list_parse(data2)
    _check(output2)
    assert output == output2

    outputfile = str(tmp_path / "outputfile.json")
    if test_input_file.is_valid:
        _run_evaluator(filename, outputfile)
    else:
        with pytest.raises(subprocess.CalledProcessError):
            _run_evaluator(filename, outputfile)

    if not test_input_file.is_valid:
        assert not os.path.exists(outputfile)
    else:
        assert os.path.exists(outputfile)

        test_collection1 = common.dataclass_from_file(
            tftbase.TestResultCollection, outputfile
        )
        assert isinstance(test_collection1, tftbase.TestResultCollection)

        if test_input_file.expected_outputfile is not None:
            assert filecmp.cmp(
                outputfile,
                _test_file(test_input_file.expected_outputfile),
            ), f"{repr(outputfile)} does not match {repr(_test_file(test_input_file.expected_outputfile))}"

        res = _run_print_results(outputfile)
        assert res.returncode in (0, 1)
