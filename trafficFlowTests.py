import common
from common import PodType
from testConfig import TestConfig
from logger import logger
from iperf import IperfServer
from iperf import IperfClient
from measureCpu import MeasureCPU
from measurePower import MeasurePower
from enum import Enum
import sys


class TestCaseType(Enum):
    POD_TO_POD_SAME_NODE                 = 1
    POD_TO_POD_DIFF_NODE                 = 2
    POD_TO_HOST_SAME_NODE                = 3
    POD_TO_HOST_DIFF_NODE                = 4
    POD_TO_CLUSTER_IP_TO_POD_SAME_NODE   = 5
    POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE   = 6
    POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE  = 7
    POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE  = 8
    POD_TO_NODE_PORT_TO_POD_SAME_NODE    = 9
    POD_TO_NODE_PORT_TO_POD_DIFF_NODE    = 10
    POD_TO_NODE_PORT_TO_HOST_SAME_NODE   = 11
    POD_TO_NODE_PORT_TO_HOST_DIFF_NODE   = 12
    HOST_TO_HOST_SAME_NODE               = 13
    HOST_TO_HOST_DIFF_NODE               = 14
    HOST_TO_POD_SAME_NODE                = 15
    HOST_TO_POD_DIFF_NODE                = 16
    HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE  = 17
    HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE  = 18
    HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE = 19
    HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE = 20
    HOST_TO_NODE_PORT_TO_POD_SAME_NODE   = 21
    HOST_TO_NODE_PORT_TO_POD_DIFF_NODE   = 22
    HOST_TO_NODE_PORT_TO_HOST_SAME_NODE  = 23
    HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE  = 24
    POD_TO_EXTERNAL                      = 25
    HOST_TO_EXTERNAL                     = 26


class TrafficFlowTests():
    def __init__(self, tft: TestConfig):
        self._tft = tft
        self.monitors = []

    def create_iperf_server_client(self, sriov: bool, test_case: TestCaseType, node_server_name: str, node_client_name: str) -> (IperfServer, IperfClient):
        server_pod_type = PodType.NORMAL
        client_pod_type = PodType.NORMAL
        if sriov:
            server_pod_type = PodType.SRIOV
            client_pod_type = PodType.SRIOV

        if test_case == TestCaseType.POD_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_CLUSTER_IP_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_NODE_PORT_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_NODE_PORT_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_NODE_PORT_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.POD_TO_NODE_PORT_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_NODE_PORT_TO_POD_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_NODE_PORT_TO_POD_DIFF_NODE:
            pass
        elif test_case == TestCaseType.HOST_TO_NODE_PORT_TO_HOST_SAME_NODE:
            node_client_name = node_server_name
        elif test_case == TestCaseType.HOST_TO_NODE_PORT_TO_HOST_DIFF_NODE:
            pass
        elif test_case == TestCaseType.POD_TO_EXTERNAL:
            pass
        elif test_case == TestCaseType.HOST_TO_EXTERNAL:
            pass

        s = IperfServer(self._tft, 0, node_server_name, False, server_pod_type, True)
        c = IperfClient(self._tft, s, 0, node_client_name, client_pod_type, True)
        return (s, c)

    def server_test_to_pod_type(self, test_id: int, cfg_pod_type: str) -> PodType:
        pod_type = PodType.NORMAL
        if cfg_pod_type == "sriov":
            pod_type = PodType.SRIOV

        if test_id in (4, 6, 10, 12):
            pod_type = PodType.HOSTBACKED

        return pod_type

    def client_test_to_pod_type(self, test_id: int, cfg_pod_type: str) -> PodType:
        pod_type = PodType.NORMAL
        if cfg_pod_type == "sriov":
            pod_type = PodType.SRIOV

        if test_id in (9, 10, 11, 12):
            pod_type = PodType.HOSTBACKED

        return pod_type

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
        servers = []
        clients = []
        monitors = []
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

        #self.cleanup_previous_pods("default")
        self.configure_namespace("default")
        duration = 10
        logger.info(f"Running for {duration} seconds")

        node_server_name = "worker-advnetlab23"
        node_client_name = "worker-advnetlab24"
        index = 0

        s, c = self.create_iperf_server_client(True, TestCaseType.POD_TO_POD_DIFF_NODE, node_server_name, node_client_name)
        #s = IperfServer(self._tft, index, node_server_name, "false", self.server_test_to_pod_type(1, "sriov"), True)
        #c = IperfClient(self._tft, s, index, node_client_name, self.client_test_to_pod_type(1, "sriov"), True)
        servers.append(s)
        clients.append(c)

        self.measure_cpu(node_server_name, node_client_name, True)
        self.measure_power(node_server_name, node_client_name, True)

        for tasks in servers + clients + self.monitors:
            tasks.setup()

        for tasks in servers + clients + self.monitors:
            tasks.run(duration)

        for tasks in servers + clients + self.monitors:
            tasks.stop()
