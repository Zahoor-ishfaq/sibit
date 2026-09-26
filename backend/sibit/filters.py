"""Row filtering and global search over a session (Rules screen + filtered exports).

Search terms (space-separated, all must match):
  192.0.2.10      rules whose source/destination contains that IP (through groups too)
  192.0.2.0/24     rules whose addresses overlap that network
  443               rules allowing that port, or containing the text '443'
  anything else     case-insensitive text in keys, object names, ports, comments
"""
from __future__ import annotations

from dataclasses import dataclass, field

from netaddr import AddrFormatError, IPAddress, IPNetwork


@dataclass
class RowFilter:
    status: list[str] = field(default_factory=list)
    severity: list[str] = field(default_factory=list)
    acl: list[str] = field(default_factory=list)
    flag: list[str] = field(default_factory=list)
    enabled: str | None = None  # 'enabled' | 'disabled' | None
    q: str = ""

    def is_empty(self) -> bool:
        return not (self.status or self.severity or self.acl or self.flag or self.enabled or self.q.strip())


def _term_matcher(term: str):
    t = term.strip().lower()
    try:
        if "/" in t:
            net = IPNetwork(t)
            v, lo, hi = net.version, int(net.first), int(net.last)
            return lambda blob, ranges, ports: any(rv == v and rf <= hi and rl >= lo for rv, rf, rl in ranges)
        if t.count(".") == 3 or ":" in t and t.count(":") >= 2:
            ip = IPAddress(t)
            v, n = ip.version, int(ip)
            return lambda blob, ranges, ports: any(rv == v and rf <= n <= rl for rv, rf, rl in ranges)
    except (AddrFormatError, ValueError):
        pass
    if t.isdigit() and 0 < int(t) <= 65535:
        port = int(t)
        return lambda blob, ranges, ports: t in blob or any(a <= port <= b for a, b in ports)
    return lambda blob, ranges, ports: t in blob


def filter_ids(session: dict, f: RowFilter) -> list[int]:
    rows = session["rows"]
    if f.is_empty():
        return [r["id"] for r in rows]
    status, sev, acl, flag = set(f.status), set(f.severity), set(f.acl), set(f.flag)
    matchers = [_term_matcher(t) for t in f.q.split() if t.strip()]
    search = session["search"]
    out: list[int] = []
    for r in rows:
        if status and r["status"] not in status:
            continue
        if sev and r["severity"] not in sev:
            continue
        if acl and r["acl"] not in acl and (r.get("zone") or "") not in acl:
            continue
        if flag and not flag.intersection(r["flags"]):
            continue
        if f.enabled == "enabled" and not r["enabled"]:
            continue
        if f.enabled == "disabled" and r["enabled"]:
            continue
        if matchers:
            s = search[r["id"]]
            if not all(m(s["text"], s["ranges"], s["ports"]) for m in matchers):
                continue
        out.append(r["id"])
    return out
