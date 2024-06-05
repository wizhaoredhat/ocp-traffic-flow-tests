import testConfig
import tftbase

from tftbase import NodeLocation
from tftbase import PodInfo
from tftbase import PodType
from tftbase import TestCaseType
from tftbase import TestMetadata


class TestSettings:
    """TestSettings will handle determining the logic require to configure the client/server for a given test"""

    def __init__(
        self,
        connection: testConfig.ConfConnection,
        test_case_id: TestCaseType,
        conf_server: testConfig.ConfServer,
        conf_client: testConfig.ConfClient,
        instance_index: int,
        reverse: bool = False,
    ):
        self.connection = connection
        self.test_case_id = test_case_id
        self.conf_server = conf_server
        self.conf_client = conf_client
        self.node_server_name = self._determine_server_name(
            test_case_id, conf_server.name, conf_client.name
        )
        self.server_pod_type = tftbase.test_case_type_to_server_pod_type(
            test_case_id,
            conf_server.pod_type,
        )
        self.client_pod_type = self.client_test_to_pod_type(
            test_case_id,
            conf_client.pod_type,
        )
        # TODO: Handle Case when client is not tenant
        self.client_is_tenant = True
        self.server_is_tenant = True
        # TODO: Add task indexing
        self.server_index = instance_index
        self.client_index = instance_index
        self.reverse = reverse

        # Derive params from test_case_id
        self.connection_mode = tftbase.test_case_type_to_connection_mode(test_case_id)
        if tftbase.test_case_type_is_same_node(test_case_id):
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

    @staticmethod
    def _determine_server_name(
        test_case_id: TestCaseType,
        node_server_name: str,
        node_client_name: str,
    ) -> str:
        """If conducting Same Node testing, the server node should be the client node"""
        if tftbase.test_case_type_is_same_node(test_case_id):
            return node_client_name
        return node_server_name

    @staticmethod
    def client_test_to_pod_type(
        test_id: TestCaseType,
        cfg_pod_type: PodType,
    ) -> PodType:
        if (
            test_id.value >= TestCaseType.HOST_TO_HOST_SAME_NODE.value
            and test_id.value <= TestCaseType.HOST_TO_EXTERNAL.value
        ):
            return PodType.HOSTBACKED

        if cfg_pod_type == PodType.SRIOV:
            return PodType.SRIOV

        return PodType.NORMAL
