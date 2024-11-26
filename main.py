#!/usr/bin/env python3

import argparse

from pathlib import Path

from ktoolbox import common

from testConfig import TestConfig
from testConfig import ConfigDescriptor
from trafficFlowTests import TrafficFlowTests


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="test Traffic Flows in an OVN-Kubernetes cluster."
    )
    parser.add_argument(
        "config",
        metavar="config",
        type=str,
        help="YAML file with test configuration (see config.yaml)",
    )
    parser.add_argument(
        "evaluator_config",
        nargs="?",
        metavar="evaluator_config",
        type=str,
        help="YAML file with configuration for scoring test results (see eval-config.yaml). "
        "This parameter is optional. If provided, this effectively runs "
        "./evaluator.py ${evaluator_config} ${test_result} ${evaluator_result}` on "
        "the result file. You can run this step separately.",
    )
    parser.add_argument(
        "-o",
        "--output-base",
        type=str,
        default=None,
        help="The base name for the result files. If specified, the result will be "
        'written to "${output_base}$(printf \'%%03d\' "$number").json" where ${number} is the '
        "zero-based index of the test. This can include the directory name and is relative to "
        'the current directory. If unspecified, the files are written to "${logs}/${timestamp}.json" '
        'where "${logs}" can be specified in the config file (and defaults to "./ft-logs/").',
    )

    common.log_argparse_add_argument_verbosity(parser)

    args = parser.parse_args()

    common.log_config_logger(args.verbosity, "tft", "ktoolbox")

    if not Path(args.config).exists():
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")

    return args


def main() -> None:
    args = parse_args()

    tc = TestConfig(
        config_path=args.config,
        evaluator_config=args.evaluator_config,
        output_base=args.output_base,
    )
    tft = TrafficFlowTests()

    for cfg_descr in ConfigDescriptor(tc).describe_all_tft():
        tft.test_run(cfg_descr)


if __name__ == "__main__":
    main()
