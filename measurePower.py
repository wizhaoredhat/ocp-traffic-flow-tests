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
import re
import time

class MeasurePower(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-measure-cpu.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-measure-cpu"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int):
        def extract(r: Result) -> int:
            for e in r.out.split("\n"):
                if "Instantaneous power reading" in e:
                    match = re.search(r"\d+", e)
                    if match:
                        return int(match.group())
            logger.error(f"Could not find Instantaneous power reading: {e}.")
            return 0

        def stat(self, cmd: str, duration: int):
            end_time = time.time() + float(duration)
            total_pwr = 0
            iteration = 0
            while True:
                r = self.run_oc(cmd)
                if r.returncode != 0:
                    logger.error(f"Failed to get power {cmd}: {r}")
                pwr = extract(r)
                total_pwr += pwr
                iteration += 1
                # FIXME: Hardcode interval for now
                time.sleep(2)
                if time.time() > end_time:
                    break
            r = Result(f"{total_pwr/iteration}", "", 0)
            logger.info(r)
            return r

        # 1 report at intervals defined by the duration in seconds.
        cmd = f"exec -t {self.pod_name} -- ipmitool dcmi power reading"
        self.exec_thread = ReturnValueThread(target=stat, args=(self, cmd, duration))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping measurePower execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        logger.info(f"measurePower results: {r.out}")

    def output(self):
        #TODO: handle printing/storing output here
        pass
