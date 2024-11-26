#!/usr/bin/env python3

import argparse
import sys
import traceback

from typing import Optional

from ktoolbox import common

import tftbase


def print_flow_test_output(test_output: Optional[tftbase.FlowTestOutput]) -> None:
    if test_output is None:
        print("Test ID: Unknown test")
        return
    if not test_output.eval_success:
        msg = f"failed: {test_output.eval_msg}"
    else:
        msg = "succeeded"
    print(
        f"Test ID: {test_output.tft_metadata.test_case_id.name}, "
        f"Test Type: {test_output.tft_metadata.test_type.name}, "
        f"Reverse: {common.bool_to_str(test_output.tft_metadata.reverse)}, "
        f"TX Bitrate: {test_output.bitrate_gbps.tx} Gbps, "
        f"RX Bitrate: {test_output.bitrate_gbps.rx} Gbps, "
        f"{msg}"
    )


def print_plugin_output(plugin_output: tftbase.PluginOutput) -> None:
    msg = f"failed: {plugin_output.eval_msg}"
    if not plugin_output.eval_success:
        msg = f"failed: {plugin_output.eval_msg}"
    else:
        msg = "succeeded"
    print("     " f"plugin {plugin_output.plugin_metadata.plugin_name}, " f"{msg}")


def print_tft_result(tft_result: tftbase.TftResult) -> None:
    print_flow_test_output(tft_result.flow_test)
    for plugin_output in tft_result.plugins:
        print_plugin_output(plugin_output)


def print_tft_results(tft_results: list[tftbase.TftResult]) -> None:
    for tft_result in tft_results:
        print_tft_result(tft_result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tool to prettify the TFT Flow test results"
    )
    parser.add_argument(
        "result",
        type=str,
        help="The JSON result file from TFT Flow test",
    )
    common.log_argparse_add_argument_verbose(parser)

    args = parser.parse_args()

    common.log_config_logger(args.verbose, "tft", "ktoolbox")

    tft_results = tftbase.output_list_parse_file(args.result)

    group_success, group_fail = tftbase.TftResult.group_by_success(tft_results)

    print(
        f"There are {len(group_success)} passing flows.{' Details:' if group_success else ''}"
    )
    print_tft_results(group_success)

    if group_success:
        print("\n\n", end="")
    print(
        f"There are {len(group_fail)} failing flows.{' Details:' if group_fail else ''}"
    )
    print_tft_results(group_fail)

    if group_fail:
        print("Failures detected")
        sys.exit(1)
    else:
        print("No failures detected in results")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
