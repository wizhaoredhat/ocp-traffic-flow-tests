import sys
import os
import yaml

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import common  # noqa: E402
import testConfig  # noqa: E402
import tftbase  # noqa: E402

from tftbase import TestCaseType  # noqa: E402
from tftbase import TestType  # noqa: E402


testConfigModeArgs1 = (tftbase.ClusterMode.SINGLE, "/root/kubeconfig.x1", None)


def test_parse_test_cases() -> None:
    def _t(input_str: str) -> list[TestCaseType]:
        return testConfig.TestConfig.parse_test_cases(input_str)

    assert _t("1,2,3,6") == [
        TestCaseType.POD_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
    ]
    assert _t("1,2,POD_TO_HOST_SAME_NODE,6") == [
        TestCaseType.POD_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
    ]

    assert _t("1-9,15-19") == [
        TestCaseType.POD_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_HOST_DIFF_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE,
        TestCaseType.POD_TO_NODE_PORT_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE,
    ]
    assert _t("POD_TO_POD_SAME_NODE-9,15-19") == [
        TestCaseType.POD_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_HOST_DIFF_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_SAME_NODE,
        TestCaseType.POD_TO_CLUSTER_IP_TO_HOST_DIFF_NODE,
        TestCaseType.POD_TO_NODE_PORT_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE,
    ]

    all_cases = sorted(TestCaseType, key=lambda e: e.value)

    assert _t("*") == all_cases

    assert _t("2,*") == [
        TestCaseType.POD_TO_POD_DIFF_NODE,
        *all_cases,
    ]


def test_validate_test_type() -> None:
    def _t(input_str: str) -> TestType:
        return testConfig.TestConfig.validate_test_type({"type": input_str})

    assert _t("iperf-tcp") == TestType.IPERF_TCP
    assert _t("iperf-udp") == TestType.IPERF_UDP
    assert _t("IPERF_UDP") == TestType.IPERF_UDP
    assert _t("http ") == TestType.HTTP
    assert _t("HTTP") == TestType.HTTP


def test_config1() -> None:
    file = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    assert os.path.exists(file)

    tc = testConfig.TestConfig(config_path=file, mode_args=testConfigModeArgs1)
    assert isinstance(tc, testConfig.TestConfig)
    assert isinstance(tc.full_config, dict)
    assert list(tc.full_config.keys()) == ["tft"]

    assert tc.config.tft[0].name == "Test 1"
    assert tc.config.tft[0].connections[0].name == "Connection_1"

    assert tc.config.yamlpath == ""
    assert tc.config.tft[0].yamlpath == ".tft[0]"
    assert tc.config.tft[0].connections[0].yamlpath == ".tft[0].connections[0]"
    assert (
        tc.config.tft[0].connections[0].server[0].yamlpath
        == ".tft[0].connections[0].server[0]"
    )
    assert (
        tc.config.tft[0].connections[0].plugins[0].yamlpath
        == ".tft[0].connections[0].plugins[0]"
    )


def test_config2() -> None:
    full_config = yaml.safe_load(
        """
tft:
  - name: "Test 1"
    namespace: "default"
    test_cases:
      - "1"
      - 2
      - HOST_TO_POD_DIFF_NODE
      - HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE - HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE
    connections:
     - name: con1
       plugins:
         - name: measure_cpu
         - measure_power
"""
    )
    tc = testConfig.TestConfig(full_config=full_config, mode_args=testConfigModeArgs1)
    assert isinstance(tc, testConfig.TestConfig)

    assert tc.config.tft[0].test_cases == (
        TestCaseType(1),
        TestCaseType(2),
        TestCaseType.HOST_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_SAME_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_POD_DIFF_NODE,
        TestCaseType.HOST_TO_CLUSTER_IP_TO_HOST_SAME_NODE,
    )
    assert tc.config.tft[0].connections[0].plugins[0].name == "measure_cpu"
    assert (
        tc.config.tft[0].connections[0].plugins[0].plugin.PLUGIN_NAME == "measure_cpu"
    )
    assert tc.config.tft[0].connections[0].plugins[1].name == "measure_power"

    # A minimal yaml.
    full_config = yaml.safe_load(
        """
tft:
  - connections:
    - {}
"""
    )
    tc = testConfig.TestConfig(full_config=full_config, mode_args=testConfigModeArgs1)
    assert isinstance(tc, testConfig.TestConfig)
    assert tc.config.tft[0].name == "Test 1"
    assert tc.config.tft[0].namespace == "default"
    assert tc.config.tft[0].test_cases == tuple(
        common.enum_convert_list(TestCaseType, "*")
    )
    assert tc.config.tft[0].connections[0].name == "Connection Test 1/1"
