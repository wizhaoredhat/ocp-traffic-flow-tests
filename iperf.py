import common
from common import PodType, ConnectionMode
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from host import Result
from testSettings import TestSettings
import sys
import yaml
import json


class IperfServer(Task):
    def __init__(self, tft: TestConfig, ts: TestSettings):
        super().__init__(tft, ts.server_index, ts.node_server_name, ts.server_is_tenant)
        self.exec_persistent = ts.server_is_persistent
        self.port = 5201 + self.index
        self.pod_type = ts.server_pod_type

        if self.pod_type == PodType.SRIOV:
            self.in_file_template = "./manifests/sriov-pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/sriov-pod-{self.node_name}-server.yaml"
            self.template_args["pod_name"] = f"sriov-pod-{self.node_name}-server-{self.port}"
        elif self.pod_type == PodType.NORMAL:
            self.in_file_template = "./manifests/pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/pod-{self.node_name}-server.yaml"
            self.template_args["pod_name"] = f"normal-pod-{self.node_name}-server-{self.port}"
        elif self.pod_type == PodType.HOSTBACKED:
            self.in_file_template = "./manifests/host-pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/host-pod-{self.node_name}-server.yaml"
            self.template_args["pod_name"] = f"host-pod-{self.node_name}-server-{self.port}"

        self.template_args["port"] = f"{self.port}"

        self.pod_name = self.template_args["pod_name"]

        if self.exec_persistent:
            self.template_args["command"] = "iperf3"
            self.template_args["args"] = ["-s", "-p", f"{self.port}"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

        self.cluster_ip_addr = self.create_cluster_ip_service()
        self.nodeport_ip_addr = self.create_node_port_service(self.port + 25000)

    def setup(self):
        super().setup()

        def server(self, cmd: str):
            if self.exec_persistent:
                return Result("Server is persistent.", "", 0)
            return self.run_oc(cmd)

        cmd = f"exec -t {self.pod_name} -- iperf3 -s -p {self.port} --one-off --json"
        self.exec_thread = ReturnValueThread(target=server, args=(self, cmd))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def run(self, duration: int):
        pass

    def stop(self):
        logger.info(f"Stopping execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        #logger.info(r.out)

class IperfClient(Task):
    def __init__(self, tft: TestConfig, ts: TestSettings, server: IperfServer):
        super().__init__(tft, ts.client_index, ts.node_client_name, ts.client_is_tenant)
        self.server = server
        self.port = self.server.port
        self.pod_type = ts.client_pod_type
        self.connection_mode = ts.connection_mode

        if self.pod_type  == PodType.SRIOV:
            self.in_file_template = "./manifests/sriov-pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/sriov-pod-{self.node_name}-client.yaml"
            self.template_args["pod_name"] = f"sriov-pod-{self.node_name}-client-{self.port}"
        elif self.pod_type  == PodType.NORMAL:
            self.in_file_template = "./manifests/pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/pod-{self.node_name}-client.yaml"
            self.template_args["pod_name"] = f"normal-pod-{self.node_name}-client-{self.port}"
        elif self.pod_type  == PodType.HOSTBACKED:
            self.in_file_template = "./manifests/host-pod.yaml.j2"
            self.out_file_yaml = f"./manifests/yamls/host-pod-{self.node_name}-client.yaml"
            self.template_args["pod_name"] = f"host-pod-{self.node_name}-client-{self.port}"

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Client Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int):
        def client(self, cmd: str):
            return self.run_oc(cmd)

        server_ip = self.get_target_ip()
        cmd = f"exec -t {self.pod_name} -- iperf3 -c {server_ip} -p {self.port} --json -t {duration}"
        self.exec_thread = ReturnValueThread(target=client, args=(self, cmd))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)

        data = json.loads(r.out)
        mss = data['start']['tcp_mss_default']
        logger.info(f"MSS = {mss}")
        gbps = data['end']['sum_received']['bits_per_second']/1e9
        logger.info(f"GBPS = {gbps}")
        #logger.info(r.out)

    def get_target_ip(self) -> str:
        if self.connection_mode == ConnectionMode.CLUSTER_IP:
            logger.debug(f"get_target_ip() ClusterIP connection to {self.server.cluster_ip_addr}")
            return self.server.cluster_ip_addr
        elif self.connection_mode == ConnectionMode.NODE_PORT_IP:
            logger.debug(f"get_target_ip() NodePortIP connection to {self.server.nodeport_ip_addr}")
            return self.server.nodeport_ip_addr
        elif self.connection_mode == ConnectionMode.EXTERNAL_IP:
            logger.error("Pod to External not yet supported")
            sys.exit(-1)
        server_ip = self.server.get_pod_ip()
        logger.debug(f"get_target_ip() Connection to server at {server_ip}")
        return server_ip
