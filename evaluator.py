import argparse
import json
import sys
import yaml

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import evalConfig
import pluginbase
import tftbase

from common import serialize_enum
from common import strict_dataclass
from logger import logger
from testType import TestTypeHandler
from tftbase import Bitrate
from tftbase import IperfOutput
from tftbase import TestCaseType
from tftbase import TestType


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class PassFailStatus:
    """Pass/Fail ratio and result from evaluating a full tft Flow Test result

    Attributes:
        result: boolean representing whether the test was successful (100% passing)
        num_passed: int number of test cases passed
        num_failed: int number of test cases failed"""

    result: bool
    num_tft_passed: int
    num_tft_failed: int
    num_plugin_passed: int
    num_plugin_failed: int


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class TestResult:
    """Result of a single test case run

    Attributes:
        test_id: TestCaseType enum representing the type of traffic test (i.e. POD_TO_POD_SAME_NODE <1> )
        test_type: TestType enum representing the traffic protocol (i.e. iperf_tcp)
        reverse: Specify whether test is client->server or reversed server->client
        success: boolean representing whether the test passed or failed
        birate_gbps: Bitrate namedtuple containing the resulting rx and tx bitrate in Gbps
    """

    test_id: TestCaseType
    test_type: TestType
    reverse: bool
    success: bool
    bitrate_gbps: Bitrate


class Evaluator:
    def __init__(self, config_path: str):
        with open(config_path, encoding="utf-8") as file:
            c = yaml.safe_load(file)

        self.eval_config = evalConfig.Config.parse(c)

    def _eval_flow_test(self, run: IperfOutput) -> TestResult:
        md = run.tft_metadata

        bitrate_gbps = Bitrate.NA
        bitrate_threshold: Optional[float] = None

        # We accept a missing eval_config entry. That is also because we can
        # generate a eval_config with "generate_new_eval_config.py", but for
        # that we require to successfully generate a RESULT first.
        cfg = self.eval_config.configs.get(md.test_type)
        if cfg is not None:
            cfg_test_case = cfg.test_cases.get(md.test_case_id)
            if cfg_test_case is not None:
                bitrate_threshold = cfg_test_case.get_threshold(is_reverse=md.reverse)
            bitrate_gbps = TestTypeHandler.get(cfg.test_type).calculate_gbps(run.result)

        return TestResult(
            test_id=md.test_case_id,
            test_type=md.test_type,
            reverse=md.reverse,
            success=bitrate_gbps.is_passing(bitrate_threshold),
            bitrate_gbps=bitrate_gbps,
        )

    def eval_log(
        self, log_path: str | Path
    ) -> tuple[list[TestResult], list[tftbase.PluginResult]]:
        try:
            runs = tftbase.output_list_parse_file(log_path)
        except Exception as e:
            logger.error(f"error parsing {log_path}: {e}")
            raise Exception(f"error parsing {log_path}: {e}")

        test_results: list[TestResult] = []
        plugin_results: list[tftbase.PluginResult] = []

        for run_idx, run in enumerate(runs):
            if run.flow_test is None:
                logger.error(f'invalid result #{run_idx}: missing "flow_test"')
                raise Exception(f'invalid result #{run_idx}: missing "flow_test"')
            result = self._eval_flow_test(run.flow_test)
            test_results.append(result)
            for plugin_output in run.plugins:
                plugin = pluginbase.get_by_name(plugin_output.name)
                plugin_result = plugin.eval_log(
                    plugin_output, run.flow_test.tft_metadata
                )
                if plugin_result is not None:
                    plugin_results.append(plugin_result)

        return test_results, plugin_results

    def dump_to_json(
        self,
        test_results: list[TestResult],
        plugin_results: list[tftbase.PluginResult],
    ) -> str:
        passing = [asdict(result) for result in test_results if result.success]
        failing = [asdict(result) for result in test_results if not result.success]
        plugin_passing = [asdict(result) for result in plugin_results if result.success]
        plugin_failing = [
            asdict(result) for result in plugin_results if not result.success
        ]

        return json.dumps(
            {
                "passing": serialize_enum(passing),
                "failing": serialize_enum(failing),
                "plugin_passing": serialize_enum(plugin_passing),
                "plugin_failing": serialize_enum(plugin_failing),
            }
        )

    def evaluate_pass_fail_status(
        self,
        test_results: list[TestResult],
        plugin_results: list[tftbase.PluginResult],
    ) -> PassFailStatus:
        tft_passing = 0
        tft_failing = 0
        for result in test_results:
            if result.success:
                tft_passing += 1
            else:
                tft_failing += 1

        plugin_passing = 0
        plugin_failing = 0
        for plugin_result in plugin_results:
            if plugin_result.success:
                plugin_passing += 1
            else:
                plugin_failing += 1

        return PassFailStatus(
            result=tft_failing + plugin_failing == 0,
            num_tft_passed=tft_passing,
            num_tft_failed=tft_failing,
            num_plugin_passed=plugin_passing,
            num_plugin_failed=plugin_failing,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tool to evaluate TFT Flow test results"
    )
    parser.add_argument(
        "config", metavar="config", type=str, help="Yaml file with tft test threshholds"
    )
    parser.add_argument(
        "logs", type=str, help="Directory containing TFT log files to evaluate"
    )
    parser.add_argument(
        "output", type=str, help="Output file to write evaluation results to"
    )

    args = parser.parse_args()

    if not Path(args.config).exists():
        logger.error(f"No config file found at {args.config}, exiting")
        sys.exit(-1)

    if not Path(args.logs).exists():
        logger.error(f"Log file {args.logs} does not exist")
        sys.exit(-1)

    return args


def main() -> None:
    args = parse_args()
    evaluator = Evaluator(args.config)

    # Hand evaluator log file to evaluate
    file = Path(args.logs)

    test_results, plugin_results = evaluator.eval_log(file)

    # Generate Resulting Json
    data = evaluator.dump_to_json(test_results, plugin_results)
    file_path = args.output
    with open(file_path, "w") as json_file:
        json_file.write(data)
    logger.info(data)

    res = evaluator.evaluate_pass_fail_status(test_results, plugin_results)
    logger.info(f"RESULT OF TEST: Success = {res.result}.")
    logger.info(
        f"  FlowTest results: Passed {res.num_tft_passed}/{res.num_tft_passed + res.num_tft_failed}"
    )
    logger.info(
        f"  Plugin results: Passed {res.num_plugin_passed}/{res.num_plugin_passed + res.num_plugin_failed}"
    )


if __name__ == "__main__":
    main()
