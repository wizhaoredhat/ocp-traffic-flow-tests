import jc

from typing import Any
from typing import cast

import perf
import pluginbase
import tftbase

from logger import logger
from task import PluginTask
from task import TaskOperation
from testSettings import TestSettings
from tftbase import BaseOutput
from tftbase import PluginOutput


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

    def get_template_args(self) -> dict[str, str]:
        return {
            **super().get_template_args(),
            "pod_name": self.pod_name,
            "test_image": tftbase.get_tft_test_image(),
        }

    def initialize(self) -> None:
        super().initialize()
        self.render_file("Server Pod Yaml")

    def _create_task_operation(self) -> TaskOperation:
        def _thread_action() -> BaseOutput:

            self.ts.clmo_barrier.wait()

            cmd = f"mpstat -P ALL {self.get_duration()} 1"
            r = self.run_oc_exec(cmd)

            data = r.out

            # satisfy the linter. jc.parse returns a list of dicts in this case
            parsed_data = cast(list[dict[str, Any]], jc.parse("mpstat", data))
            return PluginOutput(
                plugin_metadata={
                    "name": "MeasureCPU",
                    "node_name": self.node_name,
                    "pod_name": self.pod_name,
                },
                command=cmd,
                result=parsed_data[0],
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
        p_idle = result.result["percent_idle"]
        logger.info(f"Idle on {self.node_name} = {p_idle}%")
