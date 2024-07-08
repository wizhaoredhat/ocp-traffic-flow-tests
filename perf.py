import abc
import sys
import time

from typing import Optional

import tftbase

from logger import logger
from task import Task
from task import TaskOperation
from testSettings import TestSettings
from tftbase import BaseOutput
from tftbase import ConnectionMode
from tftbase import PodType


EXTERNAL_PERF_SERVER = "external-perf-server"


class PerfServer(Task, abc.ABC):
    def __init__(self, ts: TestSettings):
        super().__init__(ts, ts.server_index, ts.node_server_name, ts.server_is_tenant)

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

        assert (self.in_file_template == "") == (self.out_file_yaml == "")

        if self.in_file_template != "":
            self.render_file("Server Pod Yaml")

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

        self.ts.event_server_alive.set()

    @abc.abstractmethod
    def _create_setup_operation_get_thread_action_cmd(self) -> str:
        pass

    @abc.abstractmethod
    def _create_setup_operation_get_cancel_action_cmd(self) -> str:
        pass

    def _create_setup_operation(self) -> Optional[TaskOperation]:
        # We don't chain up super()._create_setup_operation(). Depending on
        # the connection_mode we call setup_pod().

        th_cmd = self._create_setup_operation_get_thread_action_cmd()

        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            cmd = f"podman run -it --init --replace --rm -p {self.port} --name={self.pod_name} {tftbase.get_tft_test_image()} {th_cmd}"
            cancel_cmd = f"podman rm --force {self.pod_name}"
        else:
            self.setup_pod()
            ca_cmd = self._create_setup_operation_get_cancel_action_cmd()
            cmd = f"{th_cmd}"
            cancel_cmd = f"{ca_cmd}"

        logger.info(f"Running {cmd}")

        def _run_cmd(cmd: str, *, ignore_failure: bool) -> BaseOutput:
            force_success: Optional[bool] = None
            if ignore_failure:
                # We ignore the exit code of the command, that is because this is
                # commonly a long running process that needs to get killed with the
                # "cancel_action".  In that case, the exit code will be non-zero, but
                # it's the normal termination of the command. Suppress such "failures".
                force_success = True

            if self.connection_mode == ConnectionMode.EXTERNAL_IP:
                return BaseOutput.from_cmd(self.lh.run(cmd), success=force_success)
            if self.exec_persistent:
                return BaseOutput(msg="Server is persistent")
            return BaseOutput.from_cmd(
                self.run_oc_exec(cmd, may_fail=ignore_failure),
                success=force_success,
            )

        def _thread_action() -> BaseOutput:
            return _run_cmd(cmd, ignore_failure=True)

        def _cancel_action() -> None:
            _run_cmd(cancel_cmd, ignore_failure=False)

        return TaskOperation(
            log_name=self.log_name_setup,
            thread_action=_thread_action,
            wait_ready=lambda: self.confirm_server_alive(),
            cancel_action=_cancel_action,
        )


class PerfClient(Task, abc.ABC):
    def __init__(self, ts: TestSettings, server: PerfServer):
        super().__init__(ts, ts.client_index, ts.conf_client.name, ts.client_is_tenant)

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
        self.reverse = ts.reverse
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
        self.render_file("Client Pod Yaml")

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
