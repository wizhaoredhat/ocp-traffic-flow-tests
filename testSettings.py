from common import TestCaseType, PodType, ConnectionMode, NodeLocation, TestType

class TestSettings():
    """TestSettings will handle determining the logic require to configure the client/server for a given test"""
    def __init__(
            self, connection_name: str,
            test_case_id: TestCaseType,
            node_server_name: str,
            node_client_name: str,
            server_pod_type: str,
            client_pod_type: str,
            index: int,
            test_type: TestType,
            log_path: str
        ):
        self.connection_name = connection_name
        self.test_case_id = test_case_id
        self.node_server_name = self._determine_server_name(test_case_id, node_server_name, node_client_name)
        self.node_client_name = node_client_name
        self.server_pod_type = self.server_test_to_pod_type(test_case_id, server_pod_type)
        self.client_pod_type = self.client_test_to_pod_type(test_case_id, client_pod_type)
        #TODO: Handle Case when client is not tenant
        self.client_is_tenant = True
        self.server_is_tenant = True
        #TODO: Add task indexing
        self.server_index = index
        self.client_index = index
        self.test_type = test_type
        self.log_path = log_path

        # Derive params from test_case_id
        self.set_all_params_from_test_case_id(test_case_id)

    def set_all_params_from_test_case_id(self, test_case_id):
        self.connection_mode = self._test_id_to_connection_mode(test_case_id)
        self.server_is_persistent = self._server_test_to_persistent(test_case_id)
        if self._is_same_node_test(test_case_id):
            self.nodeLocation = NodeLocation.SAME_NODE
        else:
            self.nodeLocation = NodeLocation.DIFF_NODE

    def get_test_info(self) -> str:
        return f"""{self.test_type.name} TEST CONFIGURATION
        Test Case {self.test_case_id}: {self.client_pod_type.name} pod to {self.connection_mode.name} to {self.server_pod_type.name} pod - {self.nodeLocation.name}
        Client Node: {self.node_client_name}
            Tenant={self.client_is_tenant}
            Index={self.client_index}
        Server Node: {self.node_server_name}
            Exec Persistence: {self.server_is_persistent}
            Tenant={self.server_is_tenant}
            Index={self.server_index}
        """

    def get_test_str(self) -> str:
        return f"{self.test_case_id}-{self.client_pod_type.name}_TO_{self.connection_mode.name}_TO_{self.server_pod_type.name}-{self.nodeLocation.name}"

    def _test_id_to_connection_mode(self, test_case_id) -> ConnectionMode:
        """The connection type will be used to determine what IP the client should direct traffic to"""
        if test_case_id in (5, 6, 7, 8, 17, 18, 19, 20):
            return ConnectionMode.CLUSTER_IP
        if test_case_id in (9, 10, 11, 12, 21, 22, 23, 24):
            return ConnectionMode.NODE_PORT_IP
        if test_case_id in (25, 26):
            return ConnectionMode.EXTERNAL_IP
        return ConnectionMode.POD_IP

    def get_test_info_dict(self) -> dict:
        json_dump = {
            "test_case_id": TestCaseType(self.test_case_id).name,
            "test_type": self.test_type.name,
            "server": {
                "name": self.node_server_name,
                "pod_type": self.server_pod_type.name,
                "is_tenant": self.server_is_tenant,
                "index": self.server_index,
            },
            "client": {
                "name": self.node_client_name,
                "pod_type": self.client_pod_type.name,
                "is_tenant": self.client_is_tenant,
                "index": self.client_index
            },    
        }
        return json_dump

    def _determine_server_name(self, test_case_id: TestCaseType, node_server_name: str, node_client_name: str):
        """If conducting Same Node testing, the server node should be the client node"""
        if self._is_same_node_test(test_case_id):
            return node_client_name
        return node_server_name

    def _is_same_node_test(self, test_id: int) -> bool:
        return test_id in (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23)

    def _server_test_to_persistent(self, test_id: int) -> bool:
        #TODO: add logic to determine when this is required
        return False

    def server_test_to_pod_type(self, test_id: int, cfg_pod_type: str) -> PodType:
        if test_id in (3, 4, 7, 8, 19, 20, 23, 24):
            return PodType.HOSTBACKED

        if cfg_pod_type == "sriov":
            return PodType.SRIOV

        return PodType.NORMAL

    def client_test_to_pod_type(self, test_id: int, cfg_pod_type: str) -> PodType:
        if test_id in range(13, 25) or test_id == 26:
            return PodType.HOSTBACKED

        if cfg_pod_type == "sriov":
            return PodType.SRIOV

        return PodType.NORMAL
