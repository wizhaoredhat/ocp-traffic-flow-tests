from common import TFT_TOOLS_IMG, PluginOutput, j2_render, TftAggregateOutput
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
import jc


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

    def run(self, duration: int):
        def stat(self, cmd: str):
            return self.run_oc(cmd)

        # 1 report at intervals defined by the duration in seconds.
        self.cmd = f"exec -t {self.pod_name} -- mpstat -P ALL {duration} 1"
        self.exec_thread = ReturnValueThread(target=stat, args=(self, self.cmd))
        self.exec_thread.start()
        logger.info(f"Running {self.cmd}")

    def stop(self):
        logger.info(f"Stopping measureCPU execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        logger.debug(f"measureCpu.stop(): {r.out}")
        data = jc.parse("mpstat", r.out)
        p_idle = data[0]["percent_idle"]
        logger.info(f"Idle on {self.node_name} = {p_idle}%")
        self._output = self.generate_output(data)

    def output(self, out: TftAggregateOutput):
        # Return machine-readable output to top level
        out.plugins.append(self._output)

        # Print summary to console logs
        p_idle = self._output.result["percent_idle"]
        logger.info(f"Idle on {self.node_name} = {p_idle}%")

    # TODO: We are currently only storing the "cpu: all" data from mpstat
    def generate_output(self, data) -> PluginOutput:
        return PluginOutput(
            plugin_metadata={
                "name": "MeasureCPU",
                "node_name": self.node_name,
                "pod_name": self.pod_name,
            },
            command=self.cmd,
            result=data[0],
            name="measure_cpu",
        )
