import typing
import yaml

from typing import Any
from typing import Mapping
from typing import Optional

import common
import host

from k8sClient import K8sClient
from logger import logger
from tftbase import ClusterMode
from tftbase import PodType
from tftbase import TestCaseType
from tftbase import TestType


class TestConfig:
    kubeconfig_tenant: str = "/root/kubeconfig.tenantcluster"
    kubeconfig_infra: str = "/root/kubeconfig.infracluster"
    kubeconfig_single: str = "/root/kubeconfig.nicmodecluster"
    kubeconfig_cx: str = "/root/kubeconfig.smartniccluster"

    mode: ClusterMode
    full_config: dict[str, Any]
    kc_tenant: str
    kc_infra: Optional[str]
    _client_tenant: Optional[K8sClient]
    _client_infra: Optional[K8sClient]

    @staticmethod
    def _detect_mode_args() -> tuple[ClusterMode, str, Optional[str]]:

        # Find out what type of cluster are we in.

        mode = ClusterMode.SINGLE
        kc_tenant: str
        kc_infra: Optional[str] = None

        lh = host.LocalHost()
        if lh.file_exists(TestConfig.kubeconfig_single):
            kc_tenant = TestConfig.kubeconfig_single
        elif lh.file_exists(TestConfig.kubeconfig_cx):
            kc_tenant = TestConfig.kubeconfig_cx
        elif lh.file_exists(TestConfig.kubeconfig_tenant):
            if lh.file_exists(TestConfig.kubeconfig_infra):
                mode = ClusterMode.DPU
                kc_tenant = TestConfig.kubeconfig_tenant
                kc_infra = TestConfig.kubeconfig_infra
            else:
                raise RuntimeError(
                    "Assuming DPU...Cannot Find Infrastructure Cluster Config"
                )
        else:
            raise RuntimeError("Cannot Find Kubeconfig")

        return (mode, kc_tenant, kc_infra)

    def __init__(
        self,
        *,
        full_config: Optional[dict[str, Any]] = None,
        config_path: Optional[str] = None,
        mode_args: Optional[tuple[ClusterMode, str, Optional[str]]] = None,
    ) -> None:

        if config_path is not None:
            if full_config is not None:
                raise ValueError(
                    "Must either specify a full_config or a config_path argument"
                )
            with open(config_path, "r") as f:
                full_config = yaml.safe_load(f)

        if not isinstance(full_config, dict):
            raise ValueError(
                f"invalid config is not a dictionary but {type(full_config)}"
            )

        if any(not isinstance(k, str) for k in full_config):
            raise ValueError("The configuration must contain string keys only")

        if mode_args is None:
            mode_args = TestConfig._detect_mode_args()

        self.full_config = full_config

        self._client_tenant = None
        self._client_infra = None

        self.mode, self.kc_tenant, self.kc_infra = mode_args

        logger.info(self.GetConfig())

    def client(self, *, tenant: bool) -> K8sClient:
        if tenant:
            client = self._client_tenant
        else:
            if self.kc_infra is None:
                raise RuntimeError("TestConfig has no infra client")
            client = self._client_infra

        if client is not None:
            return client

        # Construct the K8sClient on first.

        if tenant:
            self._client_tenant = K8sClient(self.kc_tenant)
        else:
            assert self.kc_infra is not None
            self._client_infra = K8sClient(self.kc_infra)

        return self.client(tenant=tenant)

    @property
    def client_tenant(self) -> K8sClient:
        return self.client(tenant=True)

    @property
    def client_infra(self) -> K8sClient:
        return self.client(tenant=False)

    def GetConfig(self) -> list[dict[str, Any]]:
        return typing.cast(list[dict[str, Any]], self.full_config["tft"])

    @staticmethod
    def parse_test_cases(input_str: str) -> list[TestCaseType]:
        return common.enum_convert_list(TestCaseType, input_str)

    @staticmethod
    def pod_type_from_config(connection_server: dict[str, str]) -> PodType:
        if "sriov" in connection_server:
            if "true" in connection_server["sriov"].lower():
                return PodType.SRIOV
        return PodType.NORMAL

    @staticmethod
    def default_network_from_config(connection: dict[str, str]) -> str:
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
