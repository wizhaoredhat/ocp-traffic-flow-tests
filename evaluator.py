import argparse
import os
import sys
import yaml
import json
from collections import namedtuple
from common import TestCaseType, TestType
from logger import logger


Bitrate = namedtuple("Bitrate", "tx rx")

#TODO: We made need to extend this to include results from other plugins (i.e. is HWOL working) such that
# we can return a single "Status" from a test
Status = namedtuple("Status", "result num_passed num_failed")

class Result():
    def __init__(self, test_id: TestCaseType, test_type: TestType, success: bool, bitrate_gbps: Bitrate):
        self.test_id = test_id
        self.test_type = test_type
        self.success = success
        self.bitrate_gbps = bitrate_gbps

    def dump_to_json(self) -> dict:
        return {"test_id": self.test_id,
                "test_type": self.test_type,
                "success": self.success,
                "Bitrate_Gbps_Tx": self.bitrate_gbps.tx,
                "Bitrate_Gbps_Rx": self.bitrate_gbps.rx}


class Evaluator():
    def __init__(self, config_path: str):
        with open(config_path, encoding='utf-8') as file:
            c = yaml.safe_load(file)

        self.config = c
        self.results = []

    def eval_log(self, log_path):
        with open(log_path, encoding='utf8') as file:
            self.log = yaml.safe_load(file)

        try:
            metadata = self.log["tft-metadata"]
            test_case_id = metadata["test_case_id"]
            test_type = metadata["test_type"]
            ft_result = self.log["result"]
        except KeyError as e:
            logger.error(f"KeyError: {e}. Malformed log handed to eval_log()")
            raise Exception(f"eval_log(): error parsing {log_path} for expected fields")

        bitrate_threshold = self.get_threshold(test_case_id, test_type)
        bitrate_gbps = self.calculate_gbps(ft_result, test_type)

        result = Result(
            test_id = test_case_id,
            test_type = test_type,
            success = self.is_passing(bitrate_threshold, bitrate_gbps),
            bitrate_gbps = bitrate_gbps)

        self.results.append(result)

    def is_passing(self, threshold: int, bitrate_gbps: Bitrate) -> bool:
        return bitrate_gbps.tx >= threshold and bitrate_gbps.rx >= threshold

    def get_threshold(self, test_case_id: TestCaseType, test_type: TestType) -> int:
        try:
            return self.config[test_type][TestCaseType[test_case_id].value]["threshold"]
        except KeyError as e:
            logger.error(f"KeyError: {e}. Config does not contain valid config for test case {test_type.name} id {test_case_id}")
            raise Exception(f"get_threshold(): Failed to parse evaluator config")

    def calculate_gbps(self, result: dict, test_type: TestType) -> Bitrate:
        if test_type == TestType.IPERF_TCP.name:
            return self.calculate_gbps_iperf_tcp(result)
        elif test_type == TestType.IPERF_UDP.name:
            return self.calculate_gbps_iperf_udp(result)
        elif test_type == TestType.HTTP.name:
            return self.calculate_gbps_http(result)
        else:
            logger.error(f"Error calculating bitrate, Test of type {test_type} is not supported")
            raise Exception(f"calculate_gbps(): Invalid test_type {test_type} provided")

    def dump_to_json(self) -> dict:
        passing = []
        failing = []
        for result in self.results:
            output = {"test_case_id": result.test_id,
                      "test_type": result.test_type,
                      "Bitrate_Gbps_rx": result.bitrate_gbps.rx,
                      "Bitrate_Gbps_tx": result.bitrate_gbps.tx}
            if result.success == True:
                passing.append(output)
            else:
                failing.append(output)
        return {"passing": passing, "failing": failing}

    def calculate_gbps_iperf_tcp(self, result: dict) -> Bitrate:
        # If an error occured, bitrate = 0
        if "error" in result:
            logger.error(f"An error occured during iperf test: {result['error']}")
            return Bitrate(0,0)

        try:
            sum_sent = result["end"]["sum_sent"]
            sum_received = result["end"]["sum_received"]
        except KeyError as e:
            logger.error(f"KeyError: {e}. Malformed results when parsing iperf tcp for sum_sent/received")
            raise Exception(f"calculate_gbps_iperf_tcp(): failed to parse iperf test results")

        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        bitrate_received = sum_received["bits_per_second"] / 1e9

        return Bitrate(float(f"{bitrate_sent:.5g}"), float(f"{bitrate_received:.5g}"))


    def calculate_gbps_iperf_udp(self, result: dict) -> Bitrate:
        # If an error occured, bitrate = 0
        if "error" in result:
            logger.error(f"An error occured during iperf test: {result['error']}")
            return Bitrate(0,0)

        sum_data = result["end"]["sum"]

        # UDP tests only have sender traffic
        bitrate_sent = sum_data["bits_per_second"] / 1e9
        return Bitrate(float(f"{bitrate_sent:.5g}"), float(f"{bitrate_sent:.5g}"))


    def calculate_gbps_http(self, result: dict) -> Bitrate:
        #TODO: Add http traffic testing
        return -1

    def evaluate_pass_fail_status(self) -> Status:
        total_passing = 0
        total_failing = 0
        for result in self.results:
            if result.success:
                total_passing += 1
            else:
                total_failing += 1
        return Status(total_failing == 0, total_passing, total_failing)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Tool to evaluate TFT Flow test results')
    parser.add_argument('config', metavar='config', type=str, help='Yaml file with tft test threshholds')
    parser.add_argument('--logs', type=str, help='Directory containing TFT log files to evaluate')

    args = parser.parse_args()

    if not os.path.exists(args.config):
        logger.error(f"No config file found at {args.config}, exiting")
        sys.exit(-1)

    if args.logs:
        if not os.path.exists(args.logs):
            logger.error(f"Log directory {args.logs} does not exist")
            sys.exit(-1)

    return args

def main():
    args = parse_args()
    evaluator = Evaluator(args.config)

    # Hand evaluator files to evaluate
    for file in os.listdir(args.logs):
        log = os.path.join(args.logs, file)

        if os.path.isfile(log):
            evaluator.eval_log(log)

    # Generate Resulting Json
    data = evaluator.dump_to_json()
    file_path = "/tmp/test.json"
    with open(file_path, "w") as json_file:
        json.dump(data, json_file)
    logger.info(data)

    res = evaluator.evaluate_pass_fail_status()
    logger.info(f"RESULT OF TEST: Success = {res.result}. Passed {res.num_passed}/{res.num_passed + res.num_failed}")

if __name__ == "__main__":
    main()
