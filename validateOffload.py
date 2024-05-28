from common import (
    TFT_TOOLS_IMG,
    PluginOutput,
    j2_render,
    TftAggregateOutput,
    PodType,
    Result,
    VALIDATE_OFFLOAD_PLUGIN,
)
from logger import logger
from testConfig import TestConfig
import perf
from thread import ReturnValueThread
from task import Task
import json
from syncManager import SyncManager
import typing


class ValidateOffload(Task):
    def __init__(
        self,
        tft: TestConfig,
        perf_instance: perf.PerfServer | perf.PerfClient,
        tenant: bool,
    ):
        super().__init__(tft, 0, perf_instance.node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = (
            f"./manifests/yamls/tools-pod-{self.node_name}-validate-offload.yaml"
        )
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-validate-offload"
        self.template_args["test_image"] = TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]
        self._perf_instance = perf_instance
        self.perf_pod_name = perf_instance.pod_name
        self.perf_pod_type = perf_instance.pod_type
        self.ethtool_cmd = ""

        j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def extract_vf_rep(self) -> str:
        if self.perf_pod_type == PodType.HOSTBACKED:
            logger.info("The VF representor is: ovn-k8s-mp0")
            return "ovn-k8s-mp0"

        if self.perf_pod_name == perf.EXTERNAL_PERF_SERVER:
            logger.info("There is no VF on an external server")
            return "external"

        self.get_vf_rep_cmd = f'exec -n default {self.pod_name} -- /bin/sh -c "crictl --runtime-endpoint=unix:///host/run/crio/crio.sock ps -a --name={self.perf_pod_name} -o json "'
        r = self.run_oc(self.get_vf_rep_cmd)

        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(f"Extract_vf_rep: {r.err}, {r.returncode}")

        vf_rep_json = r.out
        data = json.loads(vf_rep_json)
        logger.info(
            f"The VF representor is: {data['containers'][0]['podSandboxId'][:15]}"
        )
        return typing.cast(str, data["containers"][0]["podSandboxId"][:15])

    def run_ethtool_cmd(self, ethtool_cmd: str) -> Result:
        logger.info(f"Running {ethtool_cmd}")
        r = self.run_oc(ethtool_cmd)
        if self.perf_pod_type != PodType.HOSTBACKED:
            if r.returncode != 0:
                if "already exists" not in r.err:
                    logger.error(f"Run_ethtool_cmd: {r.err}, {r.returncode}")
                    raise RuntimeError(
                        f"ValidateOffload error: {r.err} returncode: {r.returncode}"
                    )

        return r

    def parse_packets(self, output: str, packet_type: str) -> int:
        # Case1: Try to parse rx_packets and tx_packets from ethtool output
        prefix = f"{packet_type}_packets"
        if prefix in output:
            for line in output.splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith(prefix):
                    return int(stripped_line.split(":")[1])
        # Case2: Ethtool output does not provide these fields, so we need to sum the queues manually
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

        if self.perf_pod_type == PodType.HOSTBACKED:
            if isinstance(self._perf_instance, perf.PerfClient):
                logger.info("The client VF representor ovn-k8s-mp0_0 does not exist")
            else:
                logger.info("The server VF representor ovn-k8s-mp0_0 does not exist")

        logger.info(
            f"validateOffload results on {self.perf_pod_name}: {self._output.result}"
        )

    def generate_output(self, data: str) -> PluginOutput:
        # Different behavior has been seen from the ethtool output depending on the driver in question
        # Log the output of ethtool temporarily until this is more stable.
        # TODO: switch to debug
        logger.info(f"generate hwol output from data: {data}")
        split_data = data.split("--DELIMIT--")
        parsed_data: dict[str, str | int] = {}

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
            name=VALIDATE_OFFLOAD_PLUGIN,
        )
