#!/usr/bin/env python3

import argparse
import sys
import traceback

from ktoolbox import common

import tftbase


def print_result(test_result: tftbase.TestResult) -> None:
    if not test_result.success:
        msg = f"failed: {test_result.msg or 'unspecified failure'}"
    else:
        msg = "succeeded"
    print(
        f"Test ID: {test_result.tft_metadata.test_case_id.name}, "
        f"Test Type: {test_result.tft_metadata.test_type.name}, "
        f"Reverse: {common.bool_to_str(test_result.tft_metadata.reverse)}, "
        f"TX Bitrate: {test_result.bitrate_gbps.tx} Gbps, "
        f"RX Bitrate: {test_result.bitrate_gbps.rx} Gbps, "
        f"{msg}"
    )


def print_plugin_result(plugin_result: tftbase.PluginResult) -> None:
    if not plugin_result.success:
        msg = f"failed: {plugin_result.msg or 'unspecified failure'}"
    else:
        msg = "succeeded"
    print("     " f"plugin {plugin_result.plugin_name}, " f"{msg}")


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

    test_results = tftbase.TestResultCollection.read_from_file(args.result)

    group_passing, group_failing = tftbase.GroupedResult.grouped_from(test_results)

    print(
        f"There are {len(group_passing)} passing flows.{' Details:' if group_passing else ''}"
    )
    for group in group_passing:
        for test_result in group.test_results:
            print_result(test_result)
        for plugin_result in group.plugin_results:
            print_plugin_result(plugin_result)

    if group_passing:
        print("\n\n", end="")
    print(
        f"There are {len(group_failing)} failing flows.{' Details:' if group_failing else ''}"
    )
    for group in group_failing:
        for test_result in group.test_results:
            print_result(test_result)
        for plugin_result in group.plugin_results:
            print_plugin_result(plugin_result)

    if group_failing:
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
