from abc import ABC
from abc import abstractmethod
from typing import Optional

import perf

from task import Task
from testConfig import TestConfig
from tftbase import PluginOutput
from tftbase import PluginResult
from tftbase import TestMetadata


class PluginTask(Task):
    @property
    @abstractmethod
    def plugin(self) -> "Plugin":
        pass


class Plugin(ABC):
    PLUGIN_NAME = ""

    @abstractmethod
    def enable(
        self,
        *,
        tc: TestConfig,
        node_server_name: str,
        node_client_name: str,
        perf_server: perf.PerfServer,
        perf_client: perf.PerfClient,
        tenant: bool,
    ) -> list[PluginTask]:
        pass

    def eval_log(
        self, plugin_output: PluginOutput, md: TestMetadata
    ) -> Optional[PluginResult]:
        # Some plugins don't have this implemented. They do nothing.
        return None


_plugins: dict[str, Plugin] = {}


def get_by_name(plugin_name: str) -> Plugin:

    if not _plugins:
        # We need to ensure, that these modules were loaded. Import them now.
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

    plugin = _plugins.get(plugin_name)
    if plugin is None:
        raise ValueError(f'Plugin "{plugin_name}" does not exist')
    return plugin
