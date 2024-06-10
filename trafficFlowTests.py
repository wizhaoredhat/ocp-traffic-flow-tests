import datetime
import json
import perf

from dataclasses import asdict
from pathlib import Path
from typing import Any

import host
import testConfig

from common import serialize_enum
from evaluator import Evaluator
from iperf import IperfClient
from iperf import IperfServer
from logger import logger
from netperf import NetPerfClient
from netperf import NetPerfServer
from syncManager import SyncManager
from task import Task
from testConfig import ConfigDescriptor
from testSettings import TestSettings
from tftbase import TFT_TESTS
from tftbase import TestType
from tftbase import TftAggregateOutput


class TrafficFlowTests:
    def _create_iperf_server_client(
        self, ts: TestSettings
    ) -> tuple[perf.PerfServer, perf.PerfClient]:
        logger.info(
            f"Initializing iperf server/client for test:\n {ts.get_test_info()}"
        )

        s = IperfServer(ts=ts)
        c = IperfClient(ts=ts, server=s)
        return (s, c)

    def _create_netperf_server_client(
        self, ts: TestSettings
    ) -> tuple[perf.PerfServer, perf.PerfClient]:
        logger.info(
            f"Initializing Netperf server/client for test:\n {ts.get_test_info()}"
        )

        s = NetPerfServer(ts)
        c = NetPerfClient(ts, server=s)
        return (s, c)

    def _configure_namespace(self, cfg_descr: ConfigDescriptor) -> None:
        namespace = cfg_descr.get_tft().namespace
        logger.info(f"Configuring namespace {namespace}")
        r = cfg_descr.tc.client_tenant.oc(
            f"label ns --overwrite {namespace} pod-security.kubernetes.io/enforce=privileged \
                                        pod-security.kubernetes.io/enforce-version=v1.24 \
                                        security.openshift.io/scc.podSecurityLabelSync=false"
        )
        if r.returncode != 0:
            logger.error(r)
            raise Exception(
                f"configure_namespace(): Failed to label namespace {namespace}"
            )
        logger.info(f"Configured namespace {namespace}")

    def _cleanup_previous_testspace(self, cfg_descr: ConfigDescriptor) -> None:
        namespace = cfg_descr.get_tft().namespace
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = cfg_descr.tc.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception("cleanup_previous_testspace(): Failed to delete pods")
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning services with label tft-tests in namespace {namespace}")
        r = cfg_descr.tc.client_tenant.oc(
            f"delete services -n {namespace} -l tft-tests"
        )
        if r.returncode != 0:
            logger.error(r)
            raise Exception("cleanup_previous_testspace(): Failed to delete services")
        logger.info(f"Cleaned services with label tft-tests in namespace {namespace}")
        logger.info(
            f"Cleaning external containers {perf.EXTERNAL_PERF_SERVER} (if present)"
        )
        cmd = f"podman rm --force --time 10 {perf.EXTERNAL_PERF_SERVER}"
        host.local.run(cmd)

    def _create_log_paths_from_tests(self, test: testConfig.ConfTest) -> Path:
        log_path = test.logs
        log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = log_path / f"{timestamp}.json"
        logger.info(f"Logs will be written to {log_file}")
        return log_file

    def _dump_result_to_log(
        self, tft_output: list[TftAggregateOutput], *, log_file: str
    ) -> None:
        # Dump test outputs into log file
        json_out: dict[str, list[dict[str, Any]]] = {TFT_TESTS: []}
        for out in tft_output:
            json_out[TFT_TESTS].append(asdict(out))
        with open(log_file, "w") as output_file:
            json.dump(serialize_enum(json_out), output_file)

    def evaluate_run_success(self, cfg_descr: ConfigDescriptor, log_file: Path) -> bool:
        # For the result of every test run, check the status of each run log to
        # ensure all test passed

        if not cfg_descr.tc.evaluator_config:
            return True

        evaluator = Evaluator(cfg_descr.tc.evaluator_config)

        logger.info(f"Evaluating results of tests {log_file}")
        results_path = log_file.parent / (str(log_file.stem) + "-RESULTS")

        evaluator.eval_log(log_file)

        # Generate Resulting Json
        logger.info(f"Dumping results to {results_path}")
        data = evaluator.dump_to_json()
        with open(results_path, "w") as file:
            file.write(data)

        # Return PassFailStatus
        res = evaluator.evaluate_pass_fail_status()
        logger.info(f"RESULT: Success = {res.result}.")
        logger.info(
            f"  FlowTest results: Passed {res.num_tft_passed}/{res.num_tft_passed + res.num_tft_failed}"
        )
        logger.info(
            f"  Plugin results: Passed {res.num_plugin_passed}/{res.num_plugin_passed + res.num_plugin_failed}"
        )

        return res.result

    def _run_test_case_instance(
        self,
        cfg_descr: ConfigDescriptor,
        instance_index: int,
        reverse: bool = False,
    ) -> TftAggregateOutput:
        connection = cfg_descr.get_connection()

        servers: list[perf.PerfServer] = []
        clients: list[perf.PerfClient] = []
        monitors: list[Task] = []

        c_server = connection.server[0]
        c_client = connection.client[0]

        ts = TestSettings(
            cfg_descr,
            conf_server=c_server,
            conf_client=c_client,
            instance_index=instance_index,
            reverse=reverse,
        )
        if (
            connection.test_type == TestType.IPERF_TCP
            or connection.test_type == TestType.IPERF_UDP
        ):
            s, c = self._create_iperf_server_client(ts)
            servers.append(s)
            clients.append(c)
        elif (
            connection.test_type == TestType.NETPERF_TCP_STREAM
            or connection.test_type == TestType.NETPERF_TCP_RR
        ):
            s, c = self._create_netperf_server_client(ts)
            servers.append(s)
            clients.append(c)
        else:
            logger.error("http connections not currently supported")
            raise Exception("http connections not currently supported")
        for plugin in connection.plugins:
            m = plugin.plugin.enable(
                ts=ts,
                node_server_name=c_server.name,
                node_client_name=c_client.name,
                perf_server=servers[-1],
                perf_client=clients[-1],
                tenant=True,
            )
            monitors.extend(m)

        for t in servers + clients + monitors:
            t.initialize()

        SyncManager.reset(len(clients) + len(monitors))

        tft_aggregate_output = TftAggregateOutput()

        duration = cfg_descr.get_tft().duration

        for tasks in servers + clients + monitors:
            tasks.setup()

        SyncManager.wait_on_server_alive()

        for tasks in servers + clients + monitors:
            tasks.run(duration)

        SyncManager.wait_on_client_finish()

        for tasks in servers + clients + monitors:
            tasks.stop(duration)

        for tasks in servers + clients + monitors:
            tasks.output(tft_aggregate_output)

        return tft_aggregate_output

    def _run_test_case(self, cfg_descr: ConfigDescriptor) -> list[TftAggregateOutput]:
        # TODO Allow for multiple connections / instances to run simultaneously
        tft_output: list[TftAggregateOutput] = []
        for cfg_descr2 in cfg_descr.describe_all_connections():
            connection = cfg_descr2.get_connection()
            logger.info(f"Starting {connection.name}")
            logger.info(f"Number Of Simultaneous connections {connection.instances}")
            for instance_index in range(connection.instances):
                # if test_type is iperf_TCP run both forward and reverse tests
                tft_output.append(
                    self._run_test_case_instance(
                        cfg_descr2,
                        instance_index=instance_index,
                    )
                )
                if connection.test_type == TestType.IPERF_TCP:
                    tft_output.append(
                        self._run_test_case_instance(
                            cfg_descr2,
                            instance_index=instance_index,
                            reverse=True,
                        )
                    )
                self._cleanup_previous_testspace(cfg_descr2)
        return tft_output

    def test_run(self, cfg_descr: ConfigDescriptor) -> None:
        test = cfg_descr.get_tft()
        self._configure_namespace(cfg_descr)
        self._cleanup_previous_testspace(cfg_descr)
        log_file = self._create_log_paths_from_tests(test)
        logger.info(f"Running test {test.name} for {test.duration} seconds")
        tft_output: list[TftAggregateOutput] = []
        for cfg_descr2 in cfg_descr.describe_all_test_cases():
            tft_output.extend(self._run_test_case(cfg_descr2))
        self._dump_result_to_log(tft_output, log_file=str(log_file))

        if not self.evaluate_run_success(cfg_descr, log_file):
            print(f"Failure detected in {cfg_descr.get_tft().name} results")
