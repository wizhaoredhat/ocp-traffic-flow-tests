import host
import sys
from enum import Enum
from logger import logger
from k8sClient import K8sClient
from yaml import safe_load
import io
from common import TestType


class ClusterMode(Enum):
    SINGLE = 1
    DPU = 3


class TestConfig:
    def __init__(self, config_path: str):
        self.mode = ClusterMode.SINGLE

        with open(config_path, "r") as f:
            contents = f.read()
            self.fullConfig = safe_load(io.StringIO(contents))

        self.kubeconfig_tenant = "/root/kubeconfig.tenantcluster"
        self.kubeconfig_infra = "/root/kubeconfig.infracluster"
        self.kubeconfig_single = "/root/kubeconfig.nicmodecluster"
        self.kubeconfig_cx = "/root/kubeconfig.smartniccluster"
        self.client_tenant = None
        self.client_infra = None
        self.server_node = None
        self.client_node = None

        lh = host.LocalHost()

        # Find out what type of cluster are we in.
        if lh.file_exists(self.kubeconfig_single):
            self.mode = ClusterMode.SINGLE
            self.client_tenant = K8sClient(self.kubeconfig_single)
        elif lh.file_exists(self.kubeconfig_cx):
            self.mode = ClusterMode.SINGLE
            self.client_tenant = K8sClient(self.kubeconfig_cx)
        elif lh.file_exists(self.kubeconfig_tenant):
            if lh.file_exists(self.kubeconfig_infra):
                self.mode = ClusterMode.DPU
                self.client_tenant = K8sClient(self.kubeconfig_tenant)
                self.client_infra = K8sClient(self.kubeconfig_infra)
            else:
                logger.error(
                    "Assuming DPU...Cannot Find Infrastructure Cluster Config."
                )
                sys.exit(-1)
        else:
            logger.error("Cannot Find Kubeconfig.")
            sys.exit(-1)

        logger.info(self.GetConfig())

    def parse_test_cases(self, input_str: str):
        output = []
        parts = input_str.split(",")

        for part in parts:
            part = part.strip()
            if part:
                if not part.isdigit() and "-" not in part:
                    raise ValueError(f"Invalid test case id: {part}")

                if "-" in part:
                    try:
                        start, end = map(int, part.split("-"))
                        output.extend(range(start, end + 1))
                    except ValueError:
                        raise ValueError(f"Invalid test case id: {part}")
                else:
                    output.append(int(part))

        return output

    def validate_pod_type(self, connection_server: dict):
        if "sriov" in connection_server:
            if "true" in connection_server["sriov"].lower():
                return "sriov"
        return "normal"

    def validate_test_type(self, connection: dict) -> TestType:
        if "type" not in connection:
            return TestType.IPERF_TCP

        input_ct = connection["type"].lower()
        if "iperf" in input_ct:
            if "udp" in input_ct:
                return TestType.IPERF_UDP
            else:
                return TestType.IPERF_TCP
        elif "http" in input_ct:
            return TestType.HTTP
        else:
            raise ValueError(
                f"Invalid connection type {connection['type']} provided. \
                Supported connection types: iperf-tcp (default), iperf-udp, http"
            )

    def GetConfig(self) -> dict:
        return self.fullConfig["tft"]
