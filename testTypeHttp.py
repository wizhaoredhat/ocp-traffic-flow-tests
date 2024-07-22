import shlex

from dataclasses import dataclass

import common
import perf
import tftbase

from perf import PerfClient
from perf import PerfServer
from task import TaskOperation
from testSettings import TestSettings
from testType import TestTypeHandler
from tftbase import BaseOutput
from tftbase import IperfOutput
from tftbase import TestType


@dataclass(frozen=True)
class TestTypeHandlerHttp(TestTypeHandler):
    def __init__(self) -> None:
        super().__init__(TestType.HTTP)

    def _create_server_client(self, ts: TestSettings) -> tuple[PerfServer, PerfClient]:
        s = HttpServer(ts=ts)
        c = HttpClient(ts=ts, server=s)
        return (s, c)


test_type_handler_http = TestTypeHandlerHttp()


class HttpServer(perf.PerfServer):
    def cmd_line_args(self) -> list[str]:
        return [
            "-m",
            "http.server",
            "-d",
            "/etc/ocp-traffic-flow-tests",
            f"{self.port}",
        ]

    def get_template_args(self) -> dict[str, str | list[str]]:

        extra_args: dict[str, str | list[str]] = {}
        if self.exec_persistent:
            extra_args["command"] = ["python3"]
            extra_args["args"] = self.cmd_line_args()

        return {
            **super().get_template_args(),
            **extra_args,
        }

    def _create_setup_operation_get_thread_action_cmd(self) -> str:
        return f"python3 {shlex.join(self.cmd_line_args())}"

    def _create_setup_operation_get_cancel_action_cmd(self) -> str:
        return "killall python3"


class HttpClient(perf.PerfClient):
    def _create_task_operation(self) -> TaskOperation:
        server_ip = self.get_target_ip()
        cmd = f"curl --fail -s http://{server_ip}:{self.port}/data"

        def _thread_action() -> BaseOutput:
            self.ts.clmo_barrier.wait()
            r = self.run_oc_exec(cmd)
            self.ts.event_client_finished.set()

            return IperfOutput(
                success=(
                    r.success and r.out == "ocp-traffic-flow-tests\n" and r.err == ""
                ),
                tft_metadata=self.ts.get_test_metadata(),
                command=cmd,
                result={
                    "result": common.dataclass_to_dict(r),
                },
                bitrate_gbps=tftbase.Bitrate.NA,
            )

        return TaskOperation(
            log_name=self.log_name,
            thread_action=_thread_action,
        )
