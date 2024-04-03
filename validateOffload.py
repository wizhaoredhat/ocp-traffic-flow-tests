from common import (
    TFT_TOOLS_IMG,
    PluginOutput,
    j2_render,
    TftAggregateOutput,
    PodType,
    RxTxData,
    BaseOutput,
)
from dataclasses import asdict
from logger import logger
from time import sleep
from testConfig import TestConfig
from iperf import IperfServer, IperfClient
from thread import ReturnValueThread
from task import Task
from typing import Optional, Union, Tuple
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
        self.iperf_pod_name = iperf_instance.template_args["pod_name"]
        self.iperf_pod_type = iperf_instance.pod_type

        j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def extract_vf_rep(self) -> str:
        if self.iperf_pod_type == PodType.HOSTBACKED:
            logger.info(f"The VF representor is: ovn-k8s-mp0_0")
            return "ovn-k8s-mp0_0"

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

    def run_ethtool_cmd(self, vf_rep: str) -> Tuple[int, int]:
        self.ethtool_cmd = (
            f'exec -n default {self.pod_name} -- /bin/sh -c "ethtool -S {vf_rep}"'
        )
        r = self.run_oc(self.ethtool_cmd)
        if self.iperf_pod_type != PodType.HOSTBACKED:
            if r.returncode != 0:
                if "already exists" not in r.err:
                    logger.info(r)
                    sys.exit(-1)

        ethtool_output = r.out
        rxpacket = self.parse_out_packet(ethtool_output, "rx_packet")
        txpacket = self.parse_out_packet(ethtool_output, "tx_packet")
        return (rxpacket, txpacket)

    def parse_out_packet(self, output: str, prefix: str) -> int:
        for line in output.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith(prefix):
                return int(stripped_line.split(":")[1])

        logger.warning(f"Parse packet. Prefix: {prefix} not found in: {output}")
        return 0

    def run_st(self) -> RxTxData:
        vf_rep = self.extract_vf_rep()
        (rxpacket_start, txpacket_start) = self.run_ethtool_cmd(vf_rep)
        sleep(self._duration)
        (rxpacket_end, txpacket_end) = self.run_ethtool_cmd(vf_rep)

        return RxTxData(
            rx_start=rxpacket_start,
            tx_start=txpacket_start,
            rx_end=rxpacket_end,
            tx_end=txpacket_end,
        )

    def run(self, duration: int):
        self.exec_thread = ReturnValueThread(target=self.run_st)
        self._duration = int(duration)
        self.exec_thread.start()

    def stop(self):
        logger.info(f"Stopping Get Vf Rep execution on {self.pod_name}")
        r = self.exec_thread.join()

        if self.iperf_pod_type == PodType.HOSTBACKED:
            data = {}
        else:
            data = asdict(r)
        self._output_ethtool = self.generate_output_ethtool(data, self.ethtool_cmd)

    def output(self, out: TftAggregateOutput):
        out.plugins.append(self._output_ethtool)

        if self.iperf_pod_type == PodType.HOSTBACKED:
            if isinstance(self._iperf_instance, IperfClient):
                logger.info(f"The client VF representor ovn-k8s-mp0_0 does not exist")
            else:
                logger.info(f"The server VF representor ovn-k8s-mp0_0 does not exist")
        else:
            # Print summary to console logs
            rx_packet_start = self._output_ethtool.result["rx_start"]
            tx_packet_start = self._output_ethtool.result["tx_start"]
            rx_packet_end = self._output_ethtool.result["rx_end"]
            tx_packet_end = self._output_ethtool.result["tx_end"]

            logger.info(
                f"rx_packet_start: {rx_packet_start}\n"
                f"tx_packet_start: {tx_packet_start}\n"
                f"rx_packet_end: {rx_packet_end}\n"
                f"tx_packet_end: {tx_packet_end}\n"
            )

    def generate_output_ethtool(self, data, cmd: str) -> PluginOutput:
        return PluginOutput(
            plugin_metadata={
                "name": "GetEthtoolStats",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            command=cmd,
            result=data,
            name="get_ethtool_stats",
        )

    def generate_output(self, data: dict) -> BaseOutput:
        raise NotImplementedError("generate_output() not implemented in IperfServer")
