import logging
import typing

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass

from ktoolbox import common

from tftbase import TestType


logger = logging.getLogger("tft." + __name__)


@dataclass(frozen=True)
class TestTypeHandler(ABC):

    test_type: TestType

    def create_server_client(
        self, ts: "TestSettings"
    ) -> tuple["ServerTask", "ClientTask"]:
        logger.info(f"Starting test {ts.get_test_info()}")
        assert ts.connection.test_type == self.test_type
        return self._create_server_client(ts)

    @abstractmethod
    def _create_server_client(
        self, ts: "TestSettings"
    ) -> tuple["ServerTask", "ClientTask"]:
        pass

    def can_run_reverse(self) -> bool:
        return False

    _registry: typing.ClassVar[dict[TestType, "TestTypeHandler"]] = {}

    @staticmethod
    def get(test_type: TestType) -> "TestTypeHandler":
        # Handlers self-register via TestTypeHandler.register_test_type() when
        # being imported. Ensure they are imported.
        import testTypeHttp  # noqa: F401
        import testTypeIperf  # noqa: F401
        import testTypeNetPerf  # noqa: F401
        import testTypeSimple  # noqa: F401

        with common.common_lock:
            handler = TestTypeHandler._registry.get(test_type)
        if handler is None:
            raise ValueError(f"Unsupported test type {test_type}")
        return handler

    @staticmethod
    def register_test_type(handler: "TestTypeHandler") -> None:
        test_type = handler.test_type
        with common.common_lock:
            h2 = TestTypeHandler._registry.setdefault(test_type, handler)
        if h2 is not handler:
            raise ValueError(f"Handler for test type {test_type} is already registered")


if typing.TYPE_CHECKING:
    from task import ClientTask
    from task import ServerTask
    from testSettings import TestSettings
