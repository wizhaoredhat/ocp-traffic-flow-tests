import os
import argparse

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description='Build a custom image and store in the specified repository')
    parser.add_argument('config', metavar='config', type=str, help='Yaml file with test configuration (see config.yaml)')

    args = parser.parse_args()

    if not os.path.exists(args.config):
        raise ValueError("Must provide a valid config.yaml file (see config.yaml)")

    return args
