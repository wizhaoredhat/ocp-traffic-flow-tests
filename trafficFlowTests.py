import common
from common import PodType, ConnectionMode, TestCaseType, TestType
from testSettings import TestSettings
from testConfig import TestConfig
from logger import logger
import iperf
from iperf import IperfServer, IperfClient
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

class TrafficFlowTests():
    def __init__(self, cc: TestConfig):
        self._cc = cc
        self.servers = []
        self.clients = []
        self.monitors = []
        self.test_settings = None
        self.lh = LocalHost()
        self.log_path = Path("ft-logs")
        self.paths_to_run_logs = []

    def get_path_to_results(self) -> str:
        return self.log_path + "/RESULTS/"


    def create_iperf_server_client(self, test_settings: TestSettings) -> (IperfServer, IperfClient):
        logger.info(f"Initializing iperf server/client for test:\n {test_settings.get_test_info()}")

        s = IperfServer(cc=self._cc, ts=self.test_settings)
        c = IperfClient(cc=self._cc, ts=self.test_settings, server=s)
        return (s, c)

    def configure_namespace(self, namespace: str):
        logger.info(f"Configuring namespace {namespace}")
        r = self._cc.client_tenant.oc(f"label ns --overwrite {namespace} pod-security.kubernetes.io/enforce=privileged \
                                        pod-security.kubernetes.io/enforce-version=v1.24 \
                                        security.openshift.io/scc.podSecurityLabelSync=false")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"configure_namespace(): Failed to label namespace {namespace}")
        logger.info(f"Configured namespace {namespace}")

    def cleanup_previous_testspace(self, namespace: str):
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = self._cc.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete pods")
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning services with label tft-tests in namespace {namespace}")
        r = self._cc.client_tenant.oc(f"delete services -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete services")
        logger.info(f"Cleaned services with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning external containers {iperf.EXTERNAL_IPERF3_SERVER} (if present)")
        cmd = f"podman stop {iperf.EXTERNAL_IPERF3_SERVER}"
        self.lh.run(cmd)

    def enable_measure_cpu_plugin(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasureCPU(self._cc, node_server_name, tenant)
        c = MeasureCPU(self._cc, node_client_name, tenant)
        self.monitors.append(s)
        self.monitors.append(c)

    def enable_measure_power_plugin(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasurePower(self._cc, node_server_name, tenant)
        c = MeasurePower(self._cc, node_client_name, tenant)
        self.monitors.append(s)
        self.monitors.append(c)

    def run_tests(self, duration: int):
        for tasks in self.servers + self.clients + self.monitors:
            tasks.setup()

        for tasks in self.servers + self.clients + self.monitors:
            tasks.run(duration)

        for tasks in self.servers + self.clients + self.monitors:
            tasks.stop()

        for tasks in self.servers + self.clients + self.monitors:
            tasks.output()

    def create_log_paths_from_tests(self, tests: dict):     
        if "logs" in tests:
            self.log_path = Path(tests['logs'])
        self.log_path = self.log_path
        logger.info(f"Logs will be written to {self.log_path}")
        if self.log_path.is_dir():
            shutil.rmtree(self.log_path)
        
        # Create directory for each connection / instance to store run results
        for connections in tests['connections']:
            for index in range(connections['instances']):
                path=Path(f"{self.log_path}/{connections['name']}-{index}")
                logger.info(f"Creating dir {path}")
                path.mkdir(parents=True)
        

    def evaluate_flow_tests(self, eval_config: str, log_dir: Path) -> PassFailStatus:
        evaluator = Evaluator(eval_config)

        logger.info(f"Evaluating results of tests {log_dir}")
        results_path = self.log_path / "RESULTS"
        results_path.mkdir(exist_ok=True)

        # Hand evaluator files to evaluate
        for file in log_dir.iterdir():
            if file.exists():
                logger.debug(f"Evaluating log {file}")
                evaluator.eval_log(file)

        # Generate Resulting Json
        file = results_path / "summary.json"
        logger.info(f"Dumping results to {file}")
        data = evaluator.dump_to_json()
        with open(file, "w") as file:
            file.write(data)

        # Return PassFailStatus
        return evaluator.evaluate_pass_fail_status()


    def run_test_case(self, tests: dict, test_id: int):
        self.servers = []
        self.clients = []
        self.monitors = []
        duration = tests['duration']
        #TODO Allow for multiple connections / instances to run simultaneously
        for connections in tests['connections']:
            logger.info(f"Starting {connections['name']}")
            logger.info(f"Number Of Simultaneous connections {connections['instances']}")
            for index in range(connections['instances']):
                node_server_name = connections['server'][0]['name']
                node_client_name = connections['client'][0]['name']
                test_type = self._cc.validate_test_type(connections)
                log_path=Path(f"{self.log_path}/{connections['name']}-{index}")
                if log_path not in self.paths_to_run_logs:
                    self.paths_to_run_logs.append(log_path)

                if test_type == TestType.IPERF_TCP or test_type == TestType.IPERF_UDP:
                    self.test_settings = TestSettings(
                        connection_name=connections['name'],
                        test_case_id=test_id,
                        node_server_name=node_server_name,
                        node_client_name=node_client_name,
                        server_pod_type=self._cc.validate_pod_type(connections['server'][0]),
                        client_pod_type=self._cc.validate_pod_type(connections['client'][0]),
                        index=index,
                        test_type=test_type,
                        log_path=log_path,
                    )
                    s, c = self.create_iperf_server_client(self.test_settings)
                    self.servers.append(s)
                    self.clients.append(c)
                else:
                    logger.error("http connections not currently supported")
                if connections['plugins']:
                    for plugins in connections['plugins']:
                        if plugins['name'] == "measure_cpu":
                            self.enable_measure_cpu_plugin(node_server_name, node_client_name, True)
                        if plugins['name'] == "measure_power":
                            self.enable_measure_power_plugin(node_server_name, node_client_name, True)

                self.run_tests(duration)
                self.cleanup_previous_testspace(tests['namespace'])

    def evaluate_run_success(self) -> bool:
        all_passing = True
        # For the result of every test run, check the status of each run log to ensure all test passed
        results = []
        for run_log_path in self.paths_to_run_logs:
            results.append(self.evaluate_flow_tests(self.eval_config, run_log_path))
        

        for pfstatus in results:
            logger.info(f"RESULT: Success = {pfstatus.result}. Passed {pfstatus.num_passed}/{pfstatus.num_passed + pfstatus.num_failed}")
            if not pfstatus.result:
                all_passing = False
        
        return all_passing

    def run(self, tests: dict, eval_config: str):
        self.paths_to_run_logs = []
        self.eval_config = eval_config
        self.configure_namespace(tests['namespace'])
        self.cleanup_previous_testspace(tests['namespace'])
        self.create_log_paths_from_tests(tests)
        logger.info(f"Running test {tests['name']} for {tests['duration']} seconds")
        test_cases = self._cc.parse_test_cases(tests['test_cases'])
        for test_id in test_cases:
            self.run_test_case(
                tests=tests,
                test_id=test_id)

