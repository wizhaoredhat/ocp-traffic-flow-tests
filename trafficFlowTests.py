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
from evaluator import Evaluator, Result, Status

class TrafficFlowTests():
    def __init__(self, tft: TestConfig):
        self._tft = tft
        self.servers = []
        self.clients = []
        self.monitors = []
        self.test_settings = None
        self.lh = LocalHost()
        self.log_path = "ft-logs/"

    def create_iperf_server_client(self, test_settings: TestSettings) -> (IperfServer, IperfClient):
        logger.info(f"Initializing iperf server/client for test:\n {test_settings.get_test_info()}")

        s = IperfServer(tft=self._tft, ts=self.test_settings)
        c = IperfClient(tft=self._tft, ts=self.test_settings, server=s)
        return (s, c)

    def configure_namespace(self, namespace: str):
        logger.info(f"Configuring namespace {namespace}")
        r = self._tft.client_tenant.oc(f"label ns --overwrite {namespace} pod-security.kubernetes.io/enforce=privileged \
                                        pod-security.kubernetes.io/enforce-version=v1.24 \
                                        security.openshift.io/scc.podSecurityLabelSync=false")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"configure_namespace(): Failed to label namespace {namespace}")
        logger.info(f"Configured namespace {namespace}")

    def cleanup_previous_testspace(self, namespace: str):
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = self._tft.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete pods")
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning services with label tft-tests in namespace {namespace}")
        r = self._tft.client_tenant.oc(f"delete services -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception(f"cleanup_previous_testspace(): Failed to delete services")
        logger.info(f"Cleaned services with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning external containers {iperf.EXTERNAL_IPERF3_SERVER} (if present)")
        cmd = f"podman stop {iperf.EXTERNAL_IPERF3_SERVER}"
        self.lh.run(cmd)

    def enable_measure_cpu_plugin(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasureCPU(self._tft, node_server_name, tenant)
        c = MeasureCPU(self._tft, node_client_name, tenant)
        self.monitors.append(s)
        self.monitors.append(c)

    def enable_measure_power_plugin(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasurePower(self._tft, node_server_name, tenant)
        c = MeasurePower(self._tft, node_client_name, tenant)
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

    def create_log_path(self, tests: dict) -> str:    
        log_path = self.log_path  
        # Create directory for logging
        if "logs" in tests:
            log_path = tests['logs'] + '/'
        if os.path.exists(log_path):
            shutil.rmtree(log_path)
        logger.info(f"Logs will be written to {log_path}")
        os.makedirs(log_path, exist_ok=False)
        for connection in tests["connections"]:
            os.makedirs(f"{log_path}/{connection['name']}-{self._tft.validate_test_type(connection).name}")
        return log_path

    def evaluate_flow_tests(self, eval_config: str, *log_paths: str, ) -> Status:
        evaluator = Evaluator(eval_config)

        for log_path in log_paths:
            logger.info(f"Evaluating results of tests {log_path}*")
            file_path = self.log_path + "/RESULTS/"
            os.makedirs(file_path, exist_ok=True)

            # Hand evaluator files to evaluate
            for file in os.listdir(log_path):
                log = os.path.join(log_path, file)

                if os.path.isfile(log):
                    logger.debug(f"Evaluating log {log}")
                    evaluator.eval_log(log)

            # Generate Resulting Json
            file = file_path + "summary.json"
            logger.info(f"Dumping results to {file}")
            data = evaluator.dump_to_json()
            with open(file, "w") as file:
                json.dump(data, file)

            # Return Status
            return evaluator.evaluate_pass_fail_status()


    def run(self, tests: dict, eval_config: str) -> Status:
        self.configure_namespace(tests['namespace'])
        self.cleanup_previous_testspace(tests['namespace'])
        self.log_path = self.create_log_path(tests)
        duration = tests['duration']
        logger.info(f"Running {tests['name']} for {duration} seconds")
        test_cases = self._tft.parse_test_cases(tests['test_cases'])
        for test_id in test_cases:
            self.servers = []
            self.clients = []
            self.monitors = []
            #TODO Allow for multiple connections / instances and compile results into single log
            for connections in tests['connections']:
                logger.info(f"Starting {connections['name']}")
                logger.info(f"Number Of Simultaneous connections {connections['instances']}")
                for index in range(connections['instances']):
                    node_server_name = connections['server'][0]['name']
                    node_client_name = connections['client'][0]['name']
                    test_type = self._tft.validate_test_type(connections)
                    log_path=f"{self.log_path}/{connections['name']}-{test_type.name}/"
                    if test_type == TestType.IPERF_TCP or test_type == TestType.IPERF_UDP:
                        self.test_settings = TestSettings(
                            connection_name=connections['name'],
                            test_case_id=test_id,
                            node_server_name=node_server_name,
                            node_client_name=node_client_name,
                            server_pod_type=self._tft.validate_pod_type(connections['server'][0]),
                            client_pod_type=self._tft.validate_pod_type(connections['client'][0]),
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
        return self.evaluate_flow_tests(eval_config, log_path)
