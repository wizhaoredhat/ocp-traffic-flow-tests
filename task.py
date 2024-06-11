import enum
import shlex
import sys
import threading
import typing
import yaml

from abc import ABC
from abc import abstractmethod
from collections.abc import Iterable
from threading import Thread
from typing import Any
from typing import Callable
from typing import Optional
from typing import TypeVar

import common
import host
import tftbase

from logger import logger
from testSettings import TestSettings
from tftbase import ClusterMode
from tftbase import BaseOutput
from pluginbase import Plugin


T = TypeVar("T")


class _OperationState(enum.Enum):
    NEW = (1,)
    STARTING = (2,)
    RUNNING = (3,)
    STOPPING = 4
    STOPPED = 5


class TaskOperation:
    @typing.overload
    def __init__(
        self,
        *,
        log_name: str,
        thread_action: None = None,
        collect_action: Callable[[], BaseOutput],
        cancel_action: Optional[Callable[[], None]] = None,
        wait_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        pass

    @typing.overload
    def __init__(
        self,
        *,
        log_name: str,
        thread_action: Callable[[], BaseOutput],
        collect_action: None = None,
        cancel_action: Optional[Callable[[], None]] = None,
        wait_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        pass

    @typing.overload
    def __init__(
        self,
        *,
        log_name: str,
        thread_action: Callable[[], T],
        collect_action: Callable[[T], BaseOutput],
        cancel_action: Optional[Callable[[], None]] = None,
        wait_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        pass

    def __init__(
        self,
        *,
        log_name: str,
        thread_action: Optional[Callable[[], Any]] = None,
        collect_action: Optional[
            Callable[[], BaseOutput] | Callable[[Any], BaseOutput]
        ] = None,
        cancel_action: Optional[Callable[[], None]] = None,
        wait_ready: Optional[Callable[[], None]] = None,
    ) -> None:
        if thread_action is None and collect_action is None:
            raise ValueError("either thread_action or collect_action must be provided")
        if cancel_action is not None and thread_action is None:
            raise ValueError("cannot set cancel_action without thread_action")
        super().__init__()
        self.log_name = log_name

        self._thread_action = thread_action
        self._collect_action = collect_action
        self._cancel_action = cancel_action
        self._wait_ready = wait_ready

        self._thread: Optional[Thread] = None

        self._intermediate_result: Any

        self._state = _OperationState.NEW
        self._lock = threading.Lock()

    def access_thread(self) -> Optional[Thread]:
        with self._lock:
            if self._thread is None:
                if self._thread_action is None:
                    return None
                self._thread = Thread(
                    target=self._run_thread_action,
                    name=self.log_name,
                )
                # this also starts the thread right away
                self._thread.start()
            return self._thread

    def _run_thread_action(self) -> None:
        assert not hasattr(self, "_intermediate_result")
        assert self._thread_action is not None
        logger.debug(f"thread[{self.log_name}]: call action")
        result = self._thread_action()
        with self._lock:
            assert not hasattr(self, "_intermediate_result")
            self._intermediate_result = result
        logger.debug(f"thread[{self.log_name}]: action completed ({result})")

    def start(self) -> None:
        with self._lock:
            assert self._state == _OperationState.NEW
            self._state = _OperationState.STARTING
        self.access_thread()
        self._start_wait_ready()

    def _start_wait_ready(self) -> None:
        with self._lock:
            if self._state.value > _OperationState.STARTING.value:
                return
            assert self._state == _OperationState.STARTING
        if self._wait_ready is not None:
            self._wait_ready()
        with self._lock:
            if self._state == _OperationState.STARTING:
                self._state = _OperationState.RUNNING

    def _cancel(self) -> None:
        if self._cancel_action is None:
            return
        logger.debug(f"thread[{self.log_name}]: cancel thread")
        self._cancel_action()
        logger.debug(f"thread[{self.log_name}]: cancel thread done")

    def finish(self, timeout: Optional[float] = None) -> BaseOutput:
        th = self.access_thread()
        if th is not None:
            with self._lock:
                assert self._state in (
                    _OperationState.STARTING,
                    _OperationState.RUNNING,
                )
                self._state = _OperationState.STOPPING
            t1 = timeout
            if self._cancel_action is not None:
                t1 = 0
            th.join(t1)
            if th.is_alive():
                # Abort and try to join again.
                if self._cancel_action is not None:
                    self._cancel()
                    th.join(timeout)
                if th.is_alive():
                    logger.error(
                        f"thread[{self.log_name}] did not terminate within the timeout {timeout}"
                    )

        result: Optional[BaseOutput] = None

        intermediate_result: Any

        with self._lock:
            if th is not None:
                assert self._state == _OperationState.STOPPING
                self._state = _OperationState.STOPPED
            else:
                assert self._state in (
                    _OperationState.STARTING,
                    _OperationState.RUNNING,
                )
                self._state = _OperationState.STOPPED

            if self._thread_action is None:
                intermediate_result = None
            elif not hasattr(self, "_intermediate_result"):
                # This really can only happen if we failed to join the thread.
                logger.error(f"thread[{self.log_name}] no result form thread received")
                result = BaseOutput(success=False, msg="failure to get thread result")
            else:
                intermediate_result = self._intermediate_result

        if result is not None:
            pass
        elif self._collect_action is None:
            assert self._thread_action
            result = intermediate_result
        elif self._thread_action:
            cb1 = typing.cast(Callable[[Any], BaseOutput], self._collect_action)
            result = cb1(intermediate_result)
        else:
            cb2 = typing.cast(Callable[[], BaseOutput], self._collect_action)
            result = cb2()

        assert isinstance(result, BaseOutput)

        logger.debug(f"thread[{self.log_name}]: got result {result}")
        return result


class Task(ABC):
    def __init__(
        self, ts: TestSettings, index: int, node_name: str, tenant: bool
    ) -> None:
        self.in_file_template = ""
        self.out_file_yaml = ""
        self.pod_name = ""
        self._setup_operation: Optional[TaskOperation] = None
        self._task_operation: Optional[TaskOperation] = None
        self._result: Optional[BaseOutput] = None
        self.lh = host.local
        self.index = index
        self.node_name = node_name
        self.tenant = tenant
        self.ts = ts
        self.tc = ts.cfg_descr.tc

        if not self.tenant and self.tc.mode == ClusterMode.SINGLE:
            raise ValueError("Cannot have non-tenant Task when cluster mode is single")

    @property
    def log_name(self) -> str:
        return self.__class__.__name__

    @property
    def log_name_setup(self) -> str:
        return f"{self.log_name}.setup"

    def get_namespace(self) -> str:
        return self.ts.cfg_descr.get_tft().namespace

    def get_duration(self) -> int:
        return self.ts.cfg_descr.get_tft().duration

    def get_template_args(self) -> dict[str, str]:
        return {
            "name_space": self.get_namespace(),
            "test_image": tftbase.TFT_TOOLS_IMG,
            "command": "/sbin/init",
            "args": "",
            "index": f"{self.index}",
            "node_name": self.node_name,
        }

    def render_file(
        self,
        log_info: str,
        in_file_template: Optional[str] = None,
        out_file_yaml: Optional[str] = None,
        template_args: Optional[dict[str, str]] = None,
    ) -> None:
        if in_file_template is None:
            in_file_template = self.in_file_template
        if out_file_yaml is None:
            out_file_yaml = self.out_file_yaml
        if template_args is None:
            template_args = self.get_template_args()
        logger.info(
            f'Generate {log_info} "{out_file_yaml}" (from "{in_file_template}")'
        )
        common.j2_render(in_file_template, out_file_yaml, template_args)

    def initialize(self) -> None:
        pass

    def run_oc(
        self,
        cmd: str,
        *,
        may_fail: bool = False,
        die_on_error: bool = False,
        namespace: Optional[str] | common._MISSING_TYPE = common.MISSING,
    ) -> host.Result:
        if isinstance(namespace, common._MISSING_TYPE):
            # By default, set use self.get_namespace(). You can select another
            # namespace or no namespace (by setting to None).
            namespace = self.get_namespace()
        return self.tc.client(tenant=self.tenant).oc(
            cmd,
            may_fail=may_fail,
            die_on_error=die_on_error,
            namespace=namespace,
        )

    def run_oc_exec(
        self,
        cmd: str | Iterable[str],
        *,
        may_fail: bool = False,
        die_on_error: bool = False,
        namespace: Optional[str] | common._MISSING_TYPE = common.MISSING,
    ) -> host.Result:
        if isinstance(cmd, str):
            argv = shlex.split(cmd)
        else:
            argv = list(cmd)
        return self.run_oc(
            f"exec {shlex.quote(self.pod_name)} -- {shlex.join(argv)}",
            may_fail=may_fail,
            die_on_error=die_on_error,
            namespace=namespace,
        )

    def get_pod_ip(self) -> str:
        r = self.run_oc(f"get pod {self.pod_name} -o yaml", die_on_error=True)
        y = yaml.safe_load(r.out)
        return typing.cast(str, y["status"]["podIP"])

    def create_cluster_ip_service(self) -> str:
        in_file_template = "./manifests/svc-cluster-ip.yaml.j2"
        out_file_yaml = "./manifests/yamls/svc-cluster-ip.yaml"

        self.render_file("Cluster IP Service", in_file_template, out_file_yaml)
        r = self.run_oc(f"apply -f {out_file_yaml}", may_fail=True)
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-clusterip-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def create_node_port_service(self, nodeport: int) -> str:
        in_file_template = "./manifests/svc-node-port.yaml.j2"
        out_file_yaml = "./manifests/yamls/svc-node-port.yaml"

        template_args = {
            **self.get_template_args(),
            "nodeport_svc_port": f"{nodeport}",
        }

        self.render_file(
            "Node Port Service", in_file_template, out_file_yaml, template_args
        )
        r = self.run_oc(f"apply -f {out_file_yaml}", may_fail=True)
        if r.returncode != 0:
            if "already exists" not in r.err:
                logger.error(r)
                sys.exit(-1)

        return self.run_oc(
            "get service tft-nodeport-service -o=jsonpath='{.spec.clusterIP}'"
        ).out

    def start_setup(self) -> None:
        assert self._setup_operation is None
        self._setup_operation = self._create_setup_operation()
        if self._setup_operation is not None:
            self._setup_operation.start()

    def _create_setup_operation(self) -> Optional[TaskOperation]:
        self.setup_pod()
        return None

    def finish_setup(self) -> None:
        if self._setup_operation is None:
            return
        to = self._setup_operation
        self._setup_operation = None
        to.finish(timeout=5)

    def setup_pod(self) -> None:
        # Check if pod already exists
        r = self.run_oc(f"get pod {self.pod_name} --output=json", may_fail=True)
        if r.returncode != 0:
            # otherwise create the pod
            logger.info(f"Creating Pod {self.pod_name}.")
            r = self.run_oc(f"apply -f {self.out_file_yaml}", die_on_error=True)
        else:
            logger.info(f"Pod {self.pod_name} already exists.")

        logger.info(f"Waiting for Pod {self.pod_name} to become ready.")
        r = self.run_oc(
            f"wait --for=condition=ready pod/{self.pod_name} --timeout=1m",
            die_on_error=True,
        )

    def start_task(self) -> None:
        assert self._task_operation is None
        self._task_operation = self._create_task_operation()
        if self._task_operation:
            self._task_operation.start()

    def _create_task_operation(self) -> Optional[TaskOperation]:
        return None

    def finish_task(self) -> None:
        if self._task_operation is None:
            return
        assert self._result is None
        logger.info(f"Completing execution on {self.log_name}")
        self._result = self._task_operation.finish(timeout=self.get_duration() * 1.5)

    def aggregate_output(self, out: tftbase.TftAggregateOutput) -> None:
        if self._result is None:
            return
        if not isinstance(self._result, tftbase.AggregatableOutput):
            # This output has nothing to collect. We are done.
            return

        self._aggregate_output(self._result, out)

    def _aggregate_output(
        self,
        result: tftbase.AggregatableOutput,
        out: tftbase.TftAggregateOutput,
    ) -> None:
        # This should never happen.
        #
        # A task that returns an AggregatableOutput *must* implement _aggregate_output().
        raise RuntimeError(
            f"Task {self.log_name} should not be called to aggregate output {result} "
        )


class PluginTask(Task):
    @property
    @abstractmethod
    def plugin(self) -> Plugin:
        pass
