import common
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from host import Result
import sys
import yaml
import json
import jc

class MeasureCPU(Task):
    def __init__(self, cc: TestConfig, node_name: str, tenant: bool):
        super().__init__(cc, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-measure-cpu.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-measure-cpu"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int):
        def stat(self, cmd: str):
            return self.run_oc(cmd)

        # 1 report at intervals defined by the duration in seconds.
        cmd = f"exec -t {self.pod_name} -- mpstat -P ALL {duration} 1"
        self.exec_thread = ReturnValueThread(target=stat, args=(self, cmd))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping measureCPU execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        logger.debug(f"measureCpu.stop(): {r.out}")
        data = jc.parse('mpstat', r.out)
        p_idle = data[0]['percent_idle']
        logger.info(f"Idle on {self.node_name} = {p_idle}%")

    def output(self):
        #TODO: handle printing/storing output here
        pass
