import datetime
import json
import perf

from pathlib import Path

import host
import testConfig
import tftbase

from evaluator import Evaluator
from logger import logger
from task import Task
from testConfig import ConfigDescriptor
from testSettings import TestSettings
from tftbase import TftAggregateOutput


class TrafficFlowTests:
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
        out = tftbase.output_list_serialize(tft_output)
        with open(log_file, "w") as f:
            json.dump(out, f)

    def evaluate_run_success(self, cfg_descr: ConfigDescriptor, log_file: Path) -> bool:
        # For the result of every test run, check the status of each run log to
        # ensure all test passed

        if not cfg_descr.tc.evaluator_config:
            return True

        evaluator = Evaluator(cfg_descr.tc.evaluator_config)

        logger.info(f"Evaluating results of tests {log_file}")
        results_path = log_file.parent / (str(log_file.stem) + "-RESULTS")

        test_results, plugin_results = evaluator.eval_log(log_file)

        # Generate Resulting Json
        logger.info(f"Dumping results to {results_path}")
        data = evaluator.dump_to_json(test_results, plugin_results)
        with open(results_path, "w") as file:
            file.write(data)

        # Return PassFailStatus
        res = evaluator.evaluate_pass_fail_status(test_results, plugin_results)
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
            cfg_descr=cfg_descr,
            conf_server=c_server,
            conf_client=c_client,
            instance_index=instance_index,
            reverse=reverse,
        )
        s, c = connection.test_type_handler.create_server_client(ts)
        servers.append(s)
        clients.append(c)
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

        ts.initialize_clmo_barrier(len(clients) + len(monitors))

        for tasks in servers + clients + monitors:
            tasks.start_setup()

        ts.event_server_alive.wait()

        for tasks in servers + clients + monitors:
            tasks.start_task()

        ts.event_client_finished.wait()

        for tasks in servers + clients + monitors:
            tasks.finish_task()

        for tasks in servers + clients + monitors:
            tasks.finish_setup()

        tft_aggregate_output = TftAggregateOutput()

        for tasks in servers + clients + monitors:
            tasks.aggregate_output(tft_aggregate_output)

        return tft_aggregate_output

    def _run_test_case(self, cfg_descr: ConfigDescriptor) -> list[TftAggregateOutput]:
        # TODO Allow for multiple connections / instances to run simultaneously
        tft_output: list[TftAggregateOutput] = []
        for cfg_descr2 in cfg_descr.describe_all_connections():
            connection = cfg_descr2.get_connection()
            logger.info(f"Starting {connection.name}")
            logger.info(f"Number Of Simultaneous connections {connection.instances}")
            for instance_index in range(connection.instances):
                tft_output.append(
                    self._run_test_case_instance(
                        cfg_descr2,
                        instance_index=instance_index,
                    )
                )
                if connection.test_type_handler.can_run_reverse():
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
