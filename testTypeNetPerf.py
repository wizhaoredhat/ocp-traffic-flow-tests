from dataclasses import dataclass

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
            if not r.success:
                return BaseOutput.from_cmd(r)

            data = r.out

            lines = data.strip().split("\n")

            if self.test_type == TestType.NETPERF_TCP_STREAM:
                headers = [
                    "Receive Socket Size Bytes",
                    "Send Socket Size Bytes",
                    "Send Message Size Bytes",
                    "Elapsed Time Seconds",
                    "Throughput 10^6bits/sec",
                ]
                values = lines[6].split()
            else:
                headers = [
                    "Socket Send Bytes",
                    "Size Receive Bytes",
                    "Request Size Bytes",
                    "Response Size Bytes",
                    "Elapsed Time Seconds",
                    "Transaction Rate Per Second",
                ]
                values = lines[6].split()

            parsed_data = dict(zip(headers, values))

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
        logger.info(f"{result.result}:")
