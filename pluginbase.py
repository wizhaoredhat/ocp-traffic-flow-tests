import typing

from abc import ABC
from abc import abstractmethod
from typing import Optional

from tftbase import PluginOutput
from tftbase import PluginResult
from tftbase import TestMetadata


class Plugin(ABC):
    PLUGIN_NAME = ""

    @abstractmethod
    def enable(
        self,
        *,
        tc: "TestConfig",
        node_server_name: str,
        node_client_name: str,
        perf_server: "PerfServer",
        perf_client: "PerfClient",
        tenant: bool,
    ) -> list["PluginTask"]:
        pass

    def eval_log(
        self, plugin_output: PluginOutput, md: TestMetadata
    ) -> Optional[PluginResult]:
        # Some plugins don't have this implemented. They do nothing.
        return None


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
    # "pluginbase" cannot import modules like perf, task or testConfig, because
    # those modules import "pluginbase" in turn. However, to forward declare
    # type annotations, we do need those module here. Import them with
    # TYPE_CHECKING, but otherwise avoid the cyclic dependency between
    # modules.
    from perf import PerfClient
    from perf import PerfServer
    from task import PluginTask
    from testConfig import TestConfig
