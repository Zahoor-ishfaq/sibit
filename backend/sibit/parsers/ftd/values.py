"""Literal value parsing for FTD network and port values."""
from __future__ import annotations

import re

from netaddr import AddrFormatError, IPAddress, IPNetwork, IPRange

from ...model import ServiceEntry
from ...ports import PORT_MAX, PORT_MIN, PROTO_BY_NUMBER, protocol_name

# 'TCP (6):22', 'UDP (17):1024-65535', 'TCP (6)', 'ICMP (1):8', 'ICMP (1):8:0', 'GRE (47)'
# Rules write 'TCP (6):22'; Referenced Objects write 'TCP (6)/22'.
_PORT_RE = re.compile(r"^(?P<pname>[A-Za-z][\w\-]*)?\s*\((?P<num>\d{1,3})\)\s*(?:[:/]\s*(?P<spec>.*))?$")
_RANGE_RE = re.compile(r"^(\d+)\s*(?:-\s*(\d+))?")
_INT_RE = re.compile(r"\d+")

# Well-known FMC system-defined objects, used only when a name is not found in
# the report's Referenced Objects section.
BUILTIN_NETWORKS: dict[str, list[str]] = {
    "any": ["0.0.0.0/0"],
    "any-ipv4": ["0.0.0.0/0"],
    "any-ipv6": ["::/0"],
    "IPv4-Private-10.0.0.0-8": ["10.0.0.0/8"],
    "IPv4-Private-172.16.0.0-12": ["172.16.0.0/12"],
    "IPv4-Private-192.168.0.0-16": ["192.168.0.0/16"],
    "IPv4-Private-All-RFC1918": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
    "IPv4-Link-Local": ["169.254.0.0/16"],
    "IPv4-Multicast": ["224.0.0.0/4"],
    "IPv4-Benchmark-Tests": ["198.18.0.0/15"],
    "IPv6-Link-Local": ["fe80::/10"],
}
BUILTIN_PORTS: dict[str, list[str]] = {
    "HTTP": ["TCP (6):80"],
    "HTTPS": ["TCP (6):443"],
    "SSH": ["TCP (6):22"],
    "TELNET": ["TCP (6):23"],
    "FTP": ["TCP (6):21"],
    "SMTP": ["TCP (6):25"],
    "SMTPS": ["TCP (6):465"],
    "POP-3": ["TCP (6):110"],
    "IMAP": ["TCP (6):143"],
    "DNS_over_TCP": ["TCP (6):53"],
    "DNS_over_UDP": ["UDP (17):53"],
    "NTP-TCP": ["TCP (6):123"],
    "NTP-UDP": ["UDP (17):123"],
    "SNMP": ["UDP (17):161-162"],
    "SYSLOG": ["UDP (17):514"],
    "LDAP": ["TCP (6):389"],
    "LDAPS": ["TCP (6):636"],
    "RADIUS": ["UDP (17):1812-1813"],
    "TFTP": ["UDP (17):69"],
    "MSSQL": ["TCP (6):1433"],
    "ORACLE": ["TCP (6):1521"],
    "RDP": ["TCP (6):3389"],
    "Kerberos": ["TCP (6):88", "UDP (17):88"],
    "ICMP": ["ICMP (1)"],
}

# Names the migration tool generates for literal values, used as a last resort.
_OBJ_PORT_RE = re.compile(r"^obj_(tcp|udp|sctp)_(?:(?:eq|src)_)?(\d+)(?:[-_](\d+))?$", re.IGNORECASE)
_IP_PREFIX_NAME_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})-(\d{1,2})$")


def split_values(text: str) -> list[str]:
    """Split a value line on commas that are not inside parentheses."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur).strip())
    return [v for v in out if v]


def parse_network_literal(v: str) -> IPNetwork | IPRange | None:
    s = v.strip()
    try:
        if "/" in s:
            return IPNetwork(s)
        if "-" in s:
            a, b = (p.strip() for p in s.split("-", 1))
            if _is_ip(a) and _is_ip(b):
                return IPRange(a, b)
            return None
        if _is_ip(s):
            return IPNetwork(s)
    except (AddrFormatError, ValueError, TypeError):
        return None
    return None


def _is_ip(s: str) -> bool:
    try:
        IPAddress(s)
        return True
    except (AddrFormatError, ValueError, TypeError):
        return False


def name_convention_network(name: str) -> IPNetwork | None:
    """'192.0.2.12-32' -> 192.0.2.12/32 (migration-tool naming convention)."""
    m = _IP_PREFIX_NAME_RE.match(name)
    if not m:
        return None
    try:
        return IPNetwork(f"{m.group(1)}/{m.group(2)}").cidr
    except (AddrFormatError, ValueError):
        return None


def parse_port_literal(v: str) -> list[ServiceEntry] | None:
    """Parse 'TCP (6):22' style values. Returns None if not a port literal."""
    s = v.strip()
    m = _PORT_RE.match(s)
    if not m:
        return None
    num = int(m.group("num"))
    proto = PROTO_BY_NUMBER.get(num) or (protocol_name(m.group("pname") or "") if m.group("pname") else None) or str(num)
    if num == 0:
        proto = "ip"
    spec = (m.group("spec") or "").strip()
    if proto in ("tcp", "udp", "sctp"):
        if not spec or spec.lower() == "any":
            return [ServiceEntry(proto)]
        r = _RANGE_RE.match(spec)
        if not r:
            return None
        a = int(r.group(1))
        b = int(r.group(2)) if r.group(2) else a
        a, b = sorted((a, b))
        return [ServiceEntry(proto, dst=((max(a, PORT_MIN), min(b, PORT_MAX)),))]
    if proto in ("icmp", "icmp6"):
        if not spec or spec.lower() == "any":
            return [ServiceEntry(proto)]
        ints = [int(x) for x in _INT_RE.findall(spec)]
        # 'Echo Request (8)' lists the type last; '8:0' lists type then code.
        if "(" in spec and ints:
            return [ServiceEntry(proto, icmp_type=ints[-1])]
        t = ints[0] if ints else None
        c = ints[1] if len(ints) > 1 else None
        return [ServiceEntry(proto, icmp_type=t, icmp_code=c)]
    return [ServiceEntry(proto)]


def name_convention_port(name: str) -> list[ServiceEntry] | None:
    """'obj_tcp_8080' -> TCP 8080 (migration-tool naming convention)."""
    m = _OBJ_PORT_RE.match(name)
    if not m:
        return None
    a = int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a
    return [ServiceEntry(m.group(1).lower(), dst=((min(a, b), max(a, b)),))]
