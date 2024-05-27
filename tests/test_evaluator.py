import os
import pytest
import subprocess
from pathlib import Path
import filecmp

current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)

config_path = os.path.join(parent_dir, "eval-config.yaml")
evaluator_file = os.path.join(parent_dir, "evaluator.py")

COMMON_COMMAND = ["python", evaluator_file, config_path]


def run_subprocess(command, **kwargs):
    full_command = COMMON_COMMAND + command
    result = subprocess.run(full_command, text=True, **kwargs)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    return result


def test_evaluator_valid_input() -> None:
    log_path = os.path.join(current_dir, "input1.json")
    compare_path1 = os.path.join(current_dir, "output1a.json")
    output_path1 = os.path.join(current_dir, "test-output1.json")

    result = run_subprocess(
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
