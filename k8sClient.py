import kubernetes
import yaml
import host
from common import Result
from typing import List


class K8sClient:
    def __init__(self, kubeconfig: str):
        self._kc = kubeconfig
        with open(kubeconfig) as f:
            c = yaml.safe_load(f)
        self._api_client = kubernetes.config.new_client_from_config_dict(c)
        self._client = kubernetes.client.CoreV1Api(self._api_client)

    def get_nodes(
        self,
    ) -> List[str]:
        return [e.metadata.name for e in self._client.list_node().items]

    def get_nodes_with_label(self, label_selector: str) -> List[str]:
        return [
            e.metadata.name
            for e in self._client.list_node(label_selector=label_selector).items
        ]

    def oc(self, cmd: str) -> Result:
        lh = host.LocalHost()
        return lh.run(f"kubectl --kubeconfig {self._kc} {cmd} ")
