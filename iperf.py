import common
from common import PodType, ConnectionMode, TestType
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from host import Result
from testSettings import TestSettings
import sys
import yaml
import json

IPERF_EXE = "iperf3"
IPERF_UDP_OPT = "-u -b 25G"
IPERF_REV_OPT = "-R"
EXTERNAL_IPERF3_SERVER = "external-iperf3-server"

class IperfServer(Task):
    def __init__(self, tft: TestConfig, ts: TestSettings):
        super().__init__(tft, ts.server_index, ts.node_server_name, ts.server_is_tenant)
        self.exec_persistent = ts.server_is_persistent
        self.port = 5201 + self.index
        self.pod_type = ts.server_pod_type
        self.connection_mode = ts.connection_mode

        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            self.pod_name = EXTERNAL_IPERF3_SERVER
            return
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
            self.template_args["command"] = IPERF_EXE
            self.template_args["args"] = ["-s", "-p", f"{self.port}"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

        self.cluster_ip_addr = self.create_cluster_ip_service()
        self.nodeport_ip_addr = self.create_node_port_service(self.port + 25000)

    def setup(self):
        if self.connection_mode == ConnectionMode.EXTERNAL_IP:
            cmd = f"podman run -itd --rm -p {self.port} --entrypoint {IPERF_EXE} --name={self.pod_name} {common.FT_BASE_IMG} -s"
        else:
            # Create the server pods
            super().setup()
            cmd = f"exec -t {self.pod_name} -- {IPERF_EXE} -s -p {self.port} --one-off --json"
        
        logger.info(f"Running {cmd}")

        def server(self, cmd: str):
            if self.connection_mode == ConnectionMode.EXTERNAL_IP:
                return self.lh.run(cmd)
            elif self.exec_persistent:
                return Result("Server is persistent.", "", 0)
            return self.run_oc(cmd)

        self.exec_thread = ReturnValueThread(target=server, args=(self, cmd))
        self.exec_thread.start()

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
        self.test_type = ts.test_type

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
        cmd = f"exec -t {self.pod_name} -- {IPERF_EXE} -c {server_ip} -p {self.port} --json -t {duration}"
        if self.test_type == TestType.IPERF_UDP:
            cmd = f" {cmd} {IPERF_UDP_OPT}"
        self.exec_thread = ReturnValueThread(target=client, args=(self, cmd))
        self.exec_thread.start()

    def stop(self):
        logger.info(f"Stopping execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        data = json.loads(r.out)
        if self.test_type == TestType.IPERF_TCP:
            self.print_tcp_results(data)
        if self.test_type == TestType.IPERF_UDP:
            self.print_udp_results(data)
    
    def print_tcp_results(self, data: dict):
        mss = data['start']['tcp_mss_default']
        logger.info(f"MSS = {mss}")
        gbps = data['end']['sum_received']['bits_per_second']/1e9
        logger.info(f"GBPS = {gbps}")
    
    def print_udp_results(self, data: dict):
        sum_data = data["end"]["sum"]

        # Extracted values
        total_bytes = sum_data["bytes"]
        average_bitrate = sum_data["bits_per_second"]
        average_jitter = sum_data["jitter_ms"]
        total_lost_packets = sum_data["lost_packets"]
        total_lost_percent = sum_data["lost_percent"]

        # Print extracted information
        logger.info(
            f"Total Bytes: {total_bytes} bytes,"
            f" Average Bitrate: {average_bitrate:.2f} bits/s,"
            f" Average Jitter: {average_jitter:.9f} ms,"
            f" Total Lost Packets: {total_lost_packets},"
            f" Total Lost Percent: {total_lost_percent:.2f}%"
)
    def get_target_ip(self) -> str:
        if self.connection_mode == ConnectionMode.CLUSTER_IP:
            logger.debug(f"get_target_ip() ClusterIP connection to {self.server.cluster_ip_addr}")
            return self.server.cluster_ip_addr
        elif self.connection_mode == ConnectionMode.NODE_PORT_IP:
            logger.debug(f"get_target_ip() NodePortIP connection to {self.server.nodeport_ip_addr}")
            return self.server.nodeport_ip_addr
        elif self.connection_mode == ConnectionMode.EXTERNAL_IP:
            external_pod_ip = self.get_podman_ip(EXTERNAL_IPERF3_SERVER)
            logger.debug(f"get_target_ip() External connection to {external_pod_ip}")
            return external_pod_ip
        server_ip = self.server.get_pod_ip()
        logger.debug(f"get_target_ip() Connection to server at {server_ip}")
        return server_ip
    
    def get_podman_ip(self, pod_name: str) -> str:
        cmd = "podman inspect --format '{{.NetworkSettings.IPAddress}}' " + pod_name
        ret = self.lh.run(cmd)
        if ret.returncode != 0:
            logger.error(f"Failed to inspect pod {pod_name} for IPAddress: {ret.err}")
            sys.exit(-1)
        return ret.out.strip()


