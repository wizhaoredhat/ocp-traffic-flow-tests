import abc
import dataclasses
import json
import logging
import pathlib
import shlex
import threading
import typing
import yaml

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any
from typing import Optional
from typing import TypeVar

from ktoolbox import common
from ktoolbox import host
from ktoolbox.common import StructParseBase
from ktoolbox.common import StructParseBaseNamed
from ktoolbox.common import strict_dataclass
from ktoolbox.k8sClient import K8sClient

from pluginbase import Plugin
from testType import TestTypeHandler
from tftbase import ClusterMode
from tftbase import PodType
from tftbase import TestCaseType
from tftbase import TestType


logger = logging.getLogger("tft." + __name__)


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
class _ConfBaseConnectionItem(StructParseBaseNamed, abc.ABC):
    @property
    def connection(self) -> "ConfConnection":
        return self._owner_reference.get(ConfConnection)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class _ConfBaseClientServer(_ConfBaseConnectionItem, abc.ABC):
    sriov: bool
    pod_type: PodType
    default_network: str

    # Extra arguments for the client/server. Their actual meaning depend on the
    # "type". These might be command line arguments passed to the tool.
    args: Optional[tuple[str, ...]]

    def serialize(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.args is not None:
            d["args"] = list(self.args)
        return {
            **super().serialize(),
            "sriov": self.sriov,
            "default-network": self.default_network,
            **d,
        }

    @staticmethod
    def _parse(
        conf_type: type[T2],
        yamlidx: int,
        yamlpath: str,
        arg: Any,
    ) -> T2:
        with common.structparse_with_strdict(arg, yamlpath) as varg:

            name = common.structparse_pop_str_name(*varg.for_name())

            sriov = common.structparse_pop_bool(
                *varg.for_key("sriov"),
                default=False,
            )

            default_network = common.structparse_pop_str(
                *varg.for_key("default-network"),
                default="default/default",
            )

            def _construct_args(
                yamlidx2: int,
                yamlpath2: str,
                arg2: Any,
            ) -> tuple[str, ...]:
                if isinstance(arg2, str):
                    return tuple(shlex.split(arg2))
                if isinstance(arg2, list):
                    if not all(isinstance(x, str) for x in arg2):
                        raise ValueError(
                            f'"{yamlpath2}": expects a list of strings but got {repr(arg2)}'
                        )
                    return tuple(arg2)
                raise ValueError(
                    f'"{yamlpath}.args": expects a string or a list of strings but got {repr(arg2)}'
                )

            args = common.structparse_pop_obj(
                *varg.for_key("args"),
                construct=_construct_args,
                default=None,
            )

            type_specific_kwargs = {}

            if conf_type == ConfServer:
                persistent = common.structparse_pop_bool(
                    *varg.for_key("persistent"),
                    default=False,
                )
                type_specific_kwargs["persistent"] = persistent

        result = conf_type(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            pod_type=PodType.SRIOV if sriov else PodType.NORMAL,
            sriov=sriov,
            default_network=default_network,
            args=args,
            **type_specific_kwargs,
        )

        return typing.cast("T2", result)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfPlugin(_ConfBaseConnectionItem):
    plugin: Plugin

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfPlugin":

        is_plain_name = isinstance(arg, str)

        if is_plain_name:
            # For convenience, we allow that the entry is a plain string instead
            # of a dictionary with "name" entry.
            name = arg
        else:
            with common.structparse_with_strdict(arg, yamlpath) as varg:
                name = common.structparse_pop_str_name(*varg.for_name())

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
    secondary_network_nad: Optional[str]
    resource_name: Optional[str]

    # This parameter is not expressed in YAML. It gets passed by the parent to
    # ConfConnection.parse()
    namespace: str

    def __post_init__(self) -> None:
        for s in self.server:
            s._owner_reference.init(self)
        for c in self.client:
            c._owner_reference.init(self)
        for p in self.plugins:
            p._owner_reference.init(self)

    @property
    def tft(self) -> "ConfTest":
        return self._owner_reference.get(ConfTest)

    def serialize(self) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        common.dict_add_optional(
            extra, "secondary_network_nad", self.secondary_network_nad
        )
        common.dict_add_optional(extra, "resource_name", self.resource_name)
        return {
            **super().serialize(),
            "type": self.test_type.name,
            "instances": self.instances,
            "server": [s.serialize() for s in self.server],
            "client": [c.serialize() for c in self.client],
            "plugins": [p.serialize() for p in self.plugins],
            **extra,
        }

    @property
    def effective_secondary_network_nad(self) -> str:
        nad = self.secondary_network_nad
        if nad is None:
            nad = "ocp-secondary"
        if "/" not in nad:
            nad = f"{self.namespace}/{nad}"
        return nad

    @staticmethod
    def parse(
        yamlidx: int,
        yamlpath: str,
        arg: Any,
        *,
        test_name: str,
        namespace: str,
    ) -> "ConfConnection":
        with common.structparse_with_strdict(arg, yamlpath) as varg:

            name = common.structparse_pop_str_name(
                *varg.for_name(),
                default=f"Connection {test_name}/{yamlidx+1}",
            )

            test_type = common.structparse_pop_enum(
                *varg.for_key("type"),
                enum_type=TestType,
                default=TestType.IPERF_TCP,
            )

            try:
                test_type_handler = TestTypeHandler.get(test_type)
            except ValueError:
                raise ValueError(
                    f'"{yamlpath}.type": "{test_type.name}" is not implemented'
                )

            instances = common.structparse_pop_int(
                *varg.for_key("instances"),
                default=1,
                check=lambda val: val > 0,
            )

            server = common.structparse_pop_objlist(
                *varg.for_key("server"),
                construct=ConfServer.parse,
            )

            client = common.structparse_pop_objlist(
                *varg.for_key("client"),
                construct=ConfClient.parse,
            )

            plugins = common.structparse_pop_objlist(
                *varg.for_key("plugins"),
                construct=ConfPlugin.parse,
            )

            secondary_network_nad = common.structparse_pop_str(
                *varg.for_key("secondary_network_nad"),
                default=None,
            )

            resource_name = common.structparse_pop_str(
                *varg.for_key("resource_name"),
                default=None,
            )

        if len(server) > 1:
            raise ValueError(
                f'"{yamlpath}.server": currently only one server entry is supported'
            )

        if len(client) > 1:
            raise ValueError(
                f'"{yamlpath}.client": currently only one client entry is supported'
            )

        for idx, s in enumerate(server):
            if s.args is not None:
                if test_type not in (TestType.SIMPLE,):
                    raise ValueError(
                        f'"{yamlpath}.server[{idx}].args": args are not supported for test type {test_type}'
                    )

        for idx, c in enumerate(client):
            if c.args is not None:
                if test_type not in (TestType.SIMPLE,):
                    raise ValueError(
                        f'"{yamlpath}.client[{idx}].args": args are not supported for test type {test_type}'
                    )

        return ConfConnection(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            test_type=test_type,
            test_type_handler=test_type_handler,
            instances=instances,
            server=server,
            client=client,
            plugins=plugins,
            secondary_network_nad=secondary_network_nad,
            resource_name=resource_name,
            namespace=namespace,
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfTest(StructParseBaseNamed):
    namespace: str
    test_cases: tuple[TestCaseType, ...]
    duration: int
    connections: tuple[ConfConnection, ...]
    logs: pathlib.Path

    def __post_init__(self) -> None:
        for c in self.connections:
            c._owner_reference.init(self)

    @property
    def config(self) -> "ConfConfig":
        return self._owner_reference.get(ConfConfig)

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

        with common.structparse_with_strdict(arg, yamlpath) as varg:

            name = common.structparse_pop_str_name(
                *varg.for_name(),
                default=f"Test {yamlidx+1}",
            )

            namespace = common.structparse_pop_str(
                *varg.for_key("namespace"),
                default="default",
            )

            def _construct_test_cases(
                yamlidx2: int,
                yamlpath2: str,
                arg2: Any,
            ) -> tuple[TestCaseType, ...]:
                if arg2 is None or (isinstance(arg2, str) and arg2 == ""):
                    # By default, all test case are run.
                    arg2 = "*"
                try:
                    lst = common.enum_convert_list(TestCaseType, arg2)
                except Exception:
                    raise ValueError(
                        f'"{yamlpath2}": value is not a valid list of test cases'
                    ) from None
                return tuple(lst)

            test_cases = common.structparse_pop_obj(
                *varg.for_key("test_cases"),
                construct=_construct_test_cases,
                construct_default=True,
            )

            duration = common.structparse_pop_int(
                *varg.for_key("duration"),
                default=0,
                check=lambda val: val >= 0,
                description="a duration in seconds",
            )
            if duration == 0:
                duration = 3600

            connections = common.structparse_pop_objlist(
                *varg.for_key("connections"),
                construct=lambda yamlidx2, yamlpath2, arg: ConfConnection.parse(
                    yamlidx2,
                    yamlpath2,
                    arg,
                    test_name=name,
                    namespace=namespace,
                ),
                allow_empty=False,
            )

            logs = common.structparse_pop_str(
                *varg.for_key("logs"),
                default="ft-logs",
            )

        return ConfTest(
            yamlidx=yamlidx,
            yamlpath=yamlpath,
            name=name,
            namespace=namespace,
            test_cases=tuple(test_cases),
            duration=duration,
            connections=connections,
            logs=pathlib.Path(logs),
        )


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class ConfConfig(StructParseBase):
    tft: tuple[ConfTest, ...]
    kubeconfig: Optional[str]
    kubeconfig_infra: Optional[str]

    def __post_init__(self) -> None:
        for t in self.tft:
            t._owner_reference.init(self)

    @property
    def test_config(self) -> "TestConfig":
        return self._owner_reference.get(TestConfig)

    def serialize(self) -> dict[str, Any]:
        return {
            "tft": [c.serialize() for c in self.tft],
            "kubeconfig": self.kubeconfig,
            "kubeconfig_infra": self.kubeconfig_infra,
        }

    @staticmethod
    def parse(yamlidx: int, yamlpath: str, arg: Any) -> "ConfConfig":
        with common.structparse_with_strdict(arg, yamlpath) as varg:

            tft = common.structparse_pop_objlist(
                *varg.for_key("tft"),
                construct=ConfTest.parse,
                allow_empty=False,
            )

            kubeconfig = common.structparse_pop_str(
                *varg.for_key("kubeconfig"),
                default=None,
            )

            kubeconfig_infra = common.structparse_pop_str(
                *varg.for_key("kubeconfig_infra"),
                default=None,
            )

        if kubeconfig_infra is not None:
            if kubeconfig is None:
                raise ValueError(
                    f'"{yamlpath}.kubeconfig": missing parameter when kubeconfig_infra is given'
                )

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
    _client_lock: threading.Lock
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

        config._owner_reference.init(self)

        self.full_config = full_config
        self.config = config

        self._client_lock = threading.Lock()
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
        with self._client_lock:
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
