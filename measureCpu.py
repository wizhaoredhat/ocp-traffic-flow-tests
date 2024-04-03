from common import TFT_TOOLS_IMG, PluginOutput, j2_render, TftAggregateOutput, Result
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
import jc
from typing import List, Dict, Any, cast
from syncManager import SyncManager


class MeasureCPU(Task):
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
        def stat(self, cmd: str) -> Result:
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
        parsed_data = cast(List[Dict[str, Any]], jc.parse("mpstat", data))
        return PluginOutput(
            plugin_metadata={
                "name": "MeasureCPU",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            command=self.cmd,
            result=parsed_data[0],
            name="measure_cpu",
        )
