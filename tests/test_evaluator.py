import filecmp
import json
import os
import pytest
import subprocess
import sys
import yaml

from pathlib import Path
from typing import Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import evalConfig  # noqa: E402
import evaluator  # noqa: E402
import tftbase  # noqa: E402

Evaluator = evaluator.Evaluator
TestType = tftbase.TestType
TestCaseType = tftbase.TestCaseType


current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)

config_path = os.path.join(parent_dir, "eval-config.yaml")
config_path2 = os.path.join(parent_dir, "updated-eval-config.yaml")
evaluator_file = os.path.join(parent_dir, "evaluator.py")

COMMON_COMMAND = ["python", evaluator_file, config_path]


def run_subprocess(
    command: list[str], **kwargs: Any
) -> subprocess.CompletedProcess[str]:
    full_command = COMMON_COMMAND + command
    result = subprocess.run(full_command, text=True, **kwargs)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    return result


def test_evaluator_valid_input() -> None:
    log_path = os.path.join(current_dir, "input1.json")
    compare_path1 = os.path.join(current_dir, "output1a.json")
    output_path1 = os.path.join(current_dir, "test-output1.json")

    run_subprocess(
        [log_path, output_path1],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert filecmp.cmp(
        output_path1, compare_path1
    ), f"{output_path1} does not match {compare_path1}"

    Path(output_path1).unlink()


def test_evaluator_invalid_test_case_id() -> None:
    log_path = os.path.join(current_dir, "input2.json")

    with pytest.raises(subprocess.CalledProcessError):
        run_subprocess(
            [log_path],
            check=True,
        )


def test_evaluator_invalid_test_type() -> None:
    log_path = os.path.join(current_dir, "input3.json")

    with pytest.raises(subprocess.CalledProcessError):
        run_subprocess(
            [log_path],
            check=True,
        )


def test_evaluator_invalid_pod_type() -> None:
    log_path = os.path.join(current_dir, "input4.json")

    with pytest.raises(subprocess.CalledProcessError):
        run_subprocess(
            [log_path],
            check=True,
        )


def test_eval_config() -> None:
    def _check(filename: str) -> None:
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
        assert c3.yamlpath == ".IPERF_UDP[1]"
        assert c3.normal.yamlpath == ".IPERF_UDP[1].Normal"

    _check(config_path)
    _check(config_path2)
