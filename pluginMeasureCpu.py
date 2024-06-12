import jc

from typing import Any
from typing import cast

import perf
import pluginbase

from common import j2_render
from host import Result
from logger import logger
from syncManager import SyncManager
from task import PluginTask
from testConfig import TestConfig
from tftbase import PluginOutput
from tftbase import TFT_TOOLS_IMG
from tftbase import TftAggregateOutput
from thread import ReturnValueThread


class PluginMeasureCpu(pluginbase.Plugin):
    PLUGIN_NAME = "measure_cpu"

    def enable(
        self,
        *,
        tc: TestConfig,
        node_server_name: str,
        node_client_name: str,
        perf_server: perf.PerfServer,
        perf_client: perf.PerfClient,
        tenant: bool,
    ) -> list[PluginTask]:
        return [
            TaskMeasureCPU(tc, node_server_name, tenant),
            TaskMeasureCPU(tc, node_client_name, tenant),
        ]


plugin = PluginMeasureCpu()


class TaskMeasureCPU(PluginTask):
    @property
    def plugin(self) -> pluginbase.Plugin:
        return plugin

    def __init__(self, tc: TestConfig, node_name: str, tenant: bool):
        super().__init__(tc, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = (
            f"./manifests/yamls/tools-pod-{self.node_name}-measure-cpu.yaml"
        )
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-measure-cpu"
        self.template_args["test_image"] = TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]
        self.node_name = node_name
        self.cmd = ""

        j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

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
        assert isinstance(
            self._output, PluginOutput
        ), f"Expected variable to be of type PluginOutput, got {type(self._output)} instead."
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
