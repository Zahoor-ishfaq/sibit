"""Line reading, secret filtering and small token helpers for ASA configs."""
from __future__ import annotations

import re

from netaddr import AddrFormatError, IPAddress, IPNetwork

# Lines carrying secrets (spec 2.4). They are blanked *before* anything else
# sees the config, so they can never reach the UI, logs, warnings or exports.
# Line numbers are preserved by replacing them with "!".
_SECRET_PATTERNS = [
    r"^\s*enable\s+password\b",
    r"^\s*enable\s+secret\b",
    r"^\s*passwd\b",
    r"^\s*username\s+\S+.*\b(password|secret|nt-encrypted)\b",
    r"^\s*username\s+\S+\s+attributes\b.*",  # harmless, but keep usernames out too
    r"^\s*failover\s+key\b",
    r"^\s*failover\s+ipsec\s+pre-shared-key\b",
    r"^\s*key\s+\S+",  # aaa-server host key
    r"^\s*server-secret\b",
    r"^\s*snmp-server\s+community\b",
    r"^\s*snmp-server\s+host\b.*\bcommunity\b",
    r"^\s*snmp-server\s+user\b",
    r"^\s*(ikev1|ikev2)\s+(local-|remote-)?authentication\s+pre-shared-key\b",
    r"^\s*(ikev1\s+)?pre-shared-key\b",
    r"^\s*ntp\s+authentication-key\b",
    r"^\s*(ldap-login-password|password|secret)\b",
    r"\bmessage-digest-key\b",
    r"\bauthentication-key\b",
    r"^\s*ospf\s+authentication\b.*\bkey\b",
    r"^\s*crypto\s+ca\s+certificate\b",
    r"^\s*quit\s*$",
]
_SECRET_RE = re.compile("|".join(f"(?:{p})" for p in _SECRET_PATTERNS), re.IGNORECASE)
# Hex blobs inside "crypto ca certificate chain" blocks.
_HEX_BLOB_RE = re.compile(r"^\s+(?:[0-9a-f]{8}\s*){2,}$", re.IGNORECASE)


def is_secret_line(line: str) -> bool:
    return bool(_SECRET_RE.search(line)) or bool(_HEX_BLOB_RE.match(line))


def sanitize_lines(text: str) -> tuple[list[str], int]:
    """Split config text into lines with secret lines replaced by '!'."""
    out: list[str] = []
    removed = 0
    for raw in text.splitlines():
        line = raw.rstrip("\r\n").rstrip()
        if line.strip() and is_secret_line(line):
            out.append("!")
            removed += 1
        else:
            out.append(line.expandtabs(1))
    return out, removed


def is_ip(tok: str) -> bool:
    try:
        IPAddress(tok)
        return True
    except (AddrFormatError, ValueError, TypeError):
        return False


def is_ipv6_prefix(tok: str) -> bool:
    if "/" not in tok or ":" not in tok:
        return False
    try:
        IPNetwork(tok)
        return True
    except (AddrFormatError, ValueError):
        return False


def mask_to_net(ip: str, mask: str) -> IPNetwork:
    """'10.0.0.0', '255.255.255.0' -> IPNetwork('10.0.0.0/24'). Raises ValueError."""
    try:
        m = IPAddress(mask)
    except (AddrFormatError, ValueError) as e:
        raise ValueError(f"bad mask {mask}") from e
    bits = m.bits().replace(".", "")
    if "01" in bits:
        raise ValueError(f"non-contiguous mask {mask}")
    prefix = bits.count("1")
    return IPNetwork(f"{ip}/{prefix}")


def collect_names(lines: list[str]) -> dict[str, str]:
    """'name 10.0.0.1 WEB01 [description ...]' aliases (legacy ASA 'names' feature)."""
    out: dict[str, str] = {}
    for line in lines:
        if line.startswith("name "):
            t = line.split()
            if len(t) >= 3 and is_ip(t[1]):
                out[t[2]] = t[1]
    return out


def apply_names(line: str, names: dict[str, str]) -> str:
    """Replace name aliases in address positions only.

    A token is an alias use when it follows 'host'/'range'/'subnet', follows an
    address (second half of a range), or is followed by a netmask. Object names
    elsewhere on the line are never touched.
    """
    toks = line.split()
    if not any(t in names for t in toks):
        return line
    for i, t in enumerate(toks):
        if t not in names:
            continue
        prev = toks[i - 1].lower() if i else ""
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        second_of_range = i >= 2 and toks[i - 2].lower() == "range" and is_ip(toks[i - 1])
        before_mask = is_ip(nxt) and nxt.startswith("255.")
        if prev in ("host", "range", "subnet") or second_of_range or before_mask:
            toks[i] = names[t]
    indent = line[: len(line) - len(line.lstrip())]
    return indent + " ".join(toks)
