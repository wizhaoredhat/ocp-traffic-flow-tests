import typing

from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from logger import logger
from tftbase import Bitrate
from tftbase import TestType


@dataclass(frozen=True)
class TestTypeHandler(ABC):

    test_type: TestType

    def create_server_client(
        self, ts: "TestSettings"
    ) -> tuple["PerfServer", "PerfClient"]:
        logger.info(
            f"Initializing {self.test_type} server/client for test:\n {ts.get_test_info()}"
        )
        assert ts.connection.test_type == self.test_type
        return self._create_server_client(ts)

    @abstractmethod
    def _create_server_client(
        self, ts: "TestSettings"
    ) -> tuple["PerfServer", "PerfClient"]:
        pass

    def calculate_gbps(self, result: Mapping[str, Any]) -> Bitrate:
        # This type does not implement calculating gbps.
        return Bitrate.NA

    def can_run_reverse(self) -> bool:
        return False

    @staticmethod
    def get(test_type: TestType) -> "TestTypeHandler":
        # The test types are all known statically. No extensive plugin loading
        # mechanism is done here.
        if test_type in (TestType.IPERF_TCP, TestType.IPERF_UDP):
            import iperf

            if test_type == TestType.IPERF_TCP:
                return iperf.test_type_handler_iperf_tcp
            return iperf.test_type_handler_iperf_udp
        if test_type in (TestType.NETPERF_TCP_STREAM, TestType.NETPERF_TCP_RR):
            import netperf

            if test_type == TestType.NETPERF_TCP_STREAM:
                return netperf.test_type_handler_netperf_tcp_stream
            return netperf.test_type_handler_netperf_tcp_rr
        raise ValueError(f"Unsupported test type {test_type}")


if typing.TYPE_CHECKING:
    from perf import PerfClient
    from perf import PerfServer
    from testSettings import TestSettings
