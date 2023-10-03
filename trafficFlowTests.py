import common
from common import PodType, ConnectionMode, TestCaseType, TestType, TftAggregateOutput, TFT_TESTS
from testSettings import TestSettings
from testConfig import TestConfig
from logger import logger
import iperf
from iperf import IperfServer, IperfClient
from validateOffload import ValidateOffload
from measureCpu import MeasureCPU
from measurePower import MeasurePower
from enum import Enum
from host import LocalHost
import sys
import os
import shutil
import json
from pathlib import Path
from evaluator import Evaluator, PassFailStatus
from typing import List
import datetime
from dataclasses import asdict

class TrafficFlowTests():
    def __init__(self, tc: TestConfig):
        self._tc = tc
        self.test_settings = None
        self.lh = LocalHost()
        self.log_path = Path("ft-logs")
        self.log_file = None
        self.tft_output: List[TftAggregateOutput] = []


    def _create_iperf_server_client(self, test_settings: TestSettings) -> (IperfServer, IperfClient):
        logger.info(f"Initializing iperf server/client for test:\n {test_settings.get_test_info()}")

        s = IperfServer(tc=self._tc, ts=self.test_settings)
        c = IperfClient(tc=self._tc, ts=self.test_settings, server=s)
        return (s, c)

    def _configure_namespace(self, namespace: str):
        logger.info(f"Configuring namespace {namespace}")
        r = self._tc.client_tenant.oc(f"label ns --overwrite {namespace} pod-security.kubernetes.io/enforce=privileged \
                                        pod-security.kubernetes.io/enforce-version=v1.24 \
                                        security.openshift.io/scc.podSecurityLabelSync=false")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"configure_namespace(): Failed to label namespace {namespace}")
        logger.info(f"Configured namespace {namespace}")

    def _cleanup_previous_testspace(self, namespace: str):
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = self._tc.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete pods")
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning services with label tft-tests in namespace {namespace}")
        r = self._tc.client_tenant.oc(f"delete services -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete services")
        logger.info(f"Cleaned services with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning external containers {iperf.EXTERNAL_IPERF3_SERVER} (if present)")
        cmd = f"podman stop {iperf.EXTERNAL_IPERF3_SERVER}"
        self.lh.run(cmd)

    def _enable_measure_cpu_plugin(self, monitors: list, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasureCPU(self._tc, node_server_name, tenant)
        c = MeasureCPU(self._tc, node_client_name, tenant)
        monitors.append(s)
        monitors.append(c)

    def _enable_measure_power_plugin(self, monitors: list, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasurePower(self._tc, node_server_name, tenant)
        c = MeasurePower(self._tc, node_client_name, tenant)
        monitors.append(s)
        monitors.append(c)
    
    def enable_validate_offload_plugin(self, monitors: list, iperf_server: IperfServer, iperf_client: IperfClient, tenant: bool):
        s = ValidateOffload(self._tc, iperf_server, tenant)
        c = ValidateOffload(self._tc, iperf_client, tenant)
        monitors.append(s)
        monitors.append(c)

    def _run_tests(self, servers, clients, monitors, duration: int) -> TftAggregateOutput:
        tft_aggregate_output = TftAggregateOutput()
        
        for tasks in servers + clients + monitors:
            tasks.setup()

        for tasks in servers + clients + monitors:
            tasks.run(duration)

        for tasks in servers + clients + monitors:
            tasks.stop()

        for tasks in servers + clients + monitors:
            tasks.output(tft_aggregate_output)

        return tft_aggregate_output

    def _create_log_paths_from_tests(self, tests: dict):     
        if "logs" in tests:
            self.log_path = Path(tests['logs'])
        self.log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        self.log_file = self.log_path / f"{timestamp}.json"
        logger.info(f"Logs will be written to {self.log_file}")

    def _dump_result_to_log(self):
        # Dump test outputs into log file
        log = self.log_file
        json_out = {TFT_TESTS: []}
        for out in self.tft_output:
            json_out[TFT_TESTS].append(
                asdict(out)
            )
        with open(log, "w") as output_file:
            json.dump(json_out, output_file)

    def evaluate_run_success(self) -> bool:
        # For the result of every test run, check the status of each run log to ensure all test passed
        evaluator = Evaluator(self.eval_config)

        logger.info(f"Evaluating results of tests {self.log_file}")
        results_file = str(self.log_file.stem) + "-RESULTS"
        results_path = self.log_path / results_file


        evaluator.eval_log(self.log_file)

        # Generate Resulting Json
        logger.info(f"Dumping results to {results_path}")
        data = evaluator.dump_to_json()
        with open(results_path, "w") as file:
            file.write(data)

        # Return PassFailStatus
        pfstatus = evaluator.evaluate_pass_fail_status()

        logger.info(f"RESULT: Success = {pfstatus.result}. Passed {pfstatus.num_passed}/{pfstatus.num_passed + pfstatus.num_failed}")

        return pfstatus.result

    def _run(self, connections: dict, test_type: TestType, test_id: int, index: int, duration: int, reverse: bool = False):
        servers = []
        clients = []
        monitors = []
        node_server_name = connections['server'][0]['name']
        node_client_name = connections['client'][0]['name']

        if test_type == TestType.IPERF_TCP or test_type == TestType.IPERF_UDP:
            self.test_settings = TestSettings(
                connection_name=connections['name'],
                test_case_id=test_id,
                node_server_name=node_server_name,
                node_client_name=node_client_name,
                server_pod_type=self._tc.validate_pod_type(connections['server'][0]),
                client_pod_type=self._tc.validate_pod_type(connections['client'][0]),
                index=index,
                test_type=test_type,
                reverse=reverse
            )
            s, c = self._create_iperf_server_client(self.test_settings)
            servers.append(s)
            clients.append(c)
        else:
            logger.error("http connections not currently supported")
            raise Exception("http connections not currently supported")
        if connections['plugins']:
            for plugins in connections['plugins']:
                if plugins['name'] == "measure_cpu":
                    self._enable_measure_cpu_plugin(monitors, node_server_name, node_client_name, True)
                if plugins['name'] == "measure_power":
                    self._enable_measure_power_plugin(monitors, node_server_name, node_client_name, True)
                if plugins['name'] == "validate_offload":
                    # TODO allow this to run on each individual server + client pairs.
                    iperf_server = servers[-1]
                    iperf_client = clients[-1]
                    self.enable_validate_offload_plugin(monitors, iperf_server, iperf_client, True)

        output = self._run_tests(servers, clients, monitors, duration)
        self.tft_output.append(output)


    def _run_test_case(self, tests: dict, test_id: int):
        duration = tests['duration']
        #TODO Allow for multiple connections / instances to run simultaneously
        for connections in tests['connections']:
            logger.info(f"Starting {connections['name']}")
            logger.info(f"Number Of Simultaneous connections {connections['instances']}")
            for index in range(connections['instances']):
                test_type = self._tc.validate_test_type(connections)
                # if test_type is iperf_TCP run both forward and reverse tests
                self._run(connections=connections, test_type=test_type, test_id=test_id, index=index, duration=duration)
                if test_type == TestType.IPERF_TCP:
                    self._run(connections=connections, test_type=test_type, test_id=test_id, index=index, duration=duration, reverse=True)
                self._cleanup_previous_testspace(tests['namespace'])

    def run(self, tests: dict, eval_config: str) -> Path:
        self.eval_config = eval_config
        self._configure_namespace(tests['namespace'])
        self._cleanup_previous_testspace(tests['namespace'])
        self._create_log_paths_from_tests(tests)
        logger.info(f"Running test {tests['name']} for {tests['duration']} seconds")
        test_cases = self._tc.parse_test_cases(tests['test_cases'])
        for test_id in test_cases:
            self._run_test_case(
                tests=tests,
                test_id=test_id)
        self._dump_result_to_log()
