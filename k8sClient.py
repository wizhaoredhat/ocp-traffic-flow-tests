import kubernetes  # type: ignore
import logging
import os
import shlex
import typing
import yaml

import host


class K8sClient:
    def __init__(self, kubeconfig: typing.Optional[str] = None):
        if kubeconfig is None:
            kubeconfig = os.getenv("KUBECONFIG")
            if not kubeconfig:
                raise RuntimeError(
                    "KUBECONFIG environment variable not set and no kubeconfig argument specified"
                )
        if not os.path.exists(kubeconfig):
            raise RuntimeError(
                f"KUBECONFIG={shlex.quote(kubeconfig)} file does not exist"
            )
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

    def oc(
        self,
        cmd: str,
        *,
        may_fail: bool = False,
        die_on_error: bool = False,
        namespace: typing.Optional[str] = None,
    ) -> host.Result:
        namespace_args: tuple[str, ...] = ()
        if namespace:
            namespace_args = ("-n", namespace)
        return host.local.run(
            ["kubectl", "--kubeconfig", self._kc, *namespace_args, *shlex.split(cmd)],
            die_on_error=die_on_error,
            log_level_fail=logging.DEBUG if may_fail else logging.ERROR,
        )
