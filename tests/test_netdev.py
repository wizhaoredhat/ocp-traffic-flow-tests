import pytest
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

    ifnames = netdev.get_ifnames()
    for ifname in ifnames:
        ipl = netdev.ip_links(ifname=ifname)
        assert isinstance(ipl, list)
        assert len(ipl) == 1
        assert ipl[0].ifname == ifname


def test_ip_routes() -> None:
    # We expect to have at least one route configured on the system and that
    # `ip -json route` works. The unit test requires that.
    assert netdev.ip_routes(host.local)


def test_sysctl_phys_port_name_parse() -> None:
    assert netdev.sysctl_phys_port_name_parse("") is None
    assert netdev.sysctl_phys_port_name_parse("  555\n") == (0, 555)
    assert netdev.sysctl_phys_port_name_parse("  c1pf6vf55\n") == (6, 55)


def test_validate_pciaddr() -> None:
    assert netdev.validate_pciaddr(b"0000:ff:0a.7") == "0000:ff:0a.7"
    assert netdev.validate_pciaddr("0000:ff:0a.7") == "0000:ff:0a.7"
    with pytest.raises(Exception):
        netdev.validate_pciaddr(b"0000:ff:0a.7/")
    with pytest.raises(Exception):
        netdev.validate_pciaddr("0000:ff:0A.7")


def test_ifnames_and_pciaddrs() -> None:
    ifnames = netdev.get_ifnames()
    assert isinstance(ifnames, list)
    assert all(isinstance(i, str) for i in ifnames)
    assert "lo" in ifnames

    pciaddrs = netdev.get_pciaddrs()
    assert isinstance(pciaddrs, list)
    assert all(isinstance(i, str) for i in pciaddrs)

    ifname_to_pci: dict[str, str] = {}
    pci_to_ifname: dict[str, str] = {}

    for ifname1 in ifnames:
        pciaddr = netdev.get_pciaddr_from_ifname(ifname1)
        if pciaddr is not None:
            assert pciaddr in pciaddrs
            assert ifname1 in (netdev.get_ifnames_from_pciaddr(pciaddr) or ())
            ifname_to_pci[ifname1] = pciaddr

    for pci in pciaddrs:
        ifnames2 = netdev.get_ifnames_from_pciaddr(pci)
        if ifnames2 is not None:
            for ifname2 in ifnames2:
                assert ifname2 in ifnames
                assert netdev.get_pciaddr_from_ifname(ifname2) == pci
                pci_to_ifname[pci] = ifname2

    assert {v: k for k, v in pci_to_ifname.items()} == ifname_to_pci
    assert {v: k for k, v in ifname_to_pci.items()} == pci_to_ifname


def test_get_device_infos() -> None:
    result = netdev.get_device_infos()
    assert isinstance(result, list)
    assert "lo" in [x.get("ifname") for x in result]
