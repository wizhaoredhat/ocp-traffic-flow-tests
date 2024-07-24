#!/usr/bin/env python

import argparse
import json
import sys

import common
import tftbase


def read_test_result(filename: str) -> tftbase.TestResultCollection:
    with open(filename, "r") as f:
        jdata = json.load(f)

    return common.dataclass_from_dict(tftbase.TestResultCollection, jdata)


def print_result(test_result: tftbase.TestResult) -> None:
    print(
        '"'
        f"Test ID: {test_result.tft_metadata.test_case_id.name}, "
        f"Test Type: {test_result.tft_metadata.test_type.name}, "
        f"Reverse: {common.bool_to_str(test_result.tft_metadata.reverse)}, "
        f"TX Bitrate: {test_result.bitrate_gbps.tx} Gbps, "
        f"RX Bitrate: {test_result.bitrate_gbps.rx} Gbps"
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
    args = parser.parse_args()

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
