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
        help="Yaml file with test configuration (see config.yaml)",
    )
    parser.add_argument(
        "evaluator_config",
        nargs="?",
        metavar="evaluator_config",
        type=str,
        help="Yaml file with configuration for scoring test results (see eval-config.yaml)",
    )
    common.log_argparse_add_argument_verbosity(parser)

    args = parser.parse_args()

    common.log_config_loggers(args.verbosity, "tft", "ktoolbox")

    if not Path(args.config).exists():
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")

    return args


def main() -> None:
    args = parse_args()

    tc = TestConfig(
        config_path=args.config,
        evaluator_config=args.evaluator_config,
    )
    tft = TrafficFlowTests()

    for cfg_descr in ConfigDescriptor(tc).describe_all_tft():
        tft.test_run(cfg_descr)


if __name__ == "__main__":
    main()
