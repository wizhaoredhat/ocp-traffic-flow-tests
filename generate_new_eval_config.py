# Script to generates a new eval_config ymal file from the json RESULTS output
import json
import yaml
import math
import sys
from common import TestCaseType
from typing import Any


# can implement custom rounding if you want
def custom_floor(value: float) -> int:
    base = math.floor(value)
    return base - 2


def process_test_cases(
    test_cases: list[dict[str, Any]], test_config_map: dict[tuple[str, int], Any]
) -> None:
    for item in test_cases:
        test_id_desc = item["test_id"]
        test_type = item["test_type"]
        reverse = item["reverse"]
        tx = item["bitrate_gbps"]["tx"]
        rx = item["bitrate_gbps"]["rx"]
        average = (tx + rx) / 2
        floored_value = custom_floor(average)

        enum_id = TestCaseType[test_id_desc].value

        if (test_type, enum_id) in test_config_map:
            test_config = test_config_map[(test_type, enum_id)]
            case_type = "Reverse" if reverse else "Normal"
            test_config[case_type]["threshold"] = floored_value
            print(
                f"{enum_id:<2} {case_type:<8} {average:.2f} {floored_value:>5} {test_id_desc:<36}"
            )


with open("eval-config.yaml", "r") as yaml_file:
    eval_config = yaml.safe_load(yaml_file)

# e.g. "tests/sample-results-sriov-subscription/2024-04-30-10-30-10-RESULTS"
if len(sys.argv) < 2:
    print("Usage: python generate_new_eval_config.py <path_to_results_json>")
    sys.exit(1)

results_json_path = sys.argv[1]
with open(results_json_path, "r") as json_file:
    result_json = json.load(json_file)

# Create a test configuration map for easy access to threshold data
test_config_map: dict[tuple[str, int], Any] = {}
for test_type, tests in eval_config.items():
    for test in tests:
        test_config_map[(test_type, test["id"])] = test

process_test_cases(result_json["passing"], test_config_map)
process_test_cases(result_json["failing"], test_config_map)

with open("updated-eval-config.yaml", "w") as yaml_file:
    yaml.dump(eval_config, yaml_file, default_flow_style=False)
