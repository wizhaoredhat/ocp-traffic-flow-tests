import sys
import yaml
import common
from abc import ABC, abstractmethod
from typing import Optional
from logger import logger
from testConfig import TestConfig
from testConfig import ClusterMode
from thread import ReturnValueThread
import host


class Task(ABC):
    def __init__(self, tc: TestConfig, index: int, node_name: str, tenant: bool):
        self.template_args = {}
        self.in_file_template = ""
        self.out_file_yaml = ""
        self.pod_name = ""
        self.exec_thread: Optional[ReturnValueThread] = None  # type: ignore
        self.lh = host.LocalHost()

        self.template_args["name_space"] = "default"
        self.template_args["net_attach_def_name"] = "default"
        self.template_args["test_image"] = common.FT_BASE_IMG
        self.template_args["command"] = "/sbin/init"
        self.template_args["args"] = ""
        self.template_args["index"] = f"{index}"

        self.index = index
        self.node_name = node_name
        self.tenant = tenant
        if not self.tenant and tc.mode == ClusterMode.SINGLE:
            logger.error("Cannot have non-tenant Task when cluster mode is single.")
            sys.exit(-1)

        self.template_args["node_name"] = self.node_name
        self.tc = tc

    def run_oc(self, cmd: str) -> host.Result:
        if self.tenant:
            r = self.tc.client_tenant.oc(cmd)
        else:
            r = self.tc.client_infra.oc(cmd)
        return r

    def get_pod_ip(self):
        r = self.run_oc(f"get pod {self.pod_name} -o yaml")
        if r.returncode != 0:
            logger.info(r)
            sys.exit(-1)

        y = yaml.safe_load(r.out)
        return y["status"]["podIP"]

    def create_cluster_ip_service(self) -> str:
        in_file_template = "./manifests/svc-cluster-ip.yaml.j2"
        out_file_yaml = f"./manifests/yamls/svc-cluster-ip.yaml"

        common.j2_render(in_file_template, out_file_yaml, self.template_args)
        logger.info(f"Creating Cluster IP Service {out_file_yaml}")
        r = self.run_oc(f"apply -f {out_file_yaml}")
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.info(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-clusterip-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def create_node_port_service(self, nodeport: int) -> str:
        in_file_template = "./manifests/svc-node-port.yaml.j2"
        out_file_yaml = f"./manifests/yamls/svc-node-port.yaml"
        self.template_args["nodeport_svc_port"] = f"{nodeport}"

        common.j2_render(in_file_template, out_file_yaml, self.template_args)
        logger.info(f"Creating Node Port Service {out_file_yaml}")
        r = self.run_oc(f"apply -f {out_file_yaml}")
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.info(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-nodeport-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def setup(self):
        # Check if pod already exists
        r = self.run_oc(f"get pod {self.pod_name} --output=json")
        if r.returncode != 0:
            # otherwise create the pod
            logger.info(f"Creating Pod {self.pod_name}.")
            r = self.run_oc(f"apply -f {self.out_file_yaml}")
            if r.returncode != 0:
                logger.info(r)
                sys.exit(-1)
        else:
            logger.info(f"Pod {self.pod_name} already exists.")

        logger.info(f"Waiting for Pod {self.pod_name} to become ready.")
        r = self.run_oc(f"wait --for=condition=ready pod/{self.pod_name} --timeout=1m")
        if r.returncode != 0:
            logger.info(r)
            sys.exit(-1)

    @abstractmethod
    def run(self, duration: int):
        raise NotImplementedError("Must implement run()")

    @abstractmethod
    def stop(self):
        raise NotImplementedError("Must implement stop()")

    """
    output() should be called to store the results of this task in a PluginOutput class object, and return this by appending the instance to the
    TftAggregateOutput Plugin fields. Additionally, this function should handle printing any required info/debug to the console. The results must
    be formated such that other modules can easily consume the output, such as a module to determine the success/failure/performance of a given run.
    """

    @abstractmethod
    def output(self, out: common.TftAggregateOutput):
        raise NotImplementedError("Must implement output()")
