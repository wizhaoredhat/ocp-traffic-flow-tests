import common
from common import PodType, ConnectionMode, TestType, IperfOutput
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from common import Result
from testSettings import TestSettings
import json
import time
from syncManager import SyncManager
import sys

EXTERNAL_PERF_SERVER = "external-perf-server"


class PerfServer(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings):
        Task.__init__(
            self, tc, ts.server_index, ts.node_server_name, ts.server_is_tenant
        )
        self.exec_persistent = ts.server_is_persistent
        self.port = 5201 + self.index
        self.pod_type = ts.server_pod_type
        self.connection_mode = ts.connection_mode

        self.template_args["default_network"] = ts.server_default_network
        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            self.pod_name = EXTERNAL_PERF_SERVER
            return
        if self.pod_type == PodType.SRIOV:
            self.in_file_template = "./manifests/sriov-pod.yaml.j2"
            self.out_file_yaml = (
                f"./manifests/yamls/sriov-pod-{self.node_name}-server.yaml"
            )
            self.template_args["pod_name"] = (
                f"sriov-pod-{self.node_name}-server-{self.port}"
            )
        elif self.pod_type == PodType.NORMAL:
            self.in_file_template = "./manifests/pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/pod-{self.node_name}-server.yaml"
            self.template_args["pod_name"] = (
                f"normal-pod-{self.node_name}-server-{self.port}"
            )
        elif self.pod_type == PodType.HOSTBACKED:
            self.in_file_template = "./manifests/host-pod.yaml.j2"
            self.out_file_yaml = (
                f"./manifests/yamls/host-pod-{self.node_name}-server.yaml"
            )
            self.template_args["pod_name"] = (
                f"host-pod-{self.node_name}-server-{self.port}"
            )

        self.template_args["port"] = f"{self.port}"

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
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

    def output(self, out: common.TftAggregateOutput) -> None:
        pass

    def generate_output(self, data: str) -> common.BaseOutput:
        return common.BaseOutput("", {})


class PerfClient(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings, server: PerfServer):
        Task.__init__(
            self, tc, ts.client_index, ts.node_client_name, ts.client_is_tenant
        )
        self.server = server
        self.port = self.server.port
        self.pod_type = ts.client_pod_type
        self.connection_mode = ts.connection_mode
        self.test_type = ts.test_type
        self.test_case_id = ts.test_case_id
        self.ts = ts
        self.reverse = ts.reverse
        self.cmd = ""

        self.template_args["default_network"] = ts.client_default_network
        if self.pod_type == PodType.SRIOV:
            self.in_file_template = "./manifests/sriov-pod.yaml.j2"
            self.out_file_yaml = (
                f"./manifests/yamls/sriov-pod-{self.node_name}-client.yaml"
            )
            self.template_args["pod_name"] = (
                f"sriov-pod-{self.node_name}-client-{self.port}"
            )
        elif self.pod_type == PodType.NORMAL:
            self.in_file_template = "./manifests/pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/pod-{self.node_name}-client.yaml"
            self.template_args["pod_name"] = (
                f"normal-pod-{self.node_name}-client-{self.port}"
            )
        elif self.pod_type == PodType.HOSTBACKED:
            self.in_file_template = "./manifests/host-pod.yaml.j2"
            self.out_file_yaml = (
                f"./manifests/yamls/host-pod-{self.node_name}-client.yaml"
            )
            self.template_args["pod_name"] = (
                f"host-pod-{self.node_name}-client-{self.port}"
            )

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
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
