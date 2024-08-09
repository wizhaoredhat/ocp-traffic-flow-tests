import dataclasses
import threading
import typing

from ktoolbox import common

import testConfig
import tftbase

from tftbase import NodeLocation
from tftbase import PodInfo
from tftbase import TestMetadata


@common.strict_dataclass
@dataclasses.dataclass(frozen=True, kw_only=True)
class TestSettings:
    """TestSettings will handle determining the logic require to configure the client/server for a given test"""

    cfg_descr: testConfig.ConfigDescriptor
    conf_server: testConfig.ConfServer
    conf_client: testConfig.ConfClient
    instance_index: int
    reverse: bool

    event_server_alive: threading.Event = dataclasses.field(
        init=False, default_factory=threading.Event
    )

    event_client_finished: threading.Event = dataclasses.field(
        init=False, default_factory=threading.Event
    )

    def _post_check(self) -> None:
        # As threading.Lock is not a regular type, @strict_dataclass
        # cannot handle fields of it. Set the attribute here.
        self._lock: threading.Lock
        object.__setattr__(self, "_lock", threading.Lock())

        # Check that the cfg_descr has a connection/test_case_id
        self.connection
        self.test_case_id

    @property
    def clmo_barrier(self) -> threading.Barrier:
        with self._lock:
            b = getattr(self, "_clmo_barrier", None)
            if b is None:
                raise RuntimeError(
                    "Cannot access the client-monitor barrier before calling initialize_clmo_barrier()"
                )
            return typing.cast(threading.Barrier, b)

    def initialize_clmo_barrier(self, parties: int) -> None:
        with self._lock:
            if hasattr(self, "_clmo_barrier"):
                raise RuntimeError("initialize_clmo_barrier() can only be called once")

            b = threading.Barrier(parties=parties)

            # TestSettings is for the most part an immutable, frozen object.
            # Here we lie about it. We do initialize the _clmo_barrier only
            # during initialize_clmo_barrier().
            #
            # Note that clmo_barrier will raise an exception if called before
            # initializing it. So you will only ever see one instance of the
            # barrier that never changes. That almost counts as "immutable".
            object.__setattr__(self, "_clmo_barrier", b)

    @property
    def connection(self) -> testConfig.ConfConnection:
        return self.cfg_descr.get_connection()

    @property
    def test_case_id(self) -> tftbase.TestCaseType:
        return self.cfg_descr.get_test_case()

    @property
    def server_is_tenant(self) -> bool:
        # TODO: Handle Case when not tenant
        return True

    @property
    def client_is_tenant(self) -> bool:
        # TODO: Handle Case when not tenant
        return True

    @property
    def server_index(self) -> int:
        # TODO: Add task indexing
        return self.instance_index

    @property
    def client_index(self) -> int:
        # TODO: Add task indexing
        return self.instance_index

    @property
    def node_server_name(self) -> str:
        if tftbase.test_case_type_is_same_node(self.test_case_id):
            return self.conf_client.name
        else:
            return self.conf_server.name

    @property
    def server_pod_type(self) -> tftbase.PodType:
        return tftbase.test_case_type_to_server_pod_type(
            self.test_case_id,
            self.conf_server.pod_type,
        )

    @property
    def client_pod_type(self) -> tftbase.PodType:
        return tftbase.test_case_type_to_client_pod_type(
            self.test_case_id,
            self.conf_client.pod_type,
        )

    @property
    def connection_mode(self) -> tftbase.ConnectionMode:
        return tftbase.test_case_type_to_connection_mode(self.test_case_id)

    @property
    def nodeLocation(self) -> NodeLocation:
        return tftbase.test_case_type_get_node_location(self.test_case_id)

    def get_test_info(self) -> str:
        return f"""type={self.connection.test_type.name}, test-case={self.test_case_id.name}: {self.client_pod_type.name} pod to {self.connection_mode.name} to {self.server_pod_type.name} pod - {self.nodeLocation.name}
        Client Node: {self.conf_client.name}
            Tenant={self.client_is_tenant}
            Index={self.client_index}
        Server Node: {self.node_server_name}
            Exec Persistence: {self.conf_server.persistent}
            Tenant={self.server_is_tenant}
            Index={self.server_index}"""

    def get_test_str(self) -> str:
        direction = ""
        if self.reverse:
            direction = "-REV"
        return f"{self.test_case_id.name}-{self.client_pod_type.name}_TO_{self.connection_mode.name}_TO_{self.server_pod_type.name}-{self.nodeLocation.name}{direction}"

    def get_test_metadata(self) -> TestMetadata:
        return TestMetadata(
            tft_idx=self.cfg_descr.tft_idx,
            test_cases_idx=self.cfg_descr.test_cases_idx,
            connections_idx=self.cfg_descr.connections_idx,
            test_case_id=self.test_case_id,
            test_type=self.connection.test_type,
            reverse=self.reverse,
            server=PodInfo(
                name=self.node_server_name,
                pod_type=self.server_pod_type,
                is_tenant=self.server_is_tenant,
                index=self.client_index,
            ),
            client=PodInfo(
                name=self.conf_client.name,
                pod_type=self.client_pod_type,
                is_tenant=self.client_is_tenant,
                index=self.client_index,
            ),
        )
