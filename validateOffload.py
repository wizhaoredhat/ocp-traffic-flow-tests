from common import (
    TFT_TOOLS_IMG,
    PluginOutput,
    j2_render,
    TftAggregateOutput,
    PodType,
    Result,
)
from logger import logger
import time
from testConfig import TestConfig
from iperf import IperfServer, IperfClient
from thread import ReturnValueThread
from task import Task
from typing import Optional, Union
import sys
import json


class ValidateOffload(Task):
    def __init__(
        self,
        tft: TestConfig,
        iperf_instance: Union[IperfServer, IperfClient],
        tenant: bool,
    ):
        super().__init__(tft, 0, iperf_instance.node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = (
            f"./manifests/yamls/tools-pod-{self.node_name}-validate-offload.yaml"
        )
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-validate-offload"
        self.template_args["test_image"] = TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]
        self._iperf_instance = iperf_instance
        self.iperf_pod_name = iperf_instance.pod_name
        self.iperf_pod_type = iperf_instance.pod_type

        j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def extract_vf_rep(self) -> str:
        if self.iperf_pod_type == PodType.HOSTBACKED:
            logger.info(f"The VF representor is: ovn-k8s-mp0")
            return "ovn-k8s-mp0"

        self.get_vf_rep_cmd = f'exec -n default {self.pod_name} -- /bin/sh -c "crictl --runtime-endpoint=/host/run/crio/crio.sock ps -a --name={self.iperf_pod_name} -o json "'
        r = self.run_oc(self.get_vf_rep_cmd)

        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.info(r)
                sys.exit(-1)

        vf_rep_json = r.out
        data = json.loads(vf_rep_json)
        logger.info(
            f"The VF representor is: %s" % data["containers"][0]["podSandboxId"][:15]
        )
        return data["containers"][0]["podSandboxId"][:15]

    def run_ethtool_cmd(self, vf_rep: str) -> Result:
        self.ethtool_cmd = (
            f'exec -n default {self.pod_name} -- /bin/sh -c "ethtool -S {vf_rep}"'
        )
        r = self.run_oc(self.ethtool_cmd)
        if self.iperf_pod_type != PodType.HOSTBACKED:
            if r.returncode != 0:
                if "already exists" not in r.err:
                    logger.info(r)
                    raise RuntimeError(
                        f"ValidateOffload error: {r.err} returncode: {r.returncode}"
                    )

        return r

    def parse_out_packet(self, output: str, prefix: str) -> Optional[int]:
        for line in output.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith(prefix):
                return int(stripped_line.split(":")[1])

        return None

    def run_st(self) -> Result:
        vf_rep = self.extract_vf_rep()
        r1 = self.run_ethtool_cmd(vf_rep)
        time.sleep(self._duration)
        r2 = self.run_ethtool_cmd(vf_rep)

        combined_out = f"{r1.out}--DELIMIT--{r2.out}"
        combined_err = f"R1: {r1.err} R2: {r2.err}"
        combined_returncode = max(r1.returncode, r2.returncode)

        return Result(
            out=combined_out, err=combined_err, returncode=combined_returncode
        )

    def run(self, duration: int) -> None:
        self.exec_thread = ReturnValueThread(target=self.run_st)
        self._duration = int(duration)
        self.exec_thread.start()

    def output(self, out: TftAggregateOutput):
        out.plugins.append(self._output)

        if self.iperf_pod_type == PodType.HOSTBACKED:
            if isinstance(self._iperf_instance, IperfClient):
                logger.info(f"The client VF representor ovn-k8s-mp0_0 does not exist")
            else:
                logger.info(f"The server VF representor ovn-k8s-mp0_0 does not exist")

    def generate_output(self, data: str) -> PluginOutput:
        split_data = data.split("--DELIMIT--")
        parsed_data = {}

        if len(split_data) >= 1:
            parsed_data["rx_start"] = self.parse_out_packet(split_data[0], "rx_packet")
            parsed_data["tx_start"] = self.parse_out_packet(split_data[0], "tx_packet")

        if len(split_data) >= 2:
            parsed_data["rx_end"] = self.parse_out_packet(split_data[1], "rx_packet")
            parsed_data["tx_end"] = self.parse_out_packet(split_data[1], "tx_packet")

        if len(split_data) >= 3:
            parsed_data["additional_info"] = "--DELIMIT--".join(split_data[2:])

        logger.info(
            f"rx_packet_start: {parsed_data.get('rx_start', 'N/A')}\n"
            f"tx_packet_start: {parsed_data.get('tx_start', 'N/A')}\n"
            f"rx_packet_end: {parsed_data.get('rx_end', 'N/A')}\n"
            f"tx_packet_end: {parsed_data.get('tx_end', 'N/A')}\n"
        )
        return PluginOutput(
            command=self.ethtool_cmd,
            plugin_metadata={
                "name": "GetEthtoolStats",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            result=parsed_data,
            name="get_ethtool_stats",
        )
