import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pluginValidateOffload  # noqa: E402


def test_ethtool_parse_stat() -> None:

    assert pluginValidateOffload.ethtool_stat_parse("") == {}

    data = """NIC statistics:
     tx_packets: 2537925
     rx_packets: 5645343
     tx_errors: 0
     rx_errors: 0
     rx_missed: 0
     align_errors: 0
     tx_single_collisions: 0
     tx_multi_collisions: 0
     rx_unicast: 5373570
     rx_broadcast: 226191
     rx_multicast: 45582
     tx_aborted: 0
     tx_underrun: 0
"""
    expected_d = {
        "tx_packets": "2537925",
        "rx_packets": "5645343",
        "tx_errors": "0",
        "rx_errors": "0",
        "rx_missed": "0",
        "align_errors": "0",
        "tx_single_collisions": "0",
        "tx_multi_collisions": "0",
        "rx_unicast": "5373570",
        "rx_broadcast": "226191",
        "rx_multicast": "45582",
        "tx_aborted": "0",
        "tx_underrun": "0",
    }

    d = pluginValidateOffload.ethtool_stat_parse(data)
    assert d == expected_d
    assert list(d) == list(expected_d)

    assert pluginValidateOffload.ethtool_stat_get_packets(d, "tx") == 2537925
    assert pluginValidateOffload.ethtool_stat_get_packets(d, "rx") == 5645343
    assert pluginValidateOffload.ethtool_stat_get_packets(d, "foo") is None

    res: dict[str, int] = {}
    assert pluginValidateOffload.ethtool_stat_get_startend(res, data, "start")
    assert res == {
        "rx_start": 5645343,
        "tx_start": 2537925,
    }
    assert pluginValidateOffload.ethtool_stat_get_startend(res, data, "end")
    assert res == {
        "rx_start": 5645343,
        "tx_start": 2537925,
        "rx_end": 5645343,
        "tx_end": 2537925,
    }
