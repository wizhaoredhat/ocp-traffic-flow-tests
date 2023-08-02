from common import TestCaseType, PodType, ConnectionMode

class TestSettings():
    """TestSettings will handle determining the logic require to configure the client/server for a given test"""
    def __init__(self, test_case_id: TestCaseType, node_server_name: str, node_client_name: str, server_pod_type: PodType, client_pod_type: PodType):
        self.test_ip = test_case_id
        self.node_server_name = self._determine_server_name(test_case_id, node_server_name, node_client_name)
        self.node_client_name = node_client_name
        self.server_pod_type = server_pod_type
        self.client_pod_type = client_pod_type
        self.connection_mode = self._test_id_to_connection_mode(test_case_id)
        self.server_is_persistent = self._server_test_to_persistent(test_case_id)
        self.client_is_tenant = True
        self.server_is_tenant = True
        #TODO: Add task indexing
        self.server_index = 0
        self.client_index = 0

    def get_test_info(self) -> str:
        test_type = ""
        if self.node_server_name == self.node_client_name:
            test_type = "SAME NODE"
        else:
            test_type = "DIFF NODE"

        return f"""TEST CONFIGURATION
        Test Case {self.test_ip}: {self.client_pod_type.name} pod to {self.connection_mode.name} to {self.server_pod_type.name} pod - {test_type}
        Client Node: {self.node_client_name}
            Tenant={self.client_is_tenant}
            Index={self.client_index}
        Server Node: {self.node_server_name}
            Exec Persistence: {self.server_is_persistent}
            Tenant={self.server_is_tenant}
            Index={self.server_index}
        """

    def _test_id_to_connection_mode(self, test_case_id) -> ConnectionMode:
        """The connection type will be used to determine what IP the client should direct traffic to"""
        if test_case_id in (5, 6, 7, 8, 17, 18, 19, 20):
            return ConnectionMode.CLUSTER_IP
        if test_case_id in (9, 10, 11, 12, 21, 22, 23, 24):
            return ConnectionMode.NODE_PORT_IP
        if test_case_id in (25, 26):
            return ConnectionMode.EXTERNAL_IP
        return ConnectionMode.POD_IP

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
