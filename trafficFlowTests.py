from common import (
    TestType,
    TestCaseType,
    TftAggregateOutput,
    TFT_TESTS,
    serialize_enum,
    VALIDATE_OFFLOAD_PLUGIN,
    MEASURE_POWER_PLUGIN,
    MEASURE_CPU_PLUGIN,
)
from testSettings import TestSettings
from testConfig import TestConfig
from logger import logger
from task import Task
from iperf import IperfServer, IperfClient
from netperf import NetPerfServer, NetPerfClient
import perf
from validateOffload import ValidateOffload
from measureCpu import MeasureCPU
from measurePower import MeasurePower
from host import LocalHost
import json
from pathlib import Path
from evaluator import Evaluator
import datetime
from dataclasses import asdict
from syncManager import SyncManager
from typing import Any


class TrafficFlowTests:
    def __init__(self, tc: TestConfig):
        self._tc: TestConfig = tc
        self.test_settings: TestSettings
        self.lh = LocalHost()
        self.log_path: Path = Path("ft-logs")
        self.log_file: Path
        self.tft_output: list[TftAggregateOutput] = []

    def _create_iperf_server_client(
        self, test_settings: TestSettings
    ) -> tuple[perf.PerfServer, perf.PerfClient]:
        logger.info(
            f"Initializing iperf server/client for test:\n {test_settings.get_test_info()}"
        )

        s = IperfServer(tc=self._tc, ts=self.test_settings)
        c = IperfClient(tc=self._tc, ts=self.test_settings, server=s)
        return (s, c)

    def _create_netperf_server_client(
        self, test_settings: TestSettings
    ) -> tuple[perf.PerfServer, perf.PerfClient]:
        logger.info(
            f"Initializing Netperf server/client for test:\n {test_settings.get_test_info()}"
        )

        s = NetPerfServer(tc=self._tc, ts=self.test_settings)
        c = NetPerfClient(tc=self._tc, ts=self.test_settings, server=s)
        return (s, c)

    def _configure_namespace(self, namespace: str) -> None:
        logger.info(f"Configuring namespace {namespace}")
        r = self._tc.client_tenant.oc(
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

    def _cleanup_previous_testspace(self, namespace: str) -> None:
        logger.info(f"Cleaning pods with label tft-tests in namespace {namespace}")
        r = self._tc.client_tenant.oc(f"delete pods -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception("cleanup_previous_testspace(): Failed to delete pods")
        logger.info(f"Cleaned pods with label tft-tests in namespace {namespace}")
        logger.info(f"Cleaning services with label tft-tests in namespace {namespace}")
        r = self._tc.client_tenant.oc(f"delete services -n {namespace} -l tft-tests")
        if r.returncode != 0:
            logger.error(r)
            raise Exception("cleanup_previous_testspace(): Failed to delete services")
        logger.info(f"Cleaned services with label tft-tests in namespace {namespace}")
        logger.info(
            f"Cleaning external containers {perf.EXTERNAL_PERF_SERVER} (if present)"
        )
        cmd = f"podman stop --time 10 {perf.EXTERNAL_PERF_SERVER}; podman rm --time 10 {perf.EXTERNAL_PERF_SERVER}"
        self.lh.run(cmd)

    def _enable_measure_cpu_plugin(
        self,
        monitors: list[Task],
        node_server_name: str,
        node_client_name: str,
        tenant: bool,
    ) -> None:
        s = MeasureCPU(self._tc, node_server_name, tenant)
        c = MeasureCPU(self._tc, node_client_name, tenant)
        monitors.append(s)
        monitors.append(c)

    def _enable_measure_power_plugin(
        self,
        monitors: list[Task],
        node_server_name: str,
        node_client_name: str,
        tenant: bool,
    ) -> None:
        s = MeasurePower(self._tc, node_server_name, tenant)
        c = MeasurePower(self._tc, node_client_name, tenant)
        monitors.append(s)
        monitors.append(c)

    def enable_validate_offload_plugin(
        self,
        monitors: list[Task],
        perf_server: perf.PerfServer,
        perf_client: perf.PerfClient,
        tenant: bool,
    ) -> None:
        s = ValidateOffload(self._tc, perf_server, tenant)
        c = ValidateOffload(self._tc, perf_client, tenant)
        monitors.append(s)
        monitors.append(c)

    def _run_tests(
        self,
        servers: list[perf.PerfServer],
        clients: list[perf.PerfClient],
        monitors: list[Task],
        duration: int,
    ) -> TftAggregateOutput:
        tft_aggregate_output = TftAggregateOutput()

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

    def _create_log_paths_from_tests(self, tests: dict[str, str]) -> None:
        if "logs" in tests:
            self.log_path = Path(tests["logs"])
        self.log_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        self.log_file = self.log_path / f"{timestamp}.json"
        logger.info(f"Logs will be written to {self.log_file}")

    def _dump_result_to_log(self) -> None:
        # Dump test outputs into log file
        log = self.log_file
        json_out: dict[str, list[dict[str, Any]]] = {TFT_TESTS: []}
        for out in self.tft_output:
            json_out[TFT_TESTS].append(asdict(out))
        with open(log, "w") as output_file:
            json.dump(serialize_enum(json_out), output_file)

    def evaluate_run_success(self) -> bool:
        # For the result of every test run, check the status of each run log to ensure all test passed
        evaluator = Evaluator(self.eval_config)

        logger.info(f"Evaluating results of tests {self.log_file}")
        results_file = str(self.log_file.stem) + "-RESULTS"
        results_path = self.log_path / results_file

        evaluator.eval_log(self.log_file)

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

    def _run(
        self,
        connections: dict[str, Any],
        test_type: TestType,
        test_id: TestCaseType,
        index: int,
        duration: int,
        reverse: bool = False,
    ) -> None:
        servers: list[perf.PerfServer] = []
        clients: list[perf.PerfClient] = []
        monitors: list[Task] = []
        node_server_name = connections["server"][0]["name"]
        node_client_name = connections["client"][0]["name"]

        self.test_settings = TestSettings(
            connection_name=connections["name"],
            test_case_id=test_id,
            node_server_name=node_server_name,
            node_client_name=node_client_name,
            server_pod_type=self._tc.pod_type_from_config(connections["server"][0]),
            client_pod_type=self._tc.pod_type_from_config(connections["client"][0]),
            server_default_network=self._tc.default_network_from_config(
                connections["server"][0]
            ),
            client_default_network=self._tc.default_network_from_config(
                connections["client"][0]
            ),
            index=index,
            test_type=test_type,
            reverse=reverse,
        )
        if test_type == TestType.IPERF_TCP or test_type == TestType.IPERF_UDP:
            s, c = self._create_iperf_server_client(self.test_settings)
            servers.append(s)
            clients.append(c)
        elif (
            test_type == TestType.NETPERF_TCP_STREAM
            or test_type == TestType.NETPERF_TCP_RR
        ):
            s, c = self._create_netperf_server_client(self.test_settings)
            servers.append(s)
            clients.append(c)
        else:
            logger.error("http connections not currently supported")
            raise Exception("http connections not currently supported")
        if connections["plugins"]:
            for plugins in connections["plugins"]:
                if plugins["name"] == MEASURE_CPU_PLUGIN:
                    self._enable_measure_cpu_plugin(
                        monitors, node_server_name, node_client_name, True
                    )
                if plugins["name"] == MEASURE_POWER_PLUGIN:
                    self._enable_measure_power_plugin(
                        monitors, node_server_name, node_client_name, True
                    )
                if plugins["name"] == VALIDATE_OFFLOAD_PLUGIN:
                    # TODO allow this to run on each individual server + client pairs.
                    iperf_server = servers[-1]
                    iperf_client = clients[-1]
                    self.enable_validate_offload_plugin(
                        monitors, iperf_server, iperf_client, True
                    )

        SyncManager.reset(len(clients) + len(monitors))
        output = self._run_tests(servers, clients, monitors, duration)
        self.tft_output.append(output)

    def _run_test_case(self, tests: dict[str, Any], test_id: TestCaseType) -> None:
        duration = int(tests["duration"])
        # TODO Allow for multiple connections / instances to run simultaneously
        for connections in tests["connections"]:
            logger.info(f"Starting {connections['name']}")
            logger.info(
                f"Number Of Simultaneous connections {connections['instances']}"
            )
            for index in range(connections["instances"]):
                test_type = self._tc.validate_test_type(connections)
                # if test_type is iperf_TCP run both forward and reverse tests
                self._run(
                    connections=connections,
                    test_type=test_type,
                    test_id=test_id,
                    index=index,
                    duration=duration,
                )
                if test_type == TestType.IPERF_TCP:
                    self._run(
                        connections=connections,
                        test_type=test_type,
                        test_id=test_id,
                        index=index,
                        duration=duration,
                        reverse=True,
                    )
                self._cleanup_previous_testspace(tests["namespace"])

    def run(self, tests: dict[str, Any], eval_config: str) -> None:
        self.eval_config = eval_config
        self._configure_namespace(tests["namespace"])
        self._cleanup_previous_testspace(tests["namespace"])
        self._create_log_paths_from_tests(tests)
        logger.info(f"Running test {tests['name']} for {tests['duration']} seconds")
        test_cases = self._tc.parse_test_cases(tests["test_cases"])
        for test_id in test_cases:
            self._run_test_case(tests=tests, test_id=test_id)
        self._dump_result_to_log()
