import json
import re
import time

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


class PluginMeasurePower(pluginbase.Plugin):
    PLUGIN_NAME = "measure_power"

    def _enable(
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
            TaskMeasurePower(tc, node_server_name, tenant),
            TaskMeasurePower(tc, node_client_name, tenant),
        ]


plugin = PluginMeasurePower()


class TaskMeasurePower(PluginTask):
    @property
    def plugin(self) -> pluginbase.Plugin:
        return plugin

    def __init__(self, tc: TestConfig, node_name: str, tenant: bool):
        super().__init__(tc, 0, node_name, tenant)

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
        j2_render(self.in_file_template, self.out_file_yaml, self.get_template_args())
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int) -> None:
        def extract(r: Result) -> int:
            for e in r.out.split("\n"):
                if "Instantaneous power reading" in e:
                    match = re.search(r"\d+", e)
                    if match:
                        return int(match.group())
            logger.error(f"Could not find Instantaneous power reading: {e}.")
            return 0

        def stat(self: TaskMeasurePower, cmd: str) -> Result:
            SyncManager.wait_on_barrier()
            total_pwr = 0
            iteration = 0
            while SyncManager.client_not_finished():
                r = self.run_oc(cmd)
                if r.returncode != 0:
                    logger.error(f"Failed to get power {cmd}: {r}")
                pwr = extract(r)
                total_pwr += pwr
                iteration += 1
                time.sleep(0.2)

            r = Result(json.dumps({"measure_power": f"{total_pwr/iteration}"}), "", 0)
            return r

        # 1 report at intervals defined by the duration in seconds.
        self.cmd = f"exec -t {self.pod_name} -- ipmitool dcmi power reading"
        self.exec_thread = ReturnValueThread(target=stat, args=(self, self.cmd))
        self.exec_thread.start()
        logger.info(f"Running {self.cmd}")

    def output(self, out: TftAggregateOutput) -> None:
        # Return machine-readable output to top level
        if not isinstance(self._output, PluginOutput):
            return
        out.plugins.append(self._output)

        # Print summary to console logs
        logger.info(f"measurePower results: {self._output.result['measure_power']}")

    def generate_output(self, data: str) -> PluginOutput:
        parsed_data = json.loads(data)
        return PluginOutput(
            plugin_metadata={
                "name": "MeasurePower",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            command=self.cmd,
            result=parsed_data,
            name=plugin.PLUGIN_NAME,
        )
