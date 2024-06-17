import jc

from typing import Any
from typing import cast

import perf
import pluginbase

from host import Result
from logger import logger
from syncManager import SyncManager
from task import PluginTask
from testSettings import TestSettings
from tftbase import PluginOutput
from tftbase import TFT_TOOLS_IMG
from tftbase import TftAggregateOutput
from thread import ReturnValueThread


class PluginMeasureCpu(pluginbase.Plugin):
    PLUGIN_NAME = "measure_cpu"

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
        return [
            TaskMeasureCPU(ts, node_server_name, tenant),
            TaskMeasureCPU(ts, node_client_name, tenant),
        ]


plugin = PluginMeasureCpu()


class TaskMeasureCPU(PluginTask):
    @property
    def plugin(self) -> pluginbase.Plugin:
        return plugin

    def __init__(self, ts: TestSettings, node_name: str, tenant: bool):
        super().__init__(ts, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = (
            f"./manifests/yamls/tools-pod-{self.node_name}-measure-cpu.yaml"
        )
        self.pod_name = f"tools-pod-{self.node_name}-measure-cpu"
        self.node_name = node_name
        self.cmd = ""

    def get_template_args(self) -> dict[str, str]:
        return {
            **super().get_template_args(),
            "pod_name": self.pod_name,
            "test_image": TFT_TOOLS_IMG,
        }

    def initialize(self) -> None:
        super().initialize()
        self.render_file("Server Pod Yaml")

    def run(self, duration: int) -> None:
        def stat(self: TaskMeasureCPU, cmd: str) -> Result:
            SyncManager.wait_on_barrier()
            return self.run_oc(cmd)

        # 1 report at intervals defined by the duration in seconds.
        self.cmd = f"exec {self.pod_name} -- mpstat -P ALL {duration} 1"
        self.exec_thread = ReturnValueThread(target=stat, args=(self, self.cmd))
        self.exec_thread.start()
        logger.info(f"Running {self.cmd}")

    def output(self, out: TftAggregateOutput) -> None:
        # Return machine-readable output to top level
        if not isinstance(self._output, PluginOutput):
            return
        out.plugins.append(self._output)

        # Print summary to console logs
        p_idle = self._output.result["percent_idle"]
        logger.info(f"Idle on {self.node_name} = {p_idle}%")

    # TODO: We are currently only storing the "cpu: all" data from mpstat
    def generate_output(self, data: str) -> PluginOutput:
        # satisfy the linter. jc.parse returns a list of dicts in this case
        parsed_data = cast(list[dict[str, Any]], jc.parse("mpstat", data))
        return PluginOutput(
            plugin_metadata={
                "name": "MeasureCPU",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            command=self.cmd,
            result=parsed_data[0],
            name=plugin.PLUGIN_NAME,
        )
