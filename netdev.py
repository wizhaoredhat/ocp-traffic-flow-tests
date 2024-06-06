from dataclasses import dataclass
from typing import Optional

import host
import common

from common import strict_dataclass


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class IPRouteAddressInfoEntry:
    family: str
    local: str

    def _post_check(self) -> None:
        if not isinstance(self.family, str) or self.family not in ("inet", "inet6"):
            raise ValueError("Invalid address family")


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class IPRouteAddressEntry:
    ifindex: int
    ifname: str
    flags: tuple[str, ...]
    master: Optional[str]
    address: str  # Ethernet address.
    addr_info: tuple[IPRouteAddressInfoEntry, ...]

    def has_carrier(self) -> bool:
        return "NO-CARRIER" not in self.flags


def ip_addrs_parse(
    jstr: str,
    *,
    strict_parsing: bool = False,
    ifname: Optional[str] = None,
) -> list[IPRouteAddressEntry]:
    ret: list[IPRouteAddressEntry] = []
    for e in common.json_parse_list(jstr, strict_parsing=strict_parsing):
        try:
            entry = IPRouteAddressEntry(
                ifindex=e["ifindex"],
                ifname=e["ifname"],
                flags=tuple(e["flags"]),
                master=e["master"] if "master" in e else None,
                address=e["address"],
                addr_info=tuple(
                    IPRouteAddressInfoEntry(
                        family=addr["family"],
                        local=addr["local"],
                    )
                    for addr in e["addr_info"]
                ),
            )
        except (KeyError, ValueError, TypeError):
            if strict_parsing:
                raise
            continue

        if ifname is not None and normalize_ifname(ifname) != normalize_ifname(
            entry.ifname
        ):
            continue
        ret.append(entry)
    return ret


def ip_addrs(
    rsh: Optional[host.Host] = None,
    *,
    strict_parsing: bool = False,
    ifname: Optional[str] = None,
    ip_log_level: int = -1,
) -> list[IPRouteAddressEntry]:
    rsh = host.host_or_local(rsh)
    ret = rsh.run(
        "ip -json addr",
        decode_errors="surrogateescape",
        log_level=ip_log_level,
    )
    if not ret.success:
        if strict_parsing:
            raise RuntimeError(f"calling ip-route on {rsh.pretty_str()} failed ({ret})")
        return []

    return ip_addrs_parse(ret.out, strict_parsing=strict_parsing, ifname=ifname)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class IPRouteLinkEntry:
    ifindex: int
    ifname: str
    flags: tuple[str, ...]
    mtu: int
    operstate: str
    link_info_kind: Optional[str]


def ip_links_parse(
    jstr: str, *, strict_parsing: bool = False, ifname: Optional[str] = None
) -> list[IPRouteLinkEntry]:
    ret: list[IPRouteLinkEntry] = []
    for e in common.json_parse_list(jstr, strict_parsing=strict_parsing):
        try:

            link_info_kind: Optional[str] = None
            link_info = e.get("linkinfo")
            if link_info is not None:
                link_info_kind = link_info.get("info_kind")

            entry = IPRouteLinkEntry(
                ifindex=e["ifindex"],
                ifname=e["ifname"],
                mtu=int(e["mtu"]),
                flags=tuple(e["flags"]),
                operstate=(e["operstate"]),
                link_info_kind=link_info_kind,
            )
        except (KeyError, ValueError, TypeError):
            if strict_parsing:
                raise
            continue

        if ifname is not None and normalize_ifname(ifname) != normalize_ifname(
            entry.ifname
        ):
            continue
        ret.append(entry)
    return ret


def ip_links(
    rsh: Optional[host.Host] = None,
    *,
    strict_parsing: bool = False,
    ifname: Optional[str] = None,
    ip_log_level: int = -1,
) -> list[IPRouteLinkEntry]:
    # If @ifname is requested, we could issue a `ip -json link show $IFNAME`. However,
    # that means we do different things for requesting one link vs. all links. That
    # seems undesirable. Instead, in all cases fetch all links. Any filtering then happens
    # in code that we control. Performance should not make a difference, since the JSON data
    # is probably small anyway (compared to the overhead of invoking a shell command).
    rsh = host.host_or_local(rsh)
    ret = rsh.run(
        "ip -json -d link",
        decode_errors="surrogateescape",
        log_level=ip_log_level,
    )
    if not ret.success:
        if strict_parsing:
            raise RuntimeError(f"calling ip-link on {rsh.pretty_str()} failed ({ret})")
        return []

    return ip_links_parse(ret.out, strict_parsing=strict_parsing, ifname=ifname)


@strict_dataclass
@dataclass(frozen=True, kw_only=True)
class IPRouteRouteEntry:
    dst: str
    dev: str


def ip_routes_parse(
    jstr: str,
    *,
    strict_parsing: bool = False,
) -> list[IPRouteRouteEntry]:
    ret: list[IPRouteRouteEntry] = []
    for e in common.json_parse_list(jstr, strict_parsing=strict_parsing):
        try:
            entry = IPRouteRouteEntry(
                dst=e["dst"],
                dev=e["dev"],
            )
        except (KeyError, ValueError, TypeError):
            if strict_parsing:
                raise
            continue

        ret.append(entry)
    return ret


def ip_routes(
    rsh: Optional[host.Host] = None,
    *,
    strict_parsing: bool = False,
    ip_log_level: int = -1,
) -> list[IPRouteRouteEntry]:
    rsh = host.host_or_local(rsh)
    ret = rsh.run(
        "ip -json route",
        decode_errors="surrogateescape",
        log_level=ip_log_level,
    )
    if not ret.success:
        if strict_parsing:
            raise RuntimeError(f"calling ip-route on {rsh.pretty_str()} failed ({ret})")
        return []

    return ip_routes_parse(ret.out, strict_parsing=strict_parsing)


def normalize_ifname(ifname: str | bytes) -> bytes:
    if isinstance(ifname, str):
        ifname = ifname.encode("utf-8", errors="surrogateescape")
    elif not isinstance(ifname, bytes):
        raise TypeError(f"Unexpected ifname of type {type(ifname)}")
    return ifname
