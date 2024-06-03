import kubernetes  # type: ignore
import yaml

import common
import host


class K8sClient:
    def __init__(self, kubeconfig: str):
        self._kc = kubeconfig
        with open(kubeconfig) as f:
            c = yaml.safe_load(f)
        self._api_client = kubernetes.config.new_client_from_config_dict(c)
        self._client = kubernetes.client.CoreV1Api(self._api_client)

    def get_nodes(
        self,
    ) -> list[str]:
        return [e.metadata.name for e in self._client.list_node().items]

    def get_nodes_with_label(self, label_selector: str) -> list[str]:
        return [
            e.metadata.name
            for e in self._client.list_node(label_selector=label_selector).items
        ]

    def oc(self, cmd: str) -> common.Result:
        lh = host.LocalHost()
        return lh.run(f"kubectl --kubeconfig {self._kc} {cmd} ")
