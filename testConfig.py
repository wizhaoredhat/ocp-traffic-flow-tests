import host
import sys
from enum import Enum
from logger import logger
from k8sClient import K8sClient
from yaml import safe_load
import io
from common import TestType, TestCaseType, enum_convert, PodType
from typing import List, Dict


class ClusterMode(Enum):
    SINGLE = 1
    DPU = 3


class TestConfig:
    kubeconfig_tenant: str = "/root/kubeconfig.tenantcluster"
    kubeconfig_infra: str = "/root/kubeconfig.infracluster"
    kubeconfig_single: str = "/root/kubeconfig.nicmodecluster"
    kubeconfig_cx: str = "/root/kubeconfig.smartniccluster"
    mode: ClusterMode = ClusterMode.SINGLE
    client_tenant: K8sClient
    client_infra: K8sClient
    full_config: dict

    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            contents = f.read()
            self.full_config = safe_load(io.StringIO(contents))

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

    def parse_test_cases(self, input_str: str) -> List[TestCaseType]:
        output: List[TestCaseType] = []
        parts = input_str.split(",")

        for part in parts:
            part = part.strip()
            if part:
                if not part.isdigit() and "-" not in part:
                    raise ValueError(f"Invalid test case id: {part}")

                if "-" in part:
                    try:
                        start, end = map(int, part.split("-"))
                        output.extend(
                            [
                                enum_convert(TestCaseType, i)
                                for i in range(start, end + 1)
                            ]
                        )
                    except ValueError:
                        raise ValueError(f"Invalid test case id: {part}")
                else:
                    output.append(enum_convert(TestCaseType, int(part)))

        return output

    def pod_type_to_enum(self, connection_server: Dict[str, str]) -> PodType:
        if "sriov" in connection_server:
            if "true" in connection_server["sriov"].lower():
                return PodType.SRIOV
        return PodType.NORMAL

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
        return self.full_config["tft"]
