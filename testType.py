import typing

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass

from ktoolbox.logger import logger

from tftbase import TestType


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

    @staticmethod
    def get(test_type: TestType) -> "TestTypeHandler":
        # The test types are all known statically. No extensive plugin loading
        # mechanism is done here.
        if test_type in (TestType.IPERF_TCP, TestType.IPERF_UDP):
            import testTypeIperf

            if test_type == TestType.IPERF_TCP:
                return testTypeIperf.test_type_handler_iperf_tcp
            return testTypeIperf.test_type_handler_iperf_udp
        if test_type in (TestType.NETPERF_TCP_STREAM, TestType.NETPERF_TCP_RR):
            import testTypeNetPerf

            if test_type == TestType.NETPERF_TCP_STREAM:
                return testTypeNetPerf.test_type_handler_netperf_tcp_stream
            return testTypeNetPerf.test_type_handler_netperf_tcp_rr
        if test_type == TestType.HTTP:
            import testTypeHttp

            return testTypeHttp.test_type_handler_http
        if test_type == TestType.SIMPLE:
            import testTypeSimple

            return testTypeSimple.test_type_handler_simple
        raise ValueError(f"Unsupported test type {test_type}")


if typing.TYPE_CHECKING:
    from task import ClientTask
    from task import ServerTask
    from testSettings import TestSettings
