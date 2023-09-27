import common
from common import PodType, ConnectionMode, TestType, IperfOutput
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from host import Result
from testSettings import TestSettings
from dataclasses import asdict
import sys
import yaml
import json

IPERF_EXE = "iperf3"
IPERF_UDP_OPT = "-u -b 25G"
IPERF_REV_OPT = "-R"
EXTERNAL_IPERF3_SERVER = "external-iperf3-server"

# Finishing switching iperf data handling to dataclass


class IperfServer(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings):
        super().__init__(tc, ts.server_index, ts.node_server_name, ts.server_is_tenant)
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
            logger.error(f"Error occured while stopping Iperf server: errcode: {r.returncode} err {r.err}")
        logger.debug(f"IperfServer.stop(): {r.out}")

    def output(self, out: common.TftAggregateOutput):
        pass

class IperfClient(Task):
    def __init__(self, tc: TestConfig, ts: TestSettings, server: IperfServer):
        super().__init__(tc, ts.client_index, ts.node_client_name, ts.client_is_tenant)
        self.server = server
        self.port = self.server.port
        self.pod_type = ts.client_pod_type
        self.connection_mode = ts.connection_mode
        self.test_type = ts.test_type
        self.test_case_id = ts.test_case_id
        self.ts = ts
        self.reverse = ts.reverse
        self.cmd = ""

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
        self.cmd = f"exec -t {self.pod_name} -- {IPERF_EXE} -c {server_ip} -p {self.port} --json -t {duration}"
        if self.test_type == TestType.IPERF_UDP:
            self.cmd = f" {self.cmd} {IPERF_UDP_OPT}"
        if self.reverse:
            self.cmd = f" {self.cmd} {IPERF_REV_OPT}"
        self.exec_thread = ReturnValueThread(target=client, args=(self, self.cmd))
        self.exec_thread.start()

    def stop(self):
        logger.info(f"Stopping execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.error(r)
        logger.debug(f"IperfClient.stop(): {r.out}")
        data = json.loads(r.out)
        self._output = self.generate_output(data)

    def generate_output(self, data: dict) -> IperfOutput:
        json_dump = IperfOutput(
            tft_metadata=self.ts.get_test_metadata(),
            command=self.cmd,
            result=data,
        )
        return json_dump

    def output(self, out: common.TftAggregateOutput):
        # Return machine-readable output to top level
        out.flow_test = self._output

        # Print summary to console logs
        logger.info(f"Results of {self.ts.get_test_str()}:")
        if self.iperf_error_occured(self._output.result):
            logger.error("Encountered error while running test:\n"
                f"  {self._output.result['error']}"
            )
            return
        if self.test_type == TestType.IPERF_TCP:
            self.print_tcp_results(self._output.result)
        if self.test_type == TestType.IPERF_UDP:
            self.print_udp_results(self._output.result)     

    def print_tcp_results(self, data: dict):
        sum_sent = data["end"]["sum_sent"]
        sum_received = data["end"]["sum_received"]

        transfer_sent = sum_sent["bytes"] / (1024 ** 3)
        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        transfer_received = sum_received["bytes"] / (1024 ** 3)
        bitrate_received = sum_received["bits_per_second"] / 1e9
        mss = data['start']['tcp_mss_default']

        logger.info(
            f"\n  [ ID]   Interval              Transfer        Bitrate\n"
            f"  [SENT]   0.00-{sum_sent['seconds']:.2f} sec   {transfer_sent:.2f} GBytes  {bitrate_sent:.2f} Gbits/sec sender\n"
            f"  [REC]   0.00-{sum_received['seconds']:.2f} sec   {transfer_received:.2f} GBytes  {bitrate_received:.2f} Gbits/sec receiver\n"
            f"  MSS = {mss}"
        )

    def print_udp_results(self, data: dict):
        sum_data = data["end"]["sum"]

        total_gigabytes = sum_data["bytes"] / (1024 ** 3)
        average_gigabitrate = sum_data["bits_per_second"] / 1e9
        average_jitter = sum_data["jitter_ms"]
        total_lost_packets = sum_data["lost_packets"]
        total_lost_percent = sum_data["lost_percent"]

        logger.info(
            f"\n  Total GBytes: {total_gigabytes:.4f} GBytes\n"
            f"  Average Bitrate: {average_gigabitrate:.2f} Gbits/s\n"
            f"  Average Jitter: {average_jitter:.9f} ms\n"
            f"  Total Lost Packets: {total_lost_packets}\n"
            f"  Total Lost Percent: {total_lost_percent:.2f}%"
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
        logger.debug(f"get_podman_ip(): {ret.out}")
        if ret.returncode != 0:
            logger.error(f"Failed to inspect pod {pod_name} for IPAddress: {ret.err}")
            raise Exception(f"get_podman_ip(): failed to get podman ip")
        return ret.out.strip()

    def iperf_error_occured(self, data: dict) -> bool:
        return "error" in data
