import abc
import dataclasses
import json
import pathlib
import shlex
import typing
import yaml

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from typing import Optional
from typing import TypeVar

import common
import host

from common import StructParseBase
from common import StructParseBaseNamed
from common import strict_dataclass
from common import structparse_check_and_pop_name
from common import structparse_check_and_pop_name_required
from common import structparse_check_empty_dict
from common import structparse_check_strdict
from k8sClient import K8sClient
from logger import logger
from pluginbase import Plugin
from testType import TestTypeHandler
from tftbase import ClusterMode
from tftbase import PodType
from tftbase import TestCaseType
from tftbase import TestType


T1 = TypeVar("T1")


def _check_plugin_name(name: str, yamlpath: str, is_plain_name: bool) -> Plugin:
    import pluginbase

    try:
        return pluginbase.get_by_name(name)
    except ValueError:
        yamlpath_suffix = "" if is_plain_name else ".name"
        raise ValueError(
            f'"{yamlpath}{yamlpath_suffix}": unknown plugin "{name}" (valid: {[p.PLUGIN_NAME for p in pluginbase.get_all()]}'
        )


T2 = TypeVar("T2", bound="ConfServer | ConfClient")


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class _ConfBaseClientServer(StructParseBaseNamed, abc.ABC):
    sriov: bool
    pod_type: PodType
    default_network: str

    def serialize(self) -> dict[str, Any]:
        return {
            **super().serialize(),
            "sriov": self.sriov,
            "default-network": self.default_network,
        }

    @staticmethod
    def _parse(
        conf_type: type[T2],
        yamlidx: int,
        yamlpath: str,
        arg: Any,
    ) -> T2:
        vdict = structparse_check_strdict(arg, yamlpath)

        name = structparse_check_and_pop_name_required(vdict, yamlpath)

        pod_type = PodType.NORMAL
        v = vdict.pop("sriov", None)
        v2 = common.str_to_bool(v, on_error=None, on_default=False)
        if v2 is None:
            raise ValueError(f'"{yamlpath}.sriov": expects a a boolean but got {v}')
        if v2:
            pod_type = PodType.SRIOV

        default_network = "default/default"
        v = vdict.pop("default-network", None)
        if v is not None:
            if not isinstance(v, str):
                raise ValueError(f'"{yamlpath}.name": expects a string but got {name}')
            default_network = v

        type_specific_kwargs = {}

        if conf_type == ConfServer:
            v = vdict.pop("persistent", None)
            persistent = common.str_to_bool(v, on_error=None, on_default=False)
            if persistent is None:
                raise ValueError(
                    f'"{yamlpath}.persistent": expects a a boolean but got {v}'
                )
            type_specific_kwargs["persistent"] = persistent

        structparse_check_empty_dict(vdict, yamlpath)

        result = conf_type(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            pod_type=pod_type,
            sriov=(pod_type == PodType.SRIOV),
            default_network=default_network,
            **type_specific_kwargs,
        )

        return typing.cast("T2", result)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfPlugin(StructParseBaseNamed):
    plugin: Plugin

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfPlugin":

        is_plain_name = isinstance(arg, str)

        if is_plain_name:
            # For convenience, we allow that the entry is a plain string instead
            # of a dictionary with "name" entry.
            name = arg
        else:
            vdict = structparse_check_strdict(arg, yamlpath)

            name = structparse_check_and_pop_name_required(vdict, yamlpath)

            structparse_check_empty_dict(vdict, yamlpath)

        plugin = _check_plugin_name(name, yamlpath, is_plain_name)

        return ConfPlugin(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            plugin=plugin,
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfServer(_ConfBaseClientServer):
    persistent: bool

    def serialize(self) -> dict[str, Any]:
        return {
            **super().serialize(),
            "persistent": self.persistent,
        }

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfServer":
        return _ConfBaseClientServer._parse(ConfServer, yamlidx, yamlpath, arg)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfClient(_ConfBaseClientServer):
    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfClient":
        return _ConfBaseClientServer._parse(ConfClient, yamlidx, yamlpath, arg)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfConnection(StructParseBaseNamed):
    test_type: TestType
    test_type_handler: TestTypeHandler
    instances: int
    server: tuple[ConfServer, ...]
    client: tuple[ConfClient, ...]
    plugins: tuple[ConfPlugin, ...]

    def serialize(self) -> dict[str, Any]:
        return {
            **super().serialize(),
            "type": self.test_type.name,
            "instances": self.instances,
            "server": [s.serialize() for s in self.server],
            "client": [c.serialize() for c in self.client],
            "plugins": [p.serialize() for p in self.plugins],
        }

    @staticmethod
    def parse(
        yamlidx: int, yamlpath: str, arg: Any, *, test_name: str
    ) -> "ConfConnection":
        v: Any
        vdict = structparse_check_strdict(arg, yamlpath)

        name = structparse_check_and_pop_name(vdict, yamlpath)
        if name is None:
            name = f"Connection {test_name}/{yamlidx+1}"

        v = vdict.pop("type", None)
        try:
            test_type = common.enum_convert(TestType, v, default=TestType.IPERF_TCP)
        except Exception:
            raise ValueError(
                f"{yamlpath}.type: expects a connection type like iperf-tcp (default), iperf-udp, http but got {v}"
            )

        try:
            test_type_handler = TestTypeHandler.get(test_type)
        except ValueError:
            raise ValueError(f'{yamlpath}.type: "{test_type.name}" is not implemented')

        instances = 1
        v = vdict.pop("instances", None)
        if v is not None:
            try:
                instances = int(v)
            except Exception:
                instances = 0
            if instances <= 0:
                raise ValueError(f'"{yamlpath}.instances": expects a positive number')

        server: list[ConfServer] = []
        v = vdict.pop("server", None)
        if v is not None:
            if not isinstance(v, list):
                raise ValueError(f'"{yamlpath}.server": mandatory list is empty')
            for yamlidx2, arg in enumerate(v):
                server.append(
                    ConfServer.parse(yamlidx2, f"{yamlpath}.server[{yamlidx}]", arg)
                )

        client: list[ConfClient] = []
        v = vdict.pop("client", None)
        if v is not None:
            if not isinstance(v, list):
                raise ValueError(f'"{yamlpath}.client": mandatory list is empty')
            for yamlidx2, arg in enumerate(v):
                client.append(
                    ConfClient.parse(yamlidx2, f"{yamlpath}.client[{yamlidx}]", arg)
                )

        plugins: list[ConfPlugin] = []
        v = vdict.pop("plugins", None)
        if v is not None:
            if not isinstance(v, list):
                raise ValueError(f'"{yamlpath}.plugins": mandatory list is empty')
            for yamlidx2, arg in enumerate(v):
                plugins.append(
                    ConfPlugin.parse(yamlidx2, f"{yamlpath}.plugins[{yamlidx}]", arg)
                )

        structparse_check_empty_dict(vdict, yamlpath)

        if len(server) > 1:
            raise ValueError(
                f'"{yamlpath}.server": currently only one server entry is supported'
            )

        if len(client) > 1:
            raise ValueError(
                f'"{yamlpath}.client": currently only one client entry is supported'
            )

        return ConfConnection(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            test_type=test_type,
            test_type_handler=test_type_handler,
            instances=instances,
            server=tuple(server),
            client=tuple(client),
            plugins=tuple(plugins),
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfTest(StructParseBaseNamed):
    namespace: str
    test_cases: tuple[TestCaseType, ...]
    duration: int
    connections: tuple[ConfConnection, ...]
    logs: pathlib.Path

    def serialize(self) -> dict[str, Any]:
        return {
            **super().serialize(),
            "namespace": self.namespace,
            "test_cases": [t.name for t in self.test_cases],
            "duration": self.duration,
            "connections": [c.serialize() for c in self.connections],
            "logs": str(self.logs),
        }

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfTest":
        v: Any
        vdict = structparse_check_strdict(arg, yamlpath)

        name = structparse_check_and_pop_name(vdict, yamlpath)
        if name is None:
            name = f"Test {yamlidx+1}"

        namespace = vdict.pop("namespace", None)
        if namespace is None:
            namespace = "default"
        elif not isinstance(namespace, str):
            raise ValueError(
                f'"{yamlpath}.namespace": expects a string but got {namespace}'
            )

        v = vdict.pop("test_cases", None)
        if v is None or (isinstance(v, str) and v == ""):
            # By default, all test case are run.
            v = "*"
        try:
            test_cases = common.enum_convert_list(TestCaseType, v)
        except Exception:
            raise ValueError(f'"{yamlpath}.namespace": mandatory parameter is missing')

        duration = 0
        v = vdict.pop("duration", None)
        if v is not None:
            try:
                duration = int(v)
            except Exception:
                duration = -1
            if duration < 0:
                raise ValueError(
                    f'"{yamlpath}.duration": expects a positive duration in seconds'
                )
        if duration == 0:
            duration = 3600

        connections: list[ConfConnection] = []
        v = vdict.pop("connections", None)
        if v is None:
            raise ValueError(
                f'"{yamlpath}.connections": mandatory parameter is missing'
            )
        if not isinstance(v, list):
            raise ValueError(f'"{yamlpath}.connections": mandatory list is empty')
        for yamlidx2, arg in enumerate(v):
            connections.append(
                ConfConnection.parse(
                    yamlidx2,
                    f"{yamlpath}.connections[{yamlidx}]",
                    arg,
                    test_name=name,
                )
            )

        logs = "ft-logs"
        v = vdict.pop("logs", None)
        if v is not None:
            if not isinstance(v, str):
                raise ValueError(f'"{yamlpath}.logs": expects a string but got {v}')
            logs = v

        structparse_check_empty_dict(vdict, yamlpath)

        return ConfTest(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            namespace=namespace,
            test_cases=tuple(test_cases),
            duration=duration,
            connections=tuple(connections),
            logs=pathlib.Path(logs),
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfConfig(StructParseBase):
    tft: tuple[ConfTest, ...]
    kubeconfig: Optional[str]
    kubeconfig_infra: Optional[str]

    def serialize(self) -> dict[str, Any]:
        return {
            "tft": [c.serialize() for c in self.tft],
            "kubeconfig": self.kubeconfig,
            "kubeconfig_infra": self.kubeconfig_infra,
        }

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfConfig":
        v: Any
        vdict = structparse_check_strdict(arg, yamlpath)

        v = vdict.pop("tft", None)
        if v is None:
            raise ValueError(f'"{yamlpath}": needs a "tft" key')
        if not isinstance(v, list):
            raise ValueError(
                f'"{yamlpath}.tft" must contain a list of tests but contains a type {type(v)}'
            )
        tft = tuple(
            ConfTest.parse(yamlidx2, f"{yamlpath}.tft[{yamlidx}]", arg)
            for yamlidx2, arg in enumerate(v)
        )

        kubeconfig: Optional[str] = None
        v = vdict.pop("kubeconfig", None)
        if v is not None:
            if not v:
                raise ValueError(f'"{yamlpath}.kubeconfig" cannot be empty')
            kubeconfig = v

        kubeconfig_infra: Optional[str] = None
        v = vdict.pop("kubeconfig_infra", None)
        if v is not None:
            if not v:
                raise ValueError(f'"{yamlpath}.kubeconfig_infra" cannot be empty')
            kubeconfig_infra = v

        if not tft:
            raise ValueError(
                f'"{yamlpath}.tft" must contain a list of tests but list is empty'
            )

        if kubeconfig_infra is not None:
            if kubeconfig is None:
                raise ValueError(
                    f"{yamlpath}.kubeconfig: missing parameter when kubeconfig_infra is given"
                )

        structparse_check_empty_dict(vdict, yamlpath)

        return ConfConfig(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            tft=tft,
            kubeconfig=kubeconfig,
            kubeconfig_infra=kubeconfig_infra,
        )


class TestConfig:
    KUBECONFIG_TENANT: str = "/root/kubeconfig.tenantcluster"
    KUBECONFIG_INFRA: str = "/root/kubeconfig.infracluster"
    KUBECONFIG_SINGLE: str = "/root/kubeconfig.nicmodecluster"
    KUBECONFIG_CX: str = "/root/kubeconfig.smartniccluster"

    full_config: dict[str, Any]
    config: ConfConfig
    kubeconfig: str
    kubeconfig_infra: Optional[str]
    _client_tenant: Optional[K8sClient]
    _client_infra: Optional[K8sClient]
    evaluator_config: Optional[str]

    @property
    def mode(self) -> ClusterMode:
        if self.kubeconfig_infra is None:
            return ClusterMode.SINGLE
        return ClusterMode.DPU

    @staticmethod
    def _detect_kubeconfigs() -> tuple[str, Optional[str]]:

        # Find out what type of cluster are we in.

        kubeconfig: str
        kubeconfig_infra: Optional[str] = None

        if host.local.file_exists(TestConfig.KUBECONFIG_SINGLE):
            kubeconfig = TestConfig.KUBECONFIG_SINGLE
        elif host.local.file_exists(TestConfig.KUBECONFIG_CX):
            kubeconfig = TestConfig.KUBECONFIG_CX
        elif host.local.file_exists(TestConfig.KUBECONFIG_TENANT):
            if host.local.file_exists(TestConfig.KUBECONFIG_INFRA):
                kubeconfig = TestConfig.KUBECONFIG_TENANT
                kubeconfig_infra = TestConfig.KUBECONFIG_INFRA
            else:
                raise RuntimeError(
                    "Assuming DPU...Cannot Find Infrastructure Cluster Config"
                )
        else:
            raise RuntimeError("Cannot Find Kubeconfig")

        return (kubeconfig, kubeconfig_infra)

    def __init__(
        self,
        *,
        full_config: Optional[dict[str, Any]] = None,
        config_path: Optional[str] = None,
        kubeconfigs: Optional[tuple[str, Optional[str]]] = None,
        evaluator_config: Optional[str] = None,
    ) -> None:

        if config_path is not None:
            if full_config is not None:
                raise ValueError(
                    "Must either specify a full_config or a config_path argument"
                )
            with open(config_path, "r") as f:
                full_config = yaml.safe_load(f)

        if not isinstance(full_config, dict):
            raise ValueError(
                f"invalid config is not a dictionary but {type(full_config)}"
            )

        try:
            config = ConfConfig.parse(0, "", full_config)
        except Exception as e:
            p = (f' "{config_path}"') if config_path else ""
            raise ValueError(f"invalid configuration{p}: {e}")

        self.full_config = full_config
        self.config = config

        self._client_tenant = None
        self._client_infra = None

        if self.config.kubeconfig is not None:
            self.kubeconfig, self.kubeconfig_infra = (
                self.config.kubeconfig,
                self.config.kubeconfig_infra,
            )
        else:
            if kubeconfigs is None:
                kubeconfigs = TestConfig._detect_kubeconfigs()
            else:
                if kubeconfigs[0] is None:
                    raise ValueError("Missing kubeconfig")
            self.kubeconfig, self.kubeconfig_infra = kubeconfigs

        self.evaluator_config = evaluator_config

        s = json.dumps(full_config["tft"])
        logger.info(f"config: KUBECONFIG={shlex.quote(self.kubeconfig)}")
        if self.kubeconfig_infra is not None:
            logger.info(
                f"config: KUBECONFIG_INFRA={shlex.quote(self.kubeconfig_infra)}"
            )
        if self.evaluator_config is not None:
            logger.info(f"config: EVAL_CONFIG={shlex.quote(self.evaluator_config)}")
        logger.info(f"config: {s}")
        logger.debug(f"config-full: {self.config.serialize_json()}")

    def client(self, *, tenant: bool) -> K8sClient:
        if tenant:
            client = self._client_tenant
        else:
            if self.kubeconfig_infra is None:
                raise RuntimeError("TestConfig has no infra client")
            client = self._client_infra

        if client is not None:
            return client

        # Construct the K8sClient on first.

        if tenant:
            self._client_tenant = K8sClient(self.kubeconfig)
        else:
            assert self.kubeconfig_infra is not None
            self._client_infra = K8sClient(self.kubeconfig_infra)

        return self.client(tenant=tenant)

    @property
    def client_tenant(self) -> K8sClient:
        return self.client(tenant=True)

    @property
    def client_infra(self) -> K8sClient:
        return self.client(tenant=False)


@strict_dataclass
@dataclass(frozen=True)
class ConfigDescriptor:
    tc: TestConfig
    tft_idx: int = dataclasses.field(default=-1, kw_only=True)
    test_cases_idx: int = dataclasses.field(default=-1, kw_only=True)
    connections_idx: int = dataclasses.field(default=-1, kw_only=True)

    def _post_check(self) -> None:
        if self.tft_idx < -1 or self.tft_idx >= len(self.tc.config.tft):
            raise ValueError("tft_idx out of range")

        if self.test_cases_idx < -1:
            raise ValueError("test_cases_idx out of range")
        if self.test_cases_idx >= 0:
            if self.tft_idx < 0:
                raise ValueError("test_cases_idx requires tft_idx")
            if self.test_cases_idx >= len(self.tc.config.tft[self.tft_idx].test_cases):
                raise ValueError("test_cases_idx out or range")

        if self.connections_idx < -1:
            raise ValueError("connections_idx out of range")
        if self.connections_idx >= 0:
            if self.tft_idx < 0:
                raise ValueError("connections_idx requires tft_idx")
            if self.connections_idx >= len(
                self.tc.config.tft[self.tft_idx].connections
            ):
                raise ValueError("connections_idx out or range")

    def get_tft(self) -> ConfTest:
        if self.tft_idx < 0:
            raise RuntimeError("No tft_idx set")
        return self.tc.config.tft[self.tft_idx]

    def get_test_case(self) -> TestCaseType:
        if self.test_cases_idx < 0:
            raise RuntimeError("No test_cases_idx set")
        return self.get_tft().test_cases[self.test_cases_idx]

    def get_connection(self) -> ConfConnection:
        if self.connections_idx < 0:
            raise RuntimeError("No connections_idx set")
        return self.get_tft().connections[self.connections_idx]

    def get_server(self) -> ConfServer:
        c = self.get_connection()
        assert len(c.server) == 1
        return c.server[0]

    def get_client(self) -> ConfClient:
        c = self.get_connection()
        assert len(c.client) == 1
        return c.client[0]

    def describe_all_tft(self) -> Generator["ConfigDescriptor", None, None]:
        for tft_idx in range(len(self.tc.config.tft)):
            yield ConfigDescriptor(tc=self.tc, tft_idx=tft_idx)

    def describe_all_test_cases(self) -> Generator["ConfigDescriptor", None, None]:
        for test_cases_idx in range(len(self.get_tft().test_cases)):
            yield ConfigDescriptor(
                tc=self.tc,
                tft_idx=self.tft_idx,
                connections_idx=self.connections_idx,
                test_cases_idx=test_cases_idx,
            )

    def describe_all_connections(self) -> Generator["ConfigDescriptor", None, None]:
        for connections_idx in range(len(self.get_tft().connections)):
            yield ConfigDescriptor(
                tc=self.tc,
                tft_idx=self.tft_idx,
                test_cases_idx=self.test_cases_idx,
                connections_idx=connections_idx,
            )
