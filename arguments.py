import os
from logger import logger, configure_logger
import logging
import argparse
from pathlib import Path

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description='Build a custom image and store in the specified repository')
    parser.add_argument('config', metavar='config', type=str, help='Yaml file with test configuration (see config.yaml)')
    parser.add_argument('evaluator_config', metavar='evaluator_config', type=str, help="Yaml file with configuration for scoring test results (see eval-config.yaml)")
    parser.add_argument('-v', '--verbosity', choices=['debug', 'info', 'warning', 'error', 'critical'], default='info', help='Set the logging level (default: info)')

    args = parser.parse_args()

    log_levels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    args.verbosity = log_levels[args.verbosity]
    configure_logger(args.verbosity)

    if not Path(args.config).exists():
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")
    if not Path(args.evaluator_config).exists():
        raise ValueError("Must provide a valid config file to evaluate results (see eval-config.yaml)")

    return args
