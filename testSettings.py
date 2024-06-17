import testConfig
import tftbase

from tftbase import NodeLocation
from tftbase import PodInfo
from tftbase import TestMetadata


class TestSettings:
    """TestSettings will handle determining the logic require to configure the client/server for a given test"""

    def __init__(
        self,
        cfg_descr: testConfig.ConfigDescriptor,
        conf_server: testConfig.ConfServer,
        conf_client: testConfig.ConfClient,
        instance_index: int,
        reverse: bool = False,
    ):
        connection = cfg_descr.get_connection()
        test_case_id = cfg_descr.get_test_case()

        self.cfg_descr = cfg_descr
        self.connection = connection
        self.test_case_id = test_case_id
        self.conf_server = conf_server
        self.conf_client = conf_client
        # TODO: Handle Case when client is not tenant
        self.client_is_tenant = True
        self.server_is_tenant = True
        # TODO: Add task indexing
        self.server_index = instance_index
        self.client_index = instance_index
        self.reverse = reverse

        # Initialize derived attributes...

        if tftbase.test_case_type_is_same_node(self.test_case_id):
            self.node_server_name = self.conf_client.name
        else:
            self.node_server_name = self.conf_server.name

        self.server_pod_type = tftbase.test_case_type_to_server_pod_type(
            self.test_case_id,
            self.conf_server.pod_type,
        )

        self.client_pod_type = tftbase.test_case_type_to_client_pod_type(
            self.test_case_id,
            self.conf_client.pod_type,
        )

        self.connection_mode = tftbase.test_case_type_to_connection_mode(
            self.test_case_id
        )

        if tftbase.test_case_type_is_same_node(self.test_case_id):
            self.nodeLocation = NodeLocation.SAME_NODE
        else:
            self.nodeLocation = NodeLocation.DIFF_NODE

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
