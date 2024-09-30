import logging
import typing

from abc import ABC
from abc import abstractmethod
from typing import Optional

from ktoolbox import common

from tftbase import PluginOutput
from tftbase import PluginResult
from tftbase import TestMetadata


logger = logging.getLogger("tft." + __name__)


class Plugin(ABC):
    PLUGIN_NAME = ""

    @property
    def log_name(self) -> str:
        return f"plugin[{self.PLUGIN_NAME}"

    def enable(
        self,
        *,
        ts: "TestSettings",
        node_server_name: str,
        node_client_name: str,
        perf_server: "ServerTask",
        perf_client: "ClientTask",
        tenant: bool,
    ) -> list["PluginTask"]:
        tasks = self._enable(
            ts=ts,
            node_server_name=node_server_name,
            node_client_name=node_client_name,
            perf_server=perf_server,
            perf_client=perf_client,
            tenant=tenant,
        )
        logger.debug(f"{self.log_name}: enable ({len(tasks)} tasks, {tasks})")
        return tasks

    @abstractmethod
    def _enable(
        self,
        *,
        ts: "TestSettings",
        node_server_name: str,
        node_client_name: str,
        perf_server: "ServerTask",
        perf_client: "ClientTask",
        tenant: bool,
    ) -> list["PluginTask"]:
        pass

    def eval_plugin_output(
        self,
        md: TestMetadata,
        plugin_output: PluginOutput,
    ) -> Optional[PluginResult]:
        if not plugin_output.success:
            logger.error(
                f"{self.PLUGIN_NAME} plugin failed for {common.dataclass_to_json(md)}: {plugin_output.err_msg}"
            )
        else:
            logger.debug(
                f"{self.PLUGIN_NAME} plugin succeded for {common.dataclass_to_json(md)}"
            )
        return PluginResult(
            tft_metadata=md,
            plugin_name=self.PLUGIN_NAME,
            success=plugin_output.success,
        )


_plugins: dict[str, Plugin] = {}


def _plugins_ensure_loaded() -> None:

    if _plugins:
        # already loaded.
        return

    # Plugins register themselves when we load their module.
    # But we must ensure that the module is loaded.
    #
    # We could search the file system for plugins, instead just hardcode
    # the list of known plugins. This is the only place where we refer to
    # plugins explicitly.
    import pluginMeasureCpu
    import pluginMeasurePower
    import pluginValidateOffload

    modules = [
        pluginMeasureCpu,
        pluginMeasurePower,
        pluginValidateOffload,
    ]
    for m in modules:
        p = m.plugin
        assert isinstance(p, Plugin)
        assert p.PLUGIN_NAME
        assert p.PLUGIN_NAME not in _plugins
        _plugins[p.PLUGIN_NAME] = p


def get_all() -> list[Plugin]:
    _plugins_ensure_loaded()
    return list(_plugins.values())


def get_by_name(plugin_name: str) -> Plugin:
    _plugins_ensure_loaded()
    plugin = _plugins.get(plugin_name)
    if plugin is None:
        raise ValueError(f'Plugin "{plugin_name}" does not exist')
    return plugin


if typing.TYPE_CHECKING:
    # "pluginbase" cannot import modules like perf, task or testSettings, because
    # those modules import "pluginbase" in turn. However, to forward declare
    # type annotations, we do need those module here. Import them with
    # TYPE_CHECKING, but otherwise avoid the cyclic dependency between
    # modules.
    from task import ClientTask
    from task import ServerTask
    from task import PluginTask
    from testSettings import TestSettings
