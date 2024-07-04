import json
import typing
from typing import Optional

import host
import perf
import pluginbase
import tftbase

from logger import logger
from task import PluginTask
from task import TaskOperation
from testSettings import TestSettings
from tftbase import BaseOutput
from tftbase import PluginOutput
from tftbase import PluginResult
from tftbase import PodType
from tftbase import TFT_TOOLS_IMG
from tftbase import TestMetadata

VF_REP_TRAFFIC_THRESHOLD = 1000


def no_traffic_on_vf_rep(
    rx_start: int, tx_start: int, rx_end: int, tx_end: int
) -> bool:
    return (
        rx_end - rx_start < VF_REP_TRAFFIC_THRESHOLD
        and tx_end - tx_start < VF_REP_TRAFFIC_THRESHOLD
    )


class PluginValidateOffload(pluginbase.Plugin):
    PLUGIN_NAME = "validate_offload"

    def _enable(
        self,
        *,
        ts: TestSettings,
        node_server_name: str,
        node_client_name: str,
        perf_server: perf.PerfServer,
        perf_client: perf.PerfClient,
        tenant: bool,
    ) -> list[PluginTask]:
        # TODO allow this to run on each individual server + client pairs.
        return [
            TaskValidateOffload(ts, perf_server, tenant),
            TaskValidateOffload(ts, perf_client, tenant),
        ]

    def eval_log(
        self, plugin_output: PluginOutput, md: TestMetadata
    ) -> Optional[PluginResult]:
        rx_start = plugin_output.result.get("rx_start")
        tx_start = plugin_output.result.get("tx_start")
        rx_end = plugin_output.result.get("rx_end")
        tx_end = plugin_output.result.get("tx_end")

        if any(x is None for x in [rx_start, tx_start, rx_end, tx_end]):
            logger.error(
                f"Validate offload plugin is missing expected ethtool data in {md.test_case_id}"
            )
            success = False
        else:
            assert isinstance(rx_start, int)
            assert isinstance(tx_start, int)
            assert isinstance(rx_end, int)
            assert isinstance(tx_end, int)
            success = no_traffic_on_vf_rep(
                rx_start=rx_start,
                tx_start=tx_start,
                rx_end=rx_end,
                tx_end=tx_end,
            )

        return PluginResult(
            test_id=md.test_case_id,
            test_type=md.test_type,
            reverse=md.reverse,
            success=success,
        )


plugin = PluginValidateOffload()


class TaskValidateOffload(PluginTask):
    @property
    def plugin(self) -> pluginbase.Plugin:
        return plugin

    def __init__(
        self,
        ts: TestSettings,
        perf_instance: perf.PerfServer | perf.PerfClient,
        tenant: bool,
    ):
        super().__init__(ts, 0, perf_instance.node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = (
            f"./manifests/yamls/tools-pod-{self.node_name}-validate-offload.yaml"
        )
        self.pod_name = f"tools-pod-{self.node_name}-validate-offload"
        self._perf_instance = perf_instance
        self.perf_pod_name = perf_instance.pod_name
        self.perf_pod_type = perf_instance.pod_type

    def get_template_args(self) -> dict[str, str]:
        return {
            **super().get_template_args(),
            "pod_name": self.pod_name,
            "test_image": TFT_TOOLS_IMG,
        }

    def initialize(self) -> None:
        super().initialize()
        self.render_file("Server Pod Yaml")

    def extract_vf_rep(self) -> str:
        if self.perf_pod_type == PodType.HOSTBACKED:
            logger.info("The VF representor is: ovn-k8s-mp0")
            return "ovn-k8s-mp0"

        if self.perf_pod_name == perf.EXTERNAL_PERF_SERVER:
            logger.info("There is no VF on an external server")
            return "external"

        get_vf_rep_cmd = f"exec {self.pod_name} -- crictl --runtime-endpoint=unix:///host/run/crio/crio.sock ps -a --name={self.perf_pod_name} -o json"
        r = self.run_oc(get_vf_rep_cmd)

        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(f"Extract_vf_rep: {r.err}, {r.returncode}")

        vf_rep_json = r.out
        data = json.loads(vf_rep_json)
        logger.info(
            f"The VF representor is: {data['containers'][0]['podSandboxId'][:15]}"
        )
        return typing.cast(str, data["containers"][0]["podSandboxId"][:15])

    def run_ethtool_cmd(self, ethtool_cmd: str) -> tuple[bool, host.Result]:
        logger.info(f"Running {ethtool_cmd}")
        success = True
        r = self.run_oc(ethtool_cmd)
        if self.perf_pod_type != PodType.HOSTBACKED:
            success = r.success or ("already exists" not in r.err)
        return success, r

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

    def _create_task_operation(self) -> TaskOperation:
        def _thread_action() -> BaseOutput:
            self.ts.clmo_barrier.wait()
            vf_rep = self.extract_vf_rep()
            ethtool_cmd = f"exec {self.pod_name} -- ethtool -S {vf_rep}"
            if vf_rep == "ovn-k8s-mp0":
                return BaseOutput(msg="Hostbacked pod")
            if vf_rep == "external":
                return BaseOutput(msg="External Iperf Server")

            success1, r1 = self.run_ethtool_cmd(ethtool_cmd)
            if not success1 or not r1.success:
                return BaseOutput(success=False, msg="ethtool command failed")

            self.ts.event_client_finished.wait()

            success2, r2 = self.run_ethtool_cmd(ethtool_cmd)

            # Different behavior has been seen from the ethtool output depending on the driver in question
            # Log the output of ethtool temporarily until this is more stable.

            data1 = r1.out
            data2 = ""
            if success2 and r2.success:
                data2 = r2.out

            parsed_data: dict[str, str | int] = {}

            if data1:
                parsed_data["rx_start"] = self.parse_packets(data1, "rx")
                parsed_data["tx_start"] = self.parse_packets(data1, "tx")

            if data2:
                parsed_data["rx_end"] = self.parse_packets(data2, "rx")
                parsed_data["tx_end"] = self.parse_packets(data2, "tx")

            logger.info(
                f"rx_packet_start: {parsed_data.get('rx_start', 'N/A')}\n"
                f"tx_packet_start: {parsed_data.get('tx_start', 'N/A')}\n"
                f"rx_packet_end: {parsed_data.get('rx_end', 'N/A')}\n"
                f"tx_packet_end: {parsed_data.get('tx_end', 'N/A')}\n"
            )
            return PluginOutput(
                success=success2 and r2.success,
                command=ethtool_cmd,
                plugin_metadata={
                    "name": "GetEthtoolStats",
                    "node_name": self.node_name,
                    "pod_name": self.pod_name,
                },
                result=parsed_data,
                name=plugin.PLUGIN_NAME,
            )

        return TaskOperation(
            log_name=self.log_name,
            thread_action=_thread_action,
        )

    def _aggregate_output(
        self,
        result: tftbase.AggregatableOutput,
        out: tftbase.TftAggregateOutput,
    ) -> None:
        assert isinstance(result, PluginOutput)

        out.plugins.append(result)

        if self.perf_pod_type == PodType.HOSTBACKED:
            if isinstance(self._perf_instance, perf.PerfClient):
                logger.info("The client VF representor ovn-k8s-mp0_0 does not exist")
            else:
                logger.info("The server VF representor ovn-k8s-mp0_0 does not exist")

        logger.info(f"validateOffload results on {self.perf_pod_name}: {result.result}")
