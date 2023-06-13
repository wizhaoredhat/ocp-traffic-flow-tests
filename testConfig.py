import host
import sys
from enum import Enum
from logger import logger
from k8sClient import K8sClient
from yaml import safe_load, safe_dump
import io


class ClusterMode(Enum):
    SINGLE    = 1
    DPU       = 3

class TestConfig():
    def __init__(self):
        self.mode = ClusterMode.SINGLE

        with open("./config.yaml", 'r') as f:
            contents = f.read()
            self.fullConfig = safe_load(io.StringIO(contents))

        self.kubeconfig_tenant = "/root/kubeconfig.tenantcluster"
        self.kubeconfig_infra = "/root/kubeconfig.infracluster"
        self.kubeconfig_single = "/root/kubeconfig.nicmodecluster"
        self.client_tenant = None
        self.client_infra = None
        self.server_node = None
        self.client_node = None

        lh = host.LocalHost()

        # Find out what type of cluster are we in.
        if lh.file_exists(self.kubeconfig_single):
            self.mode = ClusterMode.SINGLE
            self.client_tenant = K8sClient(self.kubeconfig_single)
        elif lh.file_exists(self.kubeconfig_tenant):
            if lh.file_exists(self.kubeconfig_infra):
                self.mode = ClusterMode.DPU
                self.client_tenant = K8sClient(self.kubeconfig_tenant)
                self.client_infra = K8sClient(self.kubeconfig_infra)
            else:
                logger.error("Assuming DPU...Cannot Find Infrastructure Cluster Config.")
                sys.exit(-1)
        else:
            logger.error("Cannot Find Kubeconfig.")
            sys.exit(-1)

        logger.info(self.GetConfig())

    def GetConfig(self):
        return self.fullConfig["tft"]
