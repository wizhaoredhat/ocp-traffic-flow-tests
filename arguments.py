import os
from logger import logger, configure_logger
import logging
import argparse

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description='Build a custom image and store in the specified repository')
    parser.add_argument('config', metavar='config', type=str, help='Yaml file with test configuration (see config.yaml)')
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

    if not os.path.exists(args.config):
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")

    return args
