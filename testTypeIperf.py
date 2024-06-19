import json
import perf

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import tftbase

from logger import logger
from perf import PerfClient
from perf import PerfServer
from task import TaskOperation
from testSettings import TestSettings
from testType import TestTypeHandler
from tftbase import BaseOutput
from tftbase import Bitrate
from tftbase import IperfOutput
from tftbase import TestType


IPERF_EXE = "iperf3"
IPERF_UDP_OPT = "-u -b 25G"
IPERF_REV_OPT = "-R"


@dataclass(frozen=True)
class TestTypeHandlerIperf(TestTypeHandler):
    def _create_server_client(self, ts: TestSettings) -> tuple[PerfServer, PerfClient]:
        s = IperfServer(ts=ts)
        c = IperfClient(ts=ts, server=s)
        return (s, c)

    def can_run_reverse(self) -> bool:
        if self.test_type == TestType.IPERF_TCP:
            return True
        return False

    def _calculate_gbps_tcp(self, result: Mapping[str, Any]) -> Bitrate:
        try:
            sum_sent = result["end"]["sum_sent"]
            sum_received = result["end"]["sum_received"]
        except KeyError as e:
            logger.error(
                f"KeyError: {e}. Malformed results when parsing iperf tcp for sum_sent/received"
            )
            raise Exception(
                "calculate_gbps_iperf_tcp(): failed to parse iperf test results"
            )

        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        bitrate_received = sum_received["bits_per_second"] / 1e9

        return Bitrate(
            tx=float(f"{bitrate_sent:.5g}"), rx=float(f"{bitrate_received:.5g}")
        )

    def _calculate_gbps_udp(self, result: Mapping[str, Any]) -> Bitrate:

        sum_data = result["end"]["sum"]

        # UDP tests only have sender traffic
        bitrate_sent = sum_data["bits_per_second"] / 1e9
        return Bitrate(tx=float(f"{bitrate_sent:.5g}"), rx=float(f"{bitrate_sent:.5g}"))

    def calculate_gbps(self, result: Mapping[str, Any]) -> Bitrate:
        # If an error occurred, bitrate = 0
        if "error" in result:
            logger.error(f"An error occurred during iperf test: {result['error']}")
            return Bitrate.NA

        if self.test_type == TestType.IPERF_TCP:
            return self._calculate_gbps_tcp(result)
        return self._calculate_gbps_udp(result)


test_type_handler_iperf_tcp = TestTypeHandlerIperf(TestType.IPERF_TCP)
test_type_handler_iperf_udp = TestTypeHandlerIperf(TestType.IPERF_UDP)


class IperfServer(perf.PerfServer):
    def get_template_args(self) -> dict[str, str]:

        extra_args: dict[str, str] = {}
        if self.exec_persistent:
            extra_args["command"] = IPERF_EXE
            extra_args["args"] = f'["-s", "-p", "{self.port}"]'

        return {
            **super().get_template_args(),
            **extra_args,
        }

    def _create_setup_operation_get_thread_action_cmd(self) -> str:
        return f"{IPERF_EXE} -s -p {self.port} --one-off --json"

    def _create_setup_operation_get_cancel_action_cmd(self) -> str:
        return f"killall {IPERF_EXE}"


class IperfClient(perf.PerfClient):
    def _create_task_operation(self) -> TaskOperation:
        server_ip = self.get_target_ip()
        cmd = (
            f"{IPERF_EXE} -c {server_ip} -p {self.port} --json -t {self.get_duration()}"
        )
        if self.test_type == TestType.IPERF_UDP:
            cmd += f" {IPERF_UDP_OPT}"
        if self.reverse:
            cmd += f" {IPERF_REV_OPT}"

        def _thread_action() -> BaseOutput:
            self.ts.clmo_barrier.wait()
            r = self.run_oc_exec(cmd)
            self.ts.event_client_finished.set()
            if not r.success:
                return BaseOutput.from_cmd(r)

            data = r.out

            parsed_data = json.loads(data)
            return IperfOutput(
                tft_metadata=self.ts.get_test_metadata(),
                command=cmd,
                result=parsed_data,
            )

        return TaskOperation(
            log_name=self.log_name,
            thread_action=_thread_action,
        )

    def _aggregate_output(
        self,
        result: tftbase.AggregatableOutput,
        out: tftbase.TftAggregateOutput,
    ) -> None:
        assert isinstance(result, IperfOutput)

        out.flow_test = result

        # Print summary to console logs
        logger.info(f"Results of {self.ts.get_test_str()}:")
        if self.iperf_error_occurred(result.result):
            logger.error(
                "Encountered error while running test:\n" f"  {result.result['error']}"
            )
            return
        if self.test_type == TestType.IPERF_TCP:
            self.print_tcp_results(result.result)
        if self.test_type == TestType.IPERF_UDP:
            self.print_udp_results(result.result)

    def print_tcp_results(self, data: Mapping[str, Any]) -> None:
        sum_sent = data["end"]["sum_sent"]
        sum_received = data["end"]["sum_received"]

        transfer_sent = sum_sent["bytes"] / (1024**3)
        bitrate_sent = sum_sent["bits_per_second"] / 1e9
        transfer_received = sum_received["bytes"] / (1024**3)
        bitrate_received = sum_received["bits_per_second"] / 1e9
        mss = data["start"]["tcp_mss_default"]

        logger.info(
            f"\n  [ ID]   Interval              Transfer        Bitrate\n"
            f"  [SENT]   0.00-{sum_sent['seconds']:.2f} sec   {transfer_sent:.2f} GBytes  {bitrate_sent:.2f} Gbits/sec sender\n"
            f"  [REC]   0.00-{sum_received['seconds']:.2f} sec   {transfer_received:.2f} GBytes  {bitrate_received:.2f} Gbits/sec receiver\n"
            f"  MSS = {mss}"
        )

    def print_udp_results(self, data: Mapping[str, Any]) -> None:
        sum_data = data["end"]["sum"]

        total_gigabytes = sum_data["bytes"] / (1024**3)
        average_gigabitrate = sum_data["bits_per_second"] / 1e9
        average_jitter = sum_data["jitter_ms"]
        total_lost_packets = sum_data["lost_packets"]
        total_lost_percent = sum_data["lost_percent"]

        logger.info(
            f"\n  Total GBytes: {total_gigabytes:.4f} GBytes\n"
            f"  Average Bitrate: {average_gigabitrate:.2f} Gbits/s\n"
            f"  Average Jitter: {average_jitter:.9f} ms\n"
            f"  Total Lost Packets: {total_lost_packets}\n"
            f"  Total Lost Percent: {total_lost_percent:.2f}%"
        )

    def iperf_error_occurred(self, data: Mapping[str, Any]) -> bool:
        return "error" in data
