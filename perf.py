import sys
import time

import common
import tftbase

from logger import logger
from syncManager import SyncManager
from task import Task
from testConfig import TestConfig
from testSettings import TestSettings
from tftbase import ConnectionMode
from tftbase import PodType


EXTERNAL_PERF_SERVER = "external-perf-server"


class PerfServer(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings):
        super().__init__(tc, ts.server_index, ts.node_server_name, ts.server_is_tenant)

        connection_mode = ts.connection_mode
        pod_type = ts.server_pod_type
        node_name = self.node_name
        port = 5201 + self.index

        if connection_mode == ConnectionMode.EXTERNAL_IP:
            in_file_template = ""
            out_file_yaml = ""
            pod_name = EXTERNAL_PERF_SERVER
        elif pod_type == PodType.SRIOV:
            in_file_template = "./manifests/sriov-pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/sriov-pod-{node_name}-server.yaml"
            pod_name = f"sriov-pod-{node_name}-server-{port}"
        elif pod_type == PodType.NORMAL:
            in_file_template = "./manifests/pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/pod-{node_name}-server.yaml"
            pod_name = f"normal-pod-{node_name}-server-{port}"
        elif pod_type == PodType.HOSTBACKED:
            in_file_template = "./manifests/host-pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/host-pod-{node_name}-server.yaml"
            pod_name = f"host-pod-{node_name}-server-{port}"
        else:
            raise ValueError("Invalid pod_type {pod_type}")

        self.exec_persistent = ts.conf_server.persistent
        self.port = port
        self.pod_type = pod_type
        self.connection_mode = ts.connection_mode
        self.ts = ts
        self.in_file_template = in_file_template
        self.out_file_yaml = out_file_yaml
        self.pod_name = pod_name

    def get_template_args(self) -> dict[str, str]:

        extra_args: dict[str, str] = {}
        if self.connection_mode != ConnectionMode.EXTERNAL_IP:
            extra_args["pod_name"] = self.pod_name
            extra_args["port"] = f"{self.port}"

        return {
            **super().get_template_args(),
            "default_network": self.ts.conf_server.default_network,
            **extra_args,
        }

    def initialize(self) -> None:
        super().initialize()
        common.j2_render(
            self.in_file_template, self.out_file_yaml, self.get_template_args()
        )
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

        self.cluster_ip_addr = self.create_cluster_ip_service()
        self.nodeport_ip_addr = self.create_node_port_service(self.port + 25000)

    def confirm_server_alive(self) -> None:
        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            # Podman scenario
            end_time = time.monotonic() + 60
            while time.monotonic() < end_time:
                r = self.lh.run(
                    f"podman ps --filter status=running --filter name={self.pod_name} --format '{{{{.Names}}}}'"
                )
                if self.pod_name in r.out:
                    break
                time.sleep(5)
        else:
            # Kubernetes/OpenShift scenario
            r = self.run_oc(
                f"wait --for=condition=ready pod/{self.pod_name} --timeout=1m"
            )
        if not r or r.returncode != 0:
            logger.error(f"Failed to start server: {r.err}")
            sys.exit(-1)
        SyncManager.set_server_alive()

    def run(self, duration: int) -> None:
        pass

    def output(self, out: tftbase.TftAggregateOutput) -> None:
        pass

    def generate_output(self, data: str) -> tftbase.BaseOutput:
        return tftbase.BaseOutput("", {})


class PerfClient(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings, server: PerfServer):
        super().__init__(tc, ts.client_index, ts.conf_client.name, ts.client_is_tenant)

        pod_type = ts.client_pod_type
        node_name = self.node_name
        port = server.port

        if pod_type == PodType.SRIOV:
            in_file_template = "./manifests/sriov-pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/sriov-pod-{node_name}-client.yaml"
            pod_name = f"sriov-pod-{node_name}-client-{port}"
        elif pod_type == PodType.NORMAL:
            in_file_template = "./manifests/pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/pod-{node_name}-client.yaml"
            pod_name = f"normal-pod-{node_name}-client-{port}"
        elif pod_type == PodType.HOSTBACKED:
            in_file_template = "./manifests/host-pod.yaml.j2"
            out_file_yaml = f"./manifests/yamls/host-pod-{node_name}-client.yaml"
            pod_name = f"host-pod-{node_name}-client-{port}"
        else:
            raise ValueError("Invalid pod_type {pod_type}")

        self.server = server
        self.port = port
        self.pod_type = pod_type
        self.connection_mode = ts.connection_mode
        self.test_type = ts.connection.test_type
        self.test_case_id = ts.test_case_id
        self.ts = ts
        self.reverse = ts.reverse
        self.cmd = ""
        self.in_file_template = in_file_template
        self.out_file_yaml = out_file_yaml
        self.pod_name = pod_name

    def get_template_args(self) -> dict[str, str]:
        return {
            **super().get_template_args(),
            "default_network": self.ts.conf_client.default_network,
            "pod_name": self.pod_name,
        }

    def initialize(self) -> None:
        super().initialize()
        common.j2_render(
            self.in_file_template, self.out_file_yaml, self.get_template_args()
        )
        logger.info(f"Generated Client Pod Yaml {self.out_file_yaml}")

    def get_target_ip(self) -> str:
        if self.connection_mode == ConnectionMode.CLUSTER_IP:
            logger.debug(
                f"get_target_ip() ClusterIP connection to {self.server.cluster_ip_addr}"
            )
            return self.server.cluster_ip_addr
        elif self.connection_mode == ConnectionMode.NODE_PORT_IP:
            logger.debug(
                f"get_target_ip() NodePortIP connection to {self.server.nodeport_ip_addr}"
            )
            return self.server.nodeport_ip_addr
        elif self.connection_mode == ConnectionMode.EXTERNAL_IP:
            external_pod_ip = self.get_podman_ip(self.server.pod_name)
            logger.debug(f"get_target_ip() External connection to {external_pod_ip}")
            return external_pod_ip
        server_ip = self.server.get_pod_ip()
        logger.debug(f"get_target_ip() Connection to server at {server_ip}")
        return server_ip

    def get_podman_ip(self, pod_name: str) -> str:
        cmd = "podman inspect --format '{{.NetworkSettings.IPAddress}}' " + pod_name

        for _ in range(5):
            ret = self.lh.run(cmd)
            if ret.returncode == 0:
                ip_address = ret.out.strip()
                if ip_address:
                    logger.debug(f"get_podman_ip({pod_name}) found: {ip_address}")
                    return ip_address

            time.sleep(2)

        raise Exception(
            f"get_podman_ip(): failed to get {pod_name} ip after 5 attempts"
        )
