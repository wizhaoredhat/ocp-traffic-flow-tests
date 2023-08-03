import common
from common import PodType, ConnectionMode, TestCaseType
from testSettings import TestSettings
from testConfig import TestConfig
from logger import logger
from iperf import IperfServer
from iperf import IperfClient
from measureCpu import MeasureCPU
from measurePower import MeasurePower
from enum import Enum
import sys

class TrafficFlowTests():
    def __init__(self, tft: TestConfig):
        self._tft = tft
        self.monitors = []

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
            sys.exit(-1)
        logger.info(f"Configured namespace {namespace}")

    def cleanup_previous_pods(self, namespace: str):
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = self._tft.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            sys.exit(-1)
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")

    def measure_cpu(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasureCPU(self._tft, node_server_name, tenant)
        c = MeasureCPU(self._tft, node_client_name, tenant)
        self.monitors.append(s)
        self.monitors.append(c)

    def measure_power(self, node_server_name: str, node_client_name: str, tenant: bool):
        s = MeasurePower(self._tft, node_server_name, tenant)
        c = MeasurePower(self._tft, node_client_name, tenant)
        self.monitors.append(s)
        self.monitors.append(c)

    def run(self):
        #servers = []
        #clients = []
        #monitors = []
        """
        for tests in self._tft.GetConfig():
            self.cleanup_previous_pods(tests['namespace'])
            self.configure_namespace(tests['namespace'])
            duration = tests['duration']
            logger.info(f"Running {tests['name']} for {duration} seconds")
            test_cases = [int(x) for x in tests['test_cases'].split(',') if x.strip().isdigit()]
            for test_id in test_cases:
                for connections in tests['connections']:
                    logger.info(f"Starting {connections['name']}")
                    logger.info(f"Number Of Simultaneous connections {connections['instances']}")
                    for index in range(connections['instances']):
                        node_server_name = connections['server'][0]['name']
                        node_client_name = connections['client'][0]['name']
                        if connections['type'] == "iperf":
                            s = IperfServer(self._tft, index, node_server_name,
                                            connections['server'][0]['persistent'],
                                            self.server_test_to_pod_type(test_id, connections['server'][0]['type']))
                            c = IperfClient(self._tft, s, index, node_client_name,
                                            self.client_test_to_pod_type(test_id, connections['client'][0]['type']))
                            servers.append(s)
                            clients.append(c)
                        for plugins in connections['plugins']:
                            if plugins['name'] == "measure_cpu":
                                s = MeasureCPU(self._tft, node_server_name)
                                c = MeasureCPU(self._tft, node_client_name)
                                monitors.append(s)
                                monitors.append(c)
                            if plugins['name'] == "measure_power":
                                s = MeasurePower(self._tft, node_server_name)
                                c = MeasurePower(self._tft, node_client_name)
                                monitors.append(s)
                                monitors.append(c)
        """

        for test_id in range(1, 25):
            servers = []
            clients = []
            monitors = []

            self.cleanup_previous_pods("default")
            self.configure_namespace("default")
            duration = 10
            logger.info(f"Running for {duration} seconds")

            ### Set in Configuration Reading Loop ###
            node_server_name = "worker-236"
            node_client_name = "worker-235"
            index = 0
            pod_type = "sriov"
            ###################

            self.test_settings = TestSettings(
                test_case_id=test_id,
                node_server_name=node_server_name,
                node_client_name=node_client_name,
                server_pod_type=pod_type,
                client_pod_type=pod_type
            )
            s, c = self.create_iperf_server_client(self.test_settings)

            servers.append(s)
            clients.append(c)

            #self.measure_cpu(node_server_name, node_client_name, True)
            #self.measure_power(node_server_name, node_client_name, True)

            for tasks in servers + clients + self.monitors:
                tasks.setup()

            for tasks in servers + clients + self.monitors:
                tasks.run(duration)

            for tasks in servers + clients + self.monitors:
                tasks.stop()
