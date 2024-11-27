#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml

from pathlib import Path
from typing import Optional

from ktoolbox import common
from ktoolbox.common import dataclass_to_json

import evalConfig
import tftbase

from tftbase import FlowTestOutput
from tftbase import PassFailStatus
from tftbase import TestResult
from tftbase import TestResultCollection


logger = logging.getLogger("tft." + __name__)


class Evaluator:
    def __init__(self, config_path: Optional[str]):
        if not config_path:
            c = None
        else:
            with open(config_path, encoding="utf-8") as file:
                c = yaml.safe_load(file)

        self.eval_config = evalConfig.Config.parse(c)

    def _eval_flow_test(self, run: FlowTestOutput) -> TestResult:
        md = run.tft_metadata

        bitrate_threshold: Optional[float] = None

        # We accept a missing eval_config entry.
        cfg = self.eval_config.configs.get(md.test_type)
        if cfg is not None:
            cfg_test_case = cfg.test_cases.get(md.test_case_id)
            if cfg_test_case is not None:
                bitrate_threshold = cfg_test_case.get_threshold(is_reverse=md.reverse)

        success = True
        msg: Optional[str] = None
        if not run.success:
            success = False
            if run.msg is not None:
                msg = f"Run failed: {run.msg}"
            else:
                msg = "Run failed for unspecified reason"
        elif not run.bitrate_gbps.is_passing(bitrate_threshold):
            success = False
            msg = f"Run succeeded but {run.bitrate_gbps} is below threshold {bitrate_threshold}"

        return TestResult(
            tft_metadata=md,
            success=success,
            msg=msg,
            bitrate_gbps=run.bitrate_gbps,
            bitrate_threshold=bitrate_threshold,
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
                plugin_result = plugin_output.plugin.eval_plugin_output(
                    run.flow_test.tft_metadata,
                    plugin_output,
                )
                if plugin_result is not None:
                    plugin_results.append(plugin_result)

        return test_results, plugin_results

    def dump_to_json(
        self,
        test_results: list[TestResult],
        plugin_results: list[tftbase.PluginResult],
    ) -> str:
        res = TestResultCollection(
            passing=[r for r in test_results if r.success],
            failing=[r for r in test_results if not r.success],
            plugin_passing=[r for r in plugin_results if r.success],
            plugin_failing=[r for r in plugin_results if not r.success],
        )
        return dataclass_to_json(res)

    def dump_to_json_file(
        self,
        filename: str | Path,
        test_results: list[TestResult],
        plugin_results: list[tftbase.PluginResult],
    ) -> str:
        data = self.dump_to_json(test_results, plugin_results)
        with open(filename, "w") as f:
            f.write(data)
        return data

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

    def log_pass_fail_status(
        self,
        test_results: list[TestResult],
        plugin_results: list[tftbase.PluginResult],
    ) -> PassFailStatus:
        res = self.evaluate_pass_fail_status(test_results, plugin_results)
        logger.info(f"RESULT: Success = {res.result}.")
        logger.info(
            f"  FlowTest results: Passed {res.num_tft_passed}/{res.num_tft_passed + res.num_tft_failed}"
        )
        logger.info(
            f"  Plugin results: Passed {res.num_plugin_passed}/{res.num_plugin_passed + res.num_plugin_failed}"
        )
        return res


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tool to evaluate TFT Flow test results"
    )
    parser.add_argument(
        "config",
        metavar="config",
        type=str,
        help='YAML configuration file with tft test thresholds. See "eval-config.yaml". '
        "The config can also contain a subset of the relevant configurations and skip validation "
        "otherwise. This also means, the entire configuration can be empty (either an empty "
        " YAML file or only '{}'). Also, the filename can be '' to indicate a completely "
        "empty configuration.",
    )
    parser.add_argument(
        "logs",
        type=str,
        help='Result file from ocp-traffic-flow-tests. This defaults to "./ft-logs/$TIMESTAMP.json".',
    )
    parser.add_argument(
        "output",
        type=str,
        help="Output file to write evaluation results to.",
    )
    common.log_argparse_add_argument_verbose(parser)

    args = parser.parse_args()

    common.log_config_logger(args.verbose, "tft", "ktoolbox")

    if args.config and not Path(args.config).exists():
        logger.error(f"No config file found at {args.config}, exiting")
        sys.exit(-1)

    if not args.logs or not Path(args.logs).exists():
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
    data = evaluator.dump_to_json_file(args.output, test_results, plugin_results)
    logger.info(data)

    evaluator.log_pass_fail_status(test_results, plugin_results)


if __name__ == "__main__":
    main()
