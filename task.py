import sys
import typing
import yaml

from abc import ABC
from abc import abstractmethod
from typing import Optional

import common
import host
import tftbase

from logger import logger
from testSettings import TestSettings
from tftbase import ClusterMode
from thread import ReturnValueThread
from pluginbase import Plugin


class Task(ABC):
    def __init__(
        self, ts: TestSettings, index: int, node_name: str, tenant: bool
    ) -> None:
        self.in_file_template = ""
        self.out_file_yaml = ""
        self.pod_name = ""
        self.exec_thread: ReturnValueThread
        self.lh = host.local
        self.index = index
        self.node_name = node_name
        self.tenant = tenant
        self.ts = ts
        self.tc = ts.cfg_descr.tc

        if not self.tenant and self.tc.mode == ClusterMode.SINGLE:
            raise ValueError("Cannot have non-tenant Task when cluster mode is single")

    def get_namespace(self) -> str:
        return self.ts.cfg_descr.get_tft().namespace

    def get_template_args(self) -> dict[str, str]:
        return {
            "name_space": self.get_namespace(),
            "test_image": tftbase.TFT_TOOLS_IMG,
            "command": "/sbin/init",
            "args": "",
            "index": f"{self.index}",
            "node_name": self.node_name,
        }

    def render_file(
        self,
        log_info: str,
        in_file_template: Optional[str] = None,
        out_file_yaml: Optional[str] = None,
        template_args: Optional[dict[str, str]] = None,
    ) -> None:
        if in_file_template is None:
            in_file_template = self.in_file_template
        if out_file_yaml is None:
            out_file_yaml = self.out_file_yaml
        if template_args is None:
            template_args = self.get_template_args()
        logger.info(
            f'Generate {log_info} "{out_file_yaml}" (from "{in_file_template}")'
        )
        common.j2_render(in_file_template, out_file_yaml, template_args)

    def initialize(self) -> None:
        pass

    def run_oc(
        self,
        cmd: str,
        *,
        may_fail: bool = False,
        die_on_error: bool = False,
        namespace: Optional[str] | common._MISSING_TYPE = common.MISSING,
    ) -> host.Result:
        if isinstance(namespace, common._MISSING_TYPE):
            # By default, set use self.get_namespace(). You can select another
            # namespace or no namespace (by setting to None).
            namespace = self.get_namespace()
        return self.tc.client(tenant=self.tenant).oc(
            cmd,
            may_fail=may_fail,
            die_on_error=die_on_error,
            namespace=namespace,
        )

    def get_pod_ip(self) -> str:
        r = self.run_oc(f"get pod {self.pod_name} -o yaml", die_on_error=True)
        y = yaml.safe_load(r.out)
        return typing.cast(str, y["status"]["podIP"])

    def create_cluster_ip_service(self) -> str:
        in_file_template = "./manifests/svc-cluster-ip.yaml.j2"
        out_file_yaml = "./manifests/yamls/svc-cluster-ip.yaml"

        self.render_file("Cluster IP Service", in_file_template, out_file_yaml)
        r = self.run_oc(f"apply -f {out_file_yaml}", may_fail=True)
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-clusterip-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def create_node_port_service(self, nodeport: int) -> str:
        in_file_template = "./manifests/svc-node-port.yaml.j2"
        out_file_yaml = "./manifests/yamls/svc-node-port.yaml"

        template_args = {
            **self.get_template_args(),
            "nodeport_svc_port": f"{nodeport}",
        }

        self.render_file(
            "Node Port Service", in_file_template, out_file_yaml, template_args
        )
        r = self.run_oc(f"apply -f {out_file_yaml}", may_fail=True)
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-nodeport-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def setup(self) -> None:
        # Check if pod already exists
        r = self.run_oc(f"get pod {self.pod_name} --output=json", may_fail=True)
        if r.returncode != 0:
            # otherwise create the pod
            logger.info(f"Creating Pod {self.pod_name}.")
            r = self.run_oc(f"apply -f {self.out_file_yaml}", die_on_error=True)
        else:
            logger.info(f"Pod {self.pod_name} already exists.")

        logger.info(f"Waiting for Pod {self.pod_name} to become ready.")
        r = self.run_oc(
            f"wait --for=condition=ready pod/{self.pod_name} --timeout=1m",
            die_on_error=True,
        )

    @abstractmethod
    def run(self, duration: int) -> None:
        raise NotImplementedError(
            "Must implement run(). Use SyncManager.wait_barrier()"
        )

    def stop(self, timeout: float) -> None:
        class_name = self.__class__.__name__
        logger.info(f"Stopping execution on {class_name}")
        self.exec_thread.join_with_result(timeout=timeout * 1.5)
        if self.exec_thread.result is not None:
            r = self.exec_thread.result
            if r.returncode != 0:
                logger.error(
                    f"Error occurred while stopping {class_name}: errcode: {r.returncode} err {r.err}"
                )
            logger.debug(f"{class_name}.stop(): {r.out}")
            self._output = self.generate_output(data=r.out)
        else:
            logger.error(f"Thread {class_name} did not return a result")
            self._output = tftbase.BaseOutput("", {})

    """
    output() should be called to store the results of this task in a PluginOutput class object, and return this by appending the instance to the
    TftAggregateOutput Plugin fields. Additionally, this function should handle printing any required info/debug to the console. The results must
    be formated such that other modules can easily consume the output, such as a module to determine the success/failure/performance of a given run.
    """

    @abstractmethod
    def output(self, out: tftbase.TftAggregateOutput) -> None:
        raise NotImplementedError("Must implement output()")

    @abstractmethod
    def generate_output(self, data: str) -> tftbase.BaseOutput:
        raise NotImplementedError("Must implement generate_output()")


class PluginTask(Task):
    @property
    @abstractmethod
    def plugin(self) -> Plugin:
        pass
