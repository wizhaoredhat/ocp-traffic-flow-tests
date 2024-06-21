from dataclasses import dataclass
from typing import Any
from typing import Optional

import perf
import tftbase

from logger import logger
from perf import PerfClient
from perf import PerfServer
from task import TaskOperation
from testSettings import TestSettings
from testType import TestTypeHandler
from tftbase import BaseOutput
from tftbase import IperfOutput
from tftbase import TestType


NETPERF_SERVER_EXE = "netserver"
NETPERF_CLIENT_EXE = "netperf"


def netperf_parse(testname: Any, data: str) -> dict[str, float]:

    # Let's accept both the testname as string and as TestType enum.
    s_testname = str(testname)
    if s_testname.startswith("TestType."):
        s_testname = s_testname[len("TestType.") :]
    if s_testname.startswith("NETPERF_"):
        s_testname = s_testname[len("NETPERF_") :]

    if s_testname == "TCP_RR":
        headers = [
            "Socket Send Bytes",
            "Size Receive Bytes",
            "Request Size Bytes",
            "Response Size Bytes",
            "Elapsed Time Seconds",
            "Transaction Rate Per Second",
        ]
    elif s_testname == "TCP_STREAM":
        headers = [
            "Receive Socket Size Bytes",
            "Send Socket Size Bytes",
            "Send Message Size Bytes",
            "Elapsed Time Seconds",
            "Throughput 10^6bits/sec",
        ]
    else:
        raise TypeError(f'invalid testname "{testname}"')

    lines = data.split("\n")

    values: Optional[list[float]] = None
    if len(lines) >= 7:
        slist = [s.strip() for s in lines[6].split()]
        try:
            values = [float(s) for s in slist]
        except ValueError:
            pass
    if not values or len(values) != len(headers):
        raise ValueError("Cannot parse netperf output for tcp-stream: {repr(data)}")

    return dict(zip(headers, values))


@dataclass(frozen=True)
class TestTypeHandlerNetPerf(TestTypeHandler):
    def _create_server_client(self, ts: TestSettings) -> tuple[PerfServer, PerfClient]:
        s = NetPerfServer(ts)
        c = NetPerfClient(ts, server=s)
        return (s, c)


test_type_handler_netperf_tcp_stream = TestTypeHandlerNetPerf(
    TestType.NETPERF_TCP_STREAM
)
test_type_handler_netperf_tcp_rr = TestTypeHandlerNetPerf(TestType.NETPERF_TCP_RR)


class NetPerfServer(perf.PerfServer):
    def get_template_args(self) -> dict[str, str]:

        extra_args: dict[str, str] = {}
        if self.exec_persistent:
            extra_args["command"] = NETPERF_SERVER_EXE
            extra_args["args"] = f'["-p", "{self.port}", "-N"]'

        return {
            **super().get_template_args(),
            **extra_args,
        }

    def _create_setup_operation_get_thread_action_cmd(self) -> str:
        return f"{NETPERF_SERVER_EXE} -p {self.port} -N"

    def _create_setup_operation_get_cancel_action_cmd(self) -> str:
        return f"killall {NETPERF_SERVER_EXE}"


class NetPerfClient(perf.PerfClient):
    def _create_task_operation(self) -> TaskOperation:
        assert not self.reverse

        server_ip = self.get_target_ip()
        if self.test_type == TestType.NETPERF_TCP_STREAM:
            cmd = f"{NETPERF_CLIENT_EXE} -H {server_ip} -p {self.port} -t TCP_STREAM -l {self.get_duration()}"
        else:
            cmd = f"{NETPERF_CLIENT_EXE} -H {server_ip} -p {self.port} -t TCP_RR -l {self.get_duration()}"

        def _thread_action() -> BaseOutput:
            self.ts.clmo_barrier.wait()
            r = self.run_oc_exec(cmd)
            self.ts.event_client_finished.set()

            success_result = False
            parsed_data: dict[str, float] = {}
            bitrate_gbps = tftbase.Bitrate.NA

            if r.success:
                data = r.out
                try:
                    parsed_data = netperf_parse(self.test_type, data)
                except ValueError:
                    pass
                else:
                    success_result = True

            if success_result:
                if self.test_type == TestType.NETPERF_TCP_STREAM:
                    try:
                        x = float(parsed_data["Throughput 10^6bits/sec"])
                    except Exception:
                        success_result = False
                    else:
                        bitrate_gbps = tftbase.Bitrate(tx=x / 1000.0)
                else:
                    try:
                        x = float(parsed_data["Transaction Rate Per Second"])
                    except Exception:
                        success_result = False
                    else:
                        bitrate_gbps = tftbase.Bitrate(tx=x / 1000.0)

            return IperfOutput(
                success=success_result,
                tft_metadata=self.ts.get_test_metadata(),
                command=cmd,
                result=parsed_data,
                bitrate_gbps=bitrate_gbps,
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
        logger.info(f"{result.result}:")
