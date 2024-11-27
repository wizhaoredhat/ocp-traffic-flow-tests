#!/usr/bin/env python3

import argparse
import logging
import sys
import yaml

from pathlib import Path
from typing import Optional

from ktoolbox import common

import evalConfig
import tftbase

from tftbase import FlowTestOutput
from tftbase import TftResult
from tftbase import TftResults


logger = logging.getLogger("tft." + __name__)


class Evaluator:
    def __init__(self, config_path: Optional[str]):
        if not config_path:
            c = None
        else:
            with open(config_path, encoding="utf-8") as file:
                c = yaml.safe_load(file)

        self.eval_config = evalConfig.Config.parse(c)

    def eval_flow_test_output(self, flow_test: FlowTestOutput) -> FlowTestOutput:

        bitrate_threshold: Optional[float] = None

        # We accept a missing eval_config entry.
        cfg = self.eval_config.configs.get(flow_test.tft_metadata.test_type)
        if cfg is not None:
            cfg_test_case = cfg.test_cases.get(flow_test.tft_metadata.test_case_id)
            if cfg_test_case is not None:
                bitrate_threshold = cfg_test_case.get_threshold(
                    is_reverse=flow_test.tft_metadata.reverse
                )

        success = True
        msg: Optional[str] = None
        if not flow_test.success:
            success = False
            if flow_test.msg is not None:
                msg = f"Run failed: {flow_test.msg}"
            else:
                msg = "Run failed for unspecified reason"
        elif not flow_test.bitrate_gbps.is_passing(bitrate_threshold):
            success = False
            msg = f"Run succeeded but {flow_test.bitrate_gbps} is below threshold {bitrate_threshold}"

        return flow_test.clone(
            eval_result=tftbase.EvalResult(
                success=success,
                msg=msg,
                bitrate_threshold=bitrate_threshold,
            ),
        )

    def eval_test_result(self, tft_result: TftResult) -> TftResult:
        new_flow_test = self.eval_flow_test_output(tft_result.flow_test)

        new_plugins = [
            plugin_output.plugin.eval_plugin_output(
                tft_result.flow_test.tft_metadata,
                plugin_output,
            )
            for plugin_output in tft_result.plugins
        ]

        return TftResult(
            flow_test=new_flow_test,
            plugins=tuple(new_plugins),
        )

    def eval(
        self,
        tft_results: TftResults,
    ) -> TftResults:
        lst = [self.eval_test_result(tft_result) for tft_result in tft_results]
        return TftResults(lst=tuple(lst))

    def eval_from_file(
        self,
        filename: str | Path,
    ) -> TftResults:
        return self.eval(
            TftResults.parse_from_file(filename),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tool to evaluate TFT Flow test results"
    )
    parser.add_argument(
        "config",
        metavar="config",
        type=str,
        help='YAML configuration file with tft test thresholds. See "eval-config.yaml". '
        "The configuration can also contain only a subset of the relevant configurations. "
        "Evaluation will successfully pass if thresholds as missing. "
        "Also, the entire configuration can be empty (either an empty "
        "YAML file or only '{}') or the filename can be '' to indicate a completely "
        "empty configuration.",
    )
    parser.add_argument(
        "logs",
        type=str,
        help="Result file from ocp-traffic-flow-tests. The test run by default writes this as file "
        '"./ft-logs/$TIMESTAMP.json". Also, the test always already performs an evaluation with  '
        "the provided eval config YAML (which can be empty or omitted). The input format is the same as the "
        "output format and the same as the test produces.",
    )
    parser.add_argument(
        "output",
        type=str,
        help="Output file to write evaluation results to. This is the same format as the input argument "
        "'logs'. You can pass the output to evaluator.py again for updating the evaluation.",
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
    tft_results = evaluator.eval_from_file(args.logs)
    tft_results.serialize_to_file(args.output)
    tft_results.get_pass_fail_status().log()


if __name__ == "__main__":
    main()
