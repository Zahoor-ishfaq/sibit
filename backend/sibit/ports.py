"""Cisco port, protocol and ICMP-type names -> numbers.

Single source of truth for name resolution on both the ASA and FTD side.
Protocol-specific values matter: ``syslog`` is UDP 514 while ``rsh`` is TCP 514.

The spec table (section 2.3) is authoritative; the remaining entries are the
standard Cisco ASA literal names so real configs resolve without warnings.
"""
from __future__ import annotations

# Names valid for both TCP and UDP (spec 2.3 + ASA literals).
_BOTH: dict[str, int] = {
    "echo": 7,
    "discard": 9,
    "daytime": 13,
    "domain": 53,
    "tacacs": 49,
    "www": 80,
    "http": 80,
    "kerberos": 88,  # spec 2.3 (ASA's own literal is 750; override in Settings if needed)
    "sunrpc": 111,
    "netbios-ns": 137,
    "netbios-dgm": 138,
    "netbios-ssn": 139,
    "snmp": 161,
    "snmptrap": 162,
    "ldap": 389,
    "https": 443,
    "isakmp": 500,
    "talk": 517,
    "rtsp": 554,
    "ldaps": 636,
    "sqlnet": 1521,
    "h323": 1720,
    "nfs": 2049,
    "cifs": 3020,
    "sip": 5060,
    "ntp": 123,
    "bootps": 67,
    "bootpc": 68,
    "tftp": 69,
    "pop3": 110,
    "imap4": 143,
    "smtp": 25,
    "ftp": 21,
    "ftp-data": 20,
    "ssh": 22,
    "telnet": 23,
    "pim-auto-rp": 496,
    "nameserver": 42,
    "mobile-ip": 434,
    "radius": 1645,
    "radius-acct": 1646,
    "secureid-udp": 5510,
    "vxlan": 4789,
    "lotusnotes": 1352,
    "pptp": 1723,
    "citrix-ica": 1494,
    "ctiqbe": 2748,
    "aol": 5190,
    "bgp": 179,
    "chargen": 19,
    "finger": 79,
    "gopher": 70,
    "hostname": 101,
    "ident": 113,
    "irc": 194,
    "klogin": 543,
    "kshell": 544,
    "lpd": 515,
    "nntp": 119,
    "pcanywhere-data": 5631,
    "pcanywhere-status": 5632,
    "pop2": 109,
    "time": 37,
    "uucp": 540,
    "whois": 43,
    "xdmcp": 177,
    "dnsix": 195,
    "rip": 520,
}

# Protocol-specific names. Where a name exists in both tables, the
# protocol-specific value wins for that protocol.
_TCP_ONLY: dict[str, int] = {
    "exec": 512,
    "rsh": 514,
    "cmd": 514,
    "login": 513,
}
_UDP_ONLY: dict[str, int] = {
    "syslog": 514,
    "biff": 512,
    "who": 513,
}

PROTOCOLS: dict[str, int] = {
    "ip": 0,
    "icmp": 1,
    "igmp": 2,
    "ipinip": 4,
    "tcp": 6,
    "igrp": 9,
    "udp": 17,
    "gre": 47,
    "esp": 50,
    "ipsec": 50,
    "ah": 51,
    "icmp6": 58,
    "eigrp": 88,
    "ospf": 89,
    "nos": 94,
    "pim": 103,
    "pcp": 108,
    "snp": 109,
    "sctp": 132,
}
# Reverse map used to canonicalise numeric protocols ("6" -> "tcp").
PROTO_BY_NUMBER: dict[int, str] = {
    1: "icmp",
    6: "tcp",
    17: "udp",
    58: "icmp6",
    47: "gre",
    50: "esp",
    51: "ah",
    88: "eigrp",
    89: "ospf",
    103: "pim",
    2: "igmp",
    4: "ipinip",
    9: "igrp",
    94: "nos",
    108: "pcp",
    109: "snp",
    132: "sctp",
}

ICMP_TYPES: dict[str, int] = {
    "echo-reply": 0,
    "unreachable": 3,
    "source-quench": 4,
    "redirect": 5,
    "alternate-address": 6,
    "echo": 8,
    "router-advertisement": 9,
    "router-solicitation": 10,
    "time-exceeded": 11,
    "parameter-problem": 12,
    "timestamp-request": 13,
    "timestamp-reply": 14,
    "information-request": 15,
    "information-reply": 16,
    "mask-request": 17,
    "mask-reply": 18,
    "traceroute": 30,
    "conversion-error": 31,
    "mobile-redirect": 32,
}

ICMP6_TYPES: dict[str, int] = {
    "unreachable": 1,
    "packet-too-big": 2,
    "time-exceeded": 3,
    "parameter-problem": 4,
    "echo": 128,
    "echo-reply": 129,
    "membership-query": 130,
    "membership-report": 131,
    "membership-reduction": 132,
    "router-solicitation": 133,
    "router-advertisement": 134,
    "neighbor-solicitation": 135,
    "neighbor-advertisement": 136,
    "neighbor-redirect": 137,
    "router-renumbering": 138,
}

PORT_MIN = 1
PORT_MAX = 65535


class PortResolver:
    """Resolves port names per protocol, honouring user overrides.

    ``overrides`` maps ``name`` or ``proto/name`` (e.g. ``tcp/kerberos``) to a
    port number, and takes precedence over the built-in tables.
    """

    def __init__(self, overrides: dict[str, int] | None = None) -> None:
        self.overrides = {k.lower(): int(v) for k, v in (overrides or {}).items()}

    def port(self, name: str, proto: str) -> int | None:
        """Return the port number for ``name`` under ``proto`` (tcp/udp), or None."""
        n = name.strip().lower()
        if n.isdigit():
            v = int(n)
            return v if 0 <= v <= PORT_MAX else None
        p = proto.lower()
        for key in (f"{p}/{n}", n):
            if key in self.overrides:
                return self.overrides[key]
        if p == "tcp" and n in _TCP_ONLY:
            return _TCP_ONLY[n]
        if p == "udp" and n in _UDP_ONLY:
            return _UDP_ONLY[n]
        if n in _BOTH:
            return _BOTH[n]
        return None


def protocol_name(token: str) -> str | None:
    """Canonical protocol name for a Cisco protocol keyword or number.

    Returns ``"tcp"``, ``"udp"``, ``"icmp"``, ... or a bare number string for
    protocols without a well-known name. ``None`` if unrecognised.
    """
    t = token.strip().lower()
    if t.isdigit():
        n = int(t)
        if n == 0:
            return "ip"
        if 0 < n <= 255:
            return PROTO_BY_NUMBER.get(n, str(n))
        return None
    if t in ("tcp-udp", "ip"):
        return t
    if t == "ipsec":
        return "esp"
    if t in PROTOCOLS:
        return t
    return None


def icmp_type(token: str, proto: str = "icmp") -> int | None:
    t = token.strip().lower()
    if t.isdigit():
        v = int(t)
        return v if 0 <= v <= 255 else None
    table = ICMP6_TYPES if proto == "icmp6" else ICMP_TYPES
    return table.get(t)


def is_icmp_type_name(token: str, proto: str = "icmp") -> bool:
    table = ICMP6_TYPES if proto == "icmp6" else ICMP_TYPES
    return token.lower() in table
