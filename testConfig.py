import host
import sys
from enum import Enum
from logger import logger
from k8sClient import K8sClient
from yaml import safe_load
import io
import common
from common import TestType, TestCaseType, PodType
from typing import Any
from typing import Mapping
import typing


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
    full_config: dict[str, Any]

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

    @staticmethod
    def parse_test_cases(input_str: str) -> list[TestCaseType]:
        return common.enum_convert_list(TestCaseType, input_str)

    def pod_type_from_config(self, connection_server: dict[str, str]) -> PodType:
        if "sriov" in connection_server:
            if "true" in connection_server["sriov"].lower():
                return PodType.SRIOV
        return PodType.NORMAL

    def default_network_from_config(self, connection: dict[str, str]) -> str:
        if "default-network" in connection:
            return connection["default-network"]
        return "default/default"

    @staticmethod
    def validate_test_type(connection: Mapping[str, Any]) -> TestType:
        input_ct = connection.get("type")
        try:
            return common.enum_convert(TestType, input_ct, default=TestType.IPERF_TCP)
        except Exception:
            raise ValueError(
                f"Invalid connection type {input_ct} provided. Supported connection types: iperf-tcp (default), iperf-udp, http"
            )

    def GetConfig(self) -> list[dict[str, Any]]:
        return typing.cast(list[dict[str, Any]], self.full_config["tft"])
