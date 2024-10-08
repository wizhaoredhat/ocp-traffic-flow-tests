#!/usr/bin/env python3

import argparse
import json
import sys

from ktoolbox import common

import tftbase


def read_test_result(filename: str) -> tftbase.TestResultCollection:
    with open(filename, "r") as f:
        jdata = json.load(f)

    return common.dataclass_from_dict(tftbase.TestResultCollection, jdata)


def print_result(test_result: tftbase.TestResult) -> None:
    msg = ""
    if not test_result.success:
        msg = test_result.msg or "unspecified failure"
        msg = f", {msg}"

    print(
        '"'
        f"Test ID: {test_result.tft_metadata.test_case_id.name}, "
        f"Test Type: {test_result.tft_metadata.test_type.name}, "
        f"Reverse: {common.bool_to_str(test_result.tft_metadata.reverse)}, "
        f"TX Bitrate: {test_result.bitrate_gbps.tx} Gbps, "
        f"RX Bitrate: {test_result.bitrate_gbps.rx} Gbps"
        f"{msg}"
        '"'
    )


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

    test_results = read_test_result(args.result)

    if test_results.passing:
        print(f"There are {len(test_results.passing)} passing flows. Details:")
        for test_result in test_results.passing:
            print_result(test_result)
        print("\n\n\n")

    if test_results.failing:
        print(f"There are {len(test_results.failing)} failing flows. Details:")
        for test_result in test_results.failing:
            print_result(test_result)
        sys.exit(1)
    print("No failures detected in results")


if __name__ == "__main__":
    main()
