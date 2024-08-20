from . import firewall


def test_nft_cmd_masquerade() -> None:
    assert (
        firewall.nft_data_masquerade_down(table_name="foo")
        == """add table ip foo
delete table ip foo
"""
    )
    assert (
        firewall.nft_data_masquerade_up(
            table_name="foo",
            subnet="191.168.5.0/24",
            ifname="eno4",
        )
        == """add table ip foo
flush table ip foo
add chain ip foo nat_postrouting { type nat hook postrouting priority 100; policy accept; };
add rule ip foo nat_postrouting ip saddr 191.168.5.0/24 ip daddr != 191.168.5.0/24 masquerade;
add chain ip foo filter_forward { type filter hook forward priority 0; policy accept; };
add rule ip foo filter_forward ip daddr 191.168.5.0/24 oifname "eno4"  ct state { established, related } accept;
add rule ip foo filter_forward ip saddr 191.168.5.0/24 iifname "eno4" accept;
add rule ip foo filter_forward iifname "eno4" oifname "eno4" accept;
add rule ip foo filter_forward iifname "eno4" reject;
add rule ip foo filter_forward oifname "eno4" reject;
"""
    )
