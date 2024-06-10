import dataclasses

import common
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

    def _post_check(self) -> None:
        # Check that the cfg_descr has a connection/test_case_id
        self.connection
        self.test_case_id

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
        return f"""{self.connection.test_type.name} TEST CONFIGURATION
        Test Case {self.test_case_id}: {self.client_pod_type.name} pod to {self.connection_mode.name} to {self.server_pod_type.name} pod - {self.nodeLocation.name}
        Client Node: {self.conf_client.name}
            Tenant={self.client_is_tenant}
            Index={self.client_index}
        Server Node: {self.node_server_name}
            Exec Persistence: {self.conf_server.persistent}
            Tenant={self.server_is_tenant}
            Index={self.server_index}
        """

    def get_test_str(self) -> str:
        direction = ""
        if self.reverse:
            direction = "-REV"
        return f"{self.test_case_id}-{self.client_pod_type.name}_TO_{self.connection_mode.name}_TO_{self.server_pod_type.name}-{self.nodeLocation.name}{direction}"

    def get_test_metadata(self) -> TestMetadata:
        return TestMetadata(
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
