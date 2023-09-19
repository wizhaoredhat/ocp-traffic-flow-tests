import common
from logger import logger
from testConfig import TestConfig
from thread import ReturnValueThread
from task import Task
from host import Result
from typing import Optional
import sys
import yaml
import json
import jc

def parse_out_packet(output: str, prefix: str) -> Optional[int]:
    for line in output.lines():
        stripped_line = line.strip()
        if stripped_line.startswith(prefix):
            return int(stripped_line.split(":")[1])
        
    return None

class Ethtool(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-ethtool.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-ethtool"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")
        
    def run_st(self) -> Result:
        get_vf_rep_ethtool = GetVfRep(self, self.tft, self.node_name, self.tenant).run_st()
        data = json.loads(get_vf_rep_ethtool.out)
        test_vf_rep= data["containers"][0]["podSandboxId"][:15]
    
        cmd = f"exec -n default {self.pod_name} -- /bin/sh -c ethtool -S {test_vf_rep}"
        return self.run_oc(cmd)

    def run(self, duration: int):
        self.exec_thread = ReturnValueThread(target=stat, args=(self.run_st))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping ethtool execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        ethtool_output = r.out
        logger.debug(f"ethtool.stop(): {r.out}")

    def output(self):
        #TODO: handle printing/storing output here
        pass

class GetVfRep(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-GetVfRep.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-GetVfRep"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")
        
    def run_st(self) -> Result:
        cmd = f"exec -n default {self.pod_name} -- /bin/sh -c chroot /host /bin/bash -c \"crictl ps -a --name=ft-client-pod -o json \""
        return self.run_oc(cmd)

    def run(self, duration: int):
        self.exec_thread = ReturnValueThread(target=stat, args=(self.run_st))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping Get Vf Rep execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        ethtool_output = r.out
        logger.debug(f"GetVfRep.stop(): {r.out}")

    def output(self):
        #TODO: handle printing/storing output here
        pass

class Tcpdump(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-tcpdump.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-tcpdump"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run_st(self) -> Result:
        get_vf_rep_tcp_dump = GetVfRep(self, self.tft, self.node_name, self.tenant).run_st()
        data = json.loads(get_vf_rep_tcp_dump.out)
        test_vf_rep= data["containers"][0]["podSandboxId"][:15]

        
        cmd = f"exec -t {self.pod_name} -- /bin/sh -c timeout --preserve-status 30 tcpdump -v -i ${test_vf_rep} -n not arp"
        return self.run_oc(cmd)


    def run(self, duration: int):
        def stat(self, cmd: str):
            return self.run_oc(cmd)

        # 1 report at intervals defined by the duration in seconds.
        self.exec_thread = ReturnValueThread(target=stat, args=(self.run_st))
        self.exec_thread.start()
        logger.info(f"Running {cmd}")

    def stop(self):
        logger.info(f"Stopping tcpdump execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        ethtool_output = r.out
        logger.debug(f"tcpdump.stop(): {r.out}")

    def output(self):
        #TODO: handle printing/storing output here
        pass

class InspectVfRep(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-InspectVfRep.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-InspectVfRep"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG

        self.pod_name = self.template_args["pod_name"]
        
        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int):
        def stat(self):
            ethtool_start = Ethtool(self._tft, self.node_name, self.tenant).run_st()
            Tcpdump(self._tft, self.node_name, self.tenant).run_st()
            ethtool_end = Ethtool(self._tft, self.node_name, self.tenant).run_st()
            rxpktstart = parse_out_packet(ethtool_start.out, "rxpacket")
            txpktstart = parse_out_packet(ethtool_start.out, "txpacket")
            rxpktend = parse_out_packet(ethtool_start.out, "rxpacket")
            txpktend = parse_out_packet(ethtool_start.out, "txpacket")

            # Command failed somewhere, invalid result
            if any(result is None for result in [rxpktstart, rxpktend, txpktstart, txpktend]):
                return False

            rxcount = rxpktstart - rxpktend
            txcount = txpktstart - txpktend

            if rxcount > 10000 or txcount > 10000: 
                if rxcount > txcount:
                    rxcount_failure = rxcount
                else:
                    rxcount_failure = txcount
                return False
            
            return True

    def stop(self):
        logger.info(f"Stopping Inspect VF Rep execution on {self.pod_name}")
        r = self.exec_thread.join()
        if r.returncode != 0:
            logger.info(r)
        self.return_value = r.out
        # use this as test pass or fail
        ethtool_output = r.out
        logger.debug(f"InspectVfRep.stop(): {r.out}")

    def output(self):
        #TODO: handle printing/storing output here
        pass


class ValidateHWOL(Task):
    def __init__(self, tft: TestConfig, node_name: str, tenant: bool):
        super().__init__(tft, 0, node_name, tenant)

        self.in_file_template = "./manifests/tools-pod.yaml.j2"
        self.out_file_yaml = f"./manifests/yamls/tools-pod-{self.node_name}-ValidateHWOL.yaml"
        self.template_args["pod_name"] = f"tools-pod-{self.node_name}-ValidateHWOL"
        self.template_args["test_image"] = common.TFT_TOOLS_IMG 


        self.pod_name = self.template_args["pod_name"]

        common.j2_render(self.in_file_template, self.out_file_yaml, self.template_args)
        logger.info(f"Generated Server Pod Yaml {self.out_file_yaml}")

    def run(self, duration: int):
        def stat(self):
            # Wait to learn flows and hardware offload
            sleep(10)
           
            client_test = InspectVfRep(self.tft, self.node_name, False)
            client_test.run()
            client_test.stop()
            client_val = client_test.return_value

            infra_test = InspectVfRep(self.tft, self.node_name, True)
            infra_test.run()
            infra_test.stop()
            infra_val = infra_test.return_value

            if client_val == False or infra_val == False:
                return False
            return True
                

        # 1 report at intervals defined by the duration in seconds.
        self.exec_thread = ReturnValueThread(target=stat)
        self.exec_thread.start()
        logger.info(f"Running client and server tests")

    def stop(self):
        logger.info(f"Stopping client and server tests for Validate HWOL {self.pod_name}")
        r = self.exec_thread.join()
        if r.out == True:
            print("HWOL is passing")
        else:
            print("HWOL is failing")
        if r.returncode != 0:
            logger.info(r)

    def output(self):
        #TODO: handle printing/storing output here
        pass

