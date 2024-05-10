from common import (
    TFT_TOOLS_IMG,
    PluginOutput,
    j2_render,
    TftAggregateOutput,
    PodType,
    Result,
)
from dataclasses import asdict, is_dataclass
from logger import logger
import time
from testConfig import TestConfig
from iperf import IperfServer, IperfClient, EXTERNAL_IPERF3_SERVER
from thread import ReturnValueThread
from task import Task
from typing import Optional, Union, Tuple
import sys
import json
from syncManager import SyncManager


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
        self.ethtool_cmd = ""

        j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def extract_vf_rep(self) -> str:
        if self.iperf_pod_type == PodType.HOSTBACKED:
            logger.info(f"The VF representor is: ovn-k8s-mp0")
            return "ovn-k8s-mp0"

        if self.iperf_pod_name == EXTERNAL_IPERF3_SERVER:
            logger.info(f"There is no VF on an external server")
            return "external"

        self.get_vf_rep_cmd = f'exec -n default {self.pod_name} -- /bin/sh -c "crictl --runtime-endpoint=unix:///host/run/crio/crio.sock ps -a --name={self.iperf_pod_name} -o json "'
        r = self.run_oc(self.get_vf_rep_cmd)

        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(f"Extract_vf_rep: {r.err}, {r.returncode}")

        vf_rep_json = r.out
        data = json.loads(vf_rep_json)
        logger.info(
            f"The VF representor is: {data['containers'][0]['podSandboxId'][:15]}"
        )
        return data["containers"][0]["podSandboxId"][:15]

    def run_ethtool_cmd(self, ethtool_cmd: str) -> Result:
        logger.info(f"Running {ethtool_cmd}")
        r = self.run_oc(ethtool_cmd)
        if self.iperf_pod_type != PodType.HOSTBACKED:
            if r.returncode != 0:
                if "already exists" not in r.err:
                    logger.error(f"Run_ethtool_cmd: {r.err}, {r.returncode}")
                    raise RuntimeError(
                        f"ValidateOffload error: {r.err} returncode: {r.returncode}"
                    )

        return r

    def parse_packets(self, output: str, packet_type: str) -> int:
        prefix = f"{packet_type}_packets"
        if prefix in output:
            for line in output.splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith(prefix):
                    return int(stripped_line.split(":")[1])
        total_packets = 0
        prefix = f"{packet_type}_queue_"
        packet_suffix = "_xdp_packets:"

        for line in output.splitlines():
            stripped_line = line.strip()
            if prefix in stripped_line and packet_suffix in stripped_line:
                packet_count = int(stripped_line.split(":")[1].strip())
                total_packets += packet_count

        return total_packets

    def run(self, duration: int) -> None:
        def stat(self: ValidateOffload, duration: int) -> Result:
            SyncManager.wait_on_barrier()
            vf_rep = self.extract_vf_rep()
            self.ethtool_cmd = (
                f'exec -n default {self.pod_name} -- /bin/sh -c "ethtool -S {vf_rep}"'
            )
            if vf_rep == "ovn-k8s-mp0":
                return Result(out="Hostbacked pod", err="", returncode=0)
            if vf_rep == "external":
                return Result(out="External Iperf Server", err="", returncode=0)

            r1 = self.run_ethtool_cmd(self.ethtool_cmd)
            if r1.returncode != 0:
                logger.error("Ethtool command failed")
                return r1

            SyncManager.wait_on_client_finish()
            r2 = self.run_ethtool_cmd(self.ethtool_cmd)

            combined_out = f"{r1.out}--DELIMIT--{r2.out}"

            return Result(out=combined_out, err=r2.err, returncode=r2.returncode)

        self.exec_thread = ReturnValueThread(target=stat, args=(self, duration))
        self.exec_thread.start()

    def output(self, out: TftAggregateOutput) -> None:
        assert isinstance(
            self._output, PluginOutput
        ), f"Expected variable to be of type PluginOutput, got {type(self._output)} instead."
        out.plugins.append(self._output)

        if self.iperf_pod_type == PodType.HOSTBACKED:
            if isinstance(self._iperf_instance, IperfClient):
                logger.info(f"The client VF representor ovn-k8s-mp0_0 does not exist")
            else:
                logger.info(f"The server VF representor ovn-k8s-mp0_0 does not exist")

        logger.info(
            f"validateOffload results on {self.iperf_pod_name}: {self._output.result}"
        )

    def generate_output(self, data: str) -> PluginOutput:
        # Different behavior has been seen from the ethtool output depending on the driver in question
        # Log the output of ethtool temporarily until this is more stable.
        logger.info(f"generate hwol output from data: {data}")
        split_data = data.split("--DELIMIT--")
        parsed_data: dict[str, Union[str, int]] = {}

        if len(split_data) >= 1:
            parsed_data["rx_start"] = self.parse_packets(split_data[0], "rx")
            parsed_data["tx_start"] = self.parse_packets(split_data[0], "tx")

        if len(split_data) >= 2:
            parsed_data["rx_end"] = self.parse_packets(split_data[1], "rx")
            parsed_data["tx_end"] = self.parse_packets(split_data[1], "tx")

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
            name="validate_offload",
        )
