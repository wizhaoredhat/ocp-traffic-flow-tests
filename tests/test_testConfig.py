import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import testConfig  # noqa: E402

from common import TestCaseType  # noqa: E402


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
