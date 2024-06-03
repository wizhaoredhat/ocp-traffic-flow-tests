import argparse
import logging

from pathlib import Path

from logger import configure_logger
from testConfig import TestConfig
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
    parser.add_argument(
        "-v",
        "--verbosity",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Set the logging level (default: info)",
    )

    args = parser.parse_args()

    log_levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    args.verbosity = log_levels[args.verbosity]
    configure_logger(args.verbosity)

    if not Path(args.config).exists():
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")

    return args


def main() -> None:
    args = parse_args()
    tc = TestConfig(args.config)
    tft = TrafficFlowTests(tc)

    for test in tft.tc.GetConfig():
        tft.run(test, args.evaluator_config)

        if args.evaluator_config:
            if not tft.evaluate_run_success():
                print(f"Failure detected in {test['name']} results")


if __name__ == "__main__":
    main()
