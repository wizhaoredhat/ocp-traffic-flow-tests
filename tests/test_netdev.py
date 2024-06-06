import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import host  # noqa: E402
import netdev  # noqa: E402


def test_ip_addrs() -> None:
    # We expect to have at least one address configured on the system and that
    # `ip -json addr` works. The unit test requires that.
    assert netdev.ip_addrs(host.local)


def test_ip_links() -> None:
    links = netdev.ip_links(host.local)
    assert links
    assert [link.ifindex for link in links if link.ifname == "lo"] == [1]

    assert [link.ifindex for link in netdev.ip_links(host.local, ifname="lo")] == [1]


def test_ip_routes() -> None:
    # We expect to have at least one route configured on the system and that
    # `ip -json route` works. The unit test requires that.
    assert netdev.ip_routes(host.local)
