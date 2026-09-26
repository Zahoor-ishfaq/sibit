"""AddressSet and ServiceSet: fully expanded, canonical, comparable sets.

Both parsers produce these; the comparison engine only ever looks at these
(plus the as-written refs for display), so object renaming/flattening by the
migration tool cannot hide or fake a difference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from netaddr import IPAddress, IPNetwork, IPRange, IPSet

from ..ports import PORT_MAX, PORT_MIN

ANY_V4 = IPNetwork("0.0.0.0/0")
ANY_V6 = IPNetwork("::/0")

Interval = tuple[int, int]
FULL_PORTS: tuple[Interval, ...] = ((PORT_MIN, PORT_MAX),)


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #
def _is_cidr(first: int, size: int) -> bool:
    return size & (size - 1) == 0 and first % size == 0


def range_label(r: IPRange) -> str:
    """Canonical text for an IP range: single IP, CIDR when exact, else a-b."""
    size = r.size
    if size == 1:
        return str(r[0])
    if _is_cidr(r.first, size):
        bits = 32 if r.version == 4 else 128
        return f"{r[0]}/{bits - (size.bit_length() - 1)}"
    return f"{r[0]}-{r[-1]}"


def display_labels(r: IPRange) -> list[str]:
    """Display form of a merged range: tiny non-CIDR runs are listed host by host."""
    if r.size == 2 or (1 < r.size <= 4 and not _is_cidr(r.first, r.size)):
        return [str(ip) for ip in r]
    return [range_label(r)]


def net_label(net: IPNetwork) -> str:
    if net.size == 1:
        return str(net.ip)
    return str(net.cidr)


@dataclass(eq=False)
class AddressSet:
    """Immutable after construction; derived views are cached."""

    ipset: IPSet = field(default_factory=IPSet)
    fqdns: frozenset[str] = frozenset()
    _cache: dict = field(default_factory=dict, repr=False)

    def _get(self, key: str, fn):
        v = self._cache.get(key)
        if v is None:
            v = self._cache[key] = fn()
        return v

    @property
    def has_v4_any(self) -> bool:
        return self._get("any4", lambda: ANY_V4 in self.ipset)

    @property
    def has_v6_any(self) -> bool:
        return self._get("any6", lambda: ANY_V6 in self.ipset)

    @property
    def is_any(self) -> bool:
        return self.has_v4_any or self.has_v6_any

    @property
    def is_empty(self) -> bool:
        return not self.ipset and not self.fqdns

    @property
    def size(self) -> int:
        return self.ipset.size

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AddressSet):
            return NotImplemented
        if self is other:
            return True
        return self.fqdns == other.fqdns and self.fingerprint() == other.fingerprint()

    def __hash__(self) -> int:  # pragma: no cover - sets are not hashed in practice
        return hash(self.fingerprint())

    def ranges(self) -> list[IPRange]:
        return self._get("ranges", lambda: list(self.ipset.iter_ipranges()))

    def fingerprint(self) -> tuple:
        return self._get("fp", lambda: (tuple((r.version, r.first, r.last) for r in self.ranges()),
                                        tuple(sorted(self.fqdns))))

    def contains_ip(self, ip: IPAddress) -> bool:
        return ip in self.ipset

    def labels(self, limit: int | None = None) -> list[str]:
        """Human-readable canonical items ('any' when it covers everything)."""
        out = self._get("labels", self._labels)
        return out[:limit] if limit is not None and len(out) > limit else list(out)

    def _labels(self) -> list[str]:
        def lab(version: int | None) -> list[str]:
            return [x for r in self.ranges() if version is None or r.version == version
                    for x in display_labels(r)]

        if self.has_v4_any and self.has_v6_any:
            out = ["any"]
        elif self.has_v4_any:
            out = ["any"] + lab(6)
        elif self.has_v6_any:
            out = lab(4) + ["any6"]
        else:
            out = lab(None)
        return out + [f"fqdn:{f}" for f in sorted(self.fqdns)]

    def minus(self, other: "AddressSet") -> list[str]:
        """Items in self that are not in other (display strings)."""
        if self == other:
            return []
        if other.has_v4_any and other.has_v6_any:
            return [f"fqdn:{f}" for f in sorted(self.fqdns - other.fqdns)] if other.fqdns else []
        diff = self.ipset - other.ipset
        out = [x for r in diff.iter_ipranges() for x in display_labels(r)]
        if self.has_v4_any and not other.has_v4_any and len(out) > 8:
            # "any minus a few hosts" is unreadable as ranges; summarise.
            out = [f"any (except {len(other.labels())} item(s))"]
        out += [f"fqdn:{f}" for f in sorted(self.fqdns - other.fqdns)]
        return out


class AddressBuilder:
    """Accumulates networks, then produces one merged AddressSet.

    IPSet.add() re-compacts on every call; collecting CIDRs and building the
    set once is an order of magnitude faster on large groups.
    """

    def __init__(self) -> None:
        self._items: list[IPNetwork] = []
        self._fqdns: set[str] = set()

    def add_net(self, net: IPNetwork) -> None:
        self._items.append(net.cidr)

    def add_range(self, r: IPRange) -> None:
        self._items.extend(r.cidrs())

    def add_set(self, s: AddressSet) -> None:
        self._items.extend(s.ipset.iter_cidrs())
        self._fqdns.update(s.fqdns)

    def add_fqdn(self, name: str) -> None:
        self._fqdns.add(name.lower())

    def build(self) -> AddressSet:
        return AddressSet(IPSet(self._items), frozenset(self._fqdns))


# --------------------------------------------------------------------------- #
# Port intervals
# --------------------------------------------------------------------------- #
def merge_intervals(items: Iterable[Interval]) -> tuple[Interval, ...]:
    ivs = sorted((max(PORT_MIN, a), min(PORT_MAX, b)) for a, b in items if b >= a)
    ivs = [iv for iv in ivs if iv[1] >= iv[0]]
    out: list[list[int]] = []
    for a, b in ivs:
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return tuple((a, b) for a, b in out)


def subtract_intervals(a: tuple[Interval, ...], b: tuple[Interval, ...]) -> tuple[Interval, ...]:
    out: list[Interval] = []
    for lo, hi in a:
        cur = lo
        for blo, bhi in b:
            if bhi < cur or blo > hi:
                continue
            if blo > cur:
                out.append((cur, blo - 1))
            cur = max(cur, bhi + 1)
            if cur > hi:
                break
        if cur <= hi:
            out.append((cur, hi))
    return tuple(out)


def interval_label(iv: Interval) -> str:
    a, b = iv
    return str(a) if a == b else f"{a}-{b}"


def intervals_label(ivs: tuple[Interval, ...] | None) -> str:
    if ivs is None or ivs == FULL_PORTS:
        return "any"
    return ", ".join(interval_label(i) for i in ivs)


PORT_PROTOS = ("tcp", "udp", "sctp")
ICMP_PROTOS = ("icmp", "icmp6")


@dataclass(frozen=True)
class ServiceEntry:
    """One primitive service before merging.

    proto: 'ip' | 'tcp' | 'udp' | 'sctp' | 'icmp' | 'icmp6' | other name/number
    dst/src: port intervals (tcp/udp/sctp only); None = any
    icmp_type/icmp_code: for icmp/icmp6; None = any
    """

    proto: str
    dst: tuple[Interval, ...] | None = None
    src: tuple[Interval, ...] | None = None
    icmp_type: int | None = None
    icmp_code: int | None = None

    def leaf(self) -> str:
        """Canonical text used to compare 'as written' structure (MATCH vs MATCH_MERGED)."""
        p = self.proto
        if p in PORT_PROTOS:
            s = f"{p}:{intervals_label(self.dst)}"
            if self.src is not None and self.src != FULL_PORTS:
                s += f":src={intervals_label(self.src)}"
            return s
        if p in ICMP_PROTOS:
            if self.icmp_type is None:
                return p
            if self.icmp_code is None:
                return f"{p}:{self.icmp_type}"
            return f"{p}:{self.icmp_type}/{self.icmp_code}"
        return p


def _entry_label(proto: str, dst: tuple[Interval, ...] | None, src: tuple[Interval, ...] | None) -> str:
    base = proto.upper()
    if src is not None:
        return f"{base} src {intervals_label(src)} → {intervals_label(dst)}"
    if dst is None or dst == FULL_PORTS:
        return f"{base} (all ports)"
    return f"{base} {intervals_label(dst)}"


@dataclass
class ServiceSet:
    """Canonical merged service set.

    all_ip        : every protocol is allowed (``ip``)
    protos        : protocols allowed completely (e.g. {'gre', 'tcp'})
    ports         : {(proto, src_intervals|None): dst_intervals}
    icmp          : {'icmp'|'icmp6': {(type|None, code|None)}}
    """

    all_ip: bool = False
    protos: frozenset[str] = frozenset()
    ports: dict[tuple[str, tuple[Interval, ...] | None], tuple[Interval, ...]] = field(default_factory=dict)
    icmp: dict[str, frozenset[tuple[int | None, int | None]]] = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # -- construction ------------------------------------------------------ #
    @classmethod
    def from_entries(cls, entries: Iterable[ServiceEntry]) -> "ServiceSet":
        all_ip = False
        protos: set[str] = set()
        ports: dict[tuple[str, tuple[Interval, ...] | None], list[Interval]] = {}
        icmp: dict[str, set[tuple[int | None, int | None]]] = {}
        for e in entries:
            p = e.proto
            if p == "ip":
                all_ip = True
            elif p in PORT_PROTOS:
                dst = e.dst if e.dst is not None else FULL_PORTS
                src = e.src if (e.src is not None and merge_intervals(e.src) != FULL_PORTS) else None
                src = merge_intervals(src) if src is not None else None
                ports.setdefault((p, src), []).extend(dst)
            elif p in ICMP_PROTOS:
                if e.icmp_type is None:
                    protos.add(p)
                else:
                    icmp.setdefault(p, set()).add((e.icmp_type, e.icmp_code))
            else:
                protos.add(p)
        if all_ip:
            return cls(all_ip=True)
        merged: dict[tuple[str, tuple[Interval, ...] | None], tuple[Interval, ...]] = {}
        for (p, src), ivs in ports.items():
            m = merge_intervals(ivs)
            if src is None and m == FULL_PORTS:
                protos.add(p)
            else:
                merged[(p, src)] = m
        # Drop entries already covered by a whole-protocol permit or by the any-source entry.
        final_ports: dict[tuple[str, tuple[Interval, ...] | None], tuple[Interval, ...]] = {}
        for (p, src), m in merged.items():
            if p in protos:
                continue
            if src is not None:
                any_src = merged.get((p, None), ())
                m = subtract_intervals(m, any_src)
                if not m:
                    continue
            final_ports[(p, src)] = m
        final_icmp: dict[str, frozenset[tuple[int | None, int | None]]] = {}
        for p, types in icmp.items():
            if p in protos:
                continue
            whole_types = {t for t, c in types if c is None}
            keep = {(t, c) for t, c in types if c is None or t not in whole_types}
            final_icmp[p] = frozenset(keep)
        return cls(all_ip=False, protos=frozenset(protos), ports=final_ports, icmp=final_icmp)

    def entries(self) -> list[ServiceEntry]:
        """Back to primitive entries (for unions)."""
        if self.all_ip:
            return [ServiceEntry("ip")]
        out = [ServiceEntry(p) for p in self.protos]
        out += [ServiceEntry(p, dst=d, src=s) for (p, s), d in self.ports.items()]
        out += [ServiceEntry(p, icmp_type=t, icmp_code=c) for p, v in self.icmp.items() for t, c in v]
        return out

    @classmethod
    def union(cls, sets: Iterable["ServiceSet"]) -> "ServiceSet":
        return cls.from_entries(e for s in sets for e in s.entries())

    # -- comparison -------------------------------------------------------- #
    def fingerprint(self) -> tuple:
        fp = self._cache.get("fp")
        if fp is None:
            fp = self._cache["fp"] = self._fingerprint()
        return fp

    def _fingerprint(self) -> tuple:
        if self.all_ip:
            return ("ip",)
        return (
            tuple(sorted(self.protos)),
            tuple(sorted((p, s or (), d) for (p, s), d in self.ports.items())),
            tuple(sorted((p, tuple(sorted(v, key=_icmp_key))) for p, v in self.icmp.items())),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServiceSet):
            return NotImplemented
        return self.fingerprint() == other.fingerprint()

    def __hash__(self) -> int:  # pragma: no cover
        return hash(self.fingerprint())

    @property
    def is_any(self) -> bool:
        return self.all_ip

    @property
    def is_empty(self) -> bool:
        return not self.all_ip and not self.protos and not self.ports and not self.icmp

    def _covers_port(self, proto: str, src: tuple[Interval, ...] | None, dst: tuple[Interval, ...]) -> tuple[Interval, ...]:
        """Return the part of ``dst`` (for proto/src) NOT covered by self."""
        if self.all_ip or proto in self.protos:
            return ()
        rem = subtract_intervals(dst, self.ports.get((proto, None), ()))
        if src is not None and rem:
            rem = subtract_intervals(rem, self.ports.get((proto, src), ()))
        return rem

    def minus(self, other: "ServiceSet") -> list[str]:
        """Display items allowed by self but not by other."""
        if other.all_ip or self.fingerprint() == other.fingerprint():
            return []
        out: list[str] = []
        if self.all_ip:
            return ["IP (all protocols)"]
        for p in sorted(self.protos):
            if p in other.protos:
                continue
            if p in PORT_PROTOS:
                rem = other._covers_port(p, None, FULL_PORTS)
                if rem == FULL_PORTS:
                    out.append(_entry_label(p, None, None))
                elif rem:
                    out.extend(f"{p.upper()} {interval_label(i)}" for i in rem)
            elif p in ICMP_PROTOS and other.icmp.get(p):
                out.append(f"{p.upper()} (other types)")
            else:
                out.append(p.upper())
        for (p, src), dst in sorted(self.ports.items(), key=lambda kv: (kv[0][0], kv[0][1] or ())):
            rem = other._covers_port(p, src, dst)
            if not rem:
                continue
            if src is None:
                out.extend(f"{p.upper()} {interval_label(i)}" for i in rem)
            else:
                out.append(_entry_label(p, rem, src))
        for p, types in sorted(self.icmp.items()):
            if p in other.protos:
                continue
            ot = other.icmp.get(p, frozenset())
            for t, c in sorted(types, key=_icmp_key):
                if (t, None) in ot or (t, c) in ot:
                    continue
                out.append(_icmp_label(p, t, c))
        return out

    def labels(self) -> list[str]:
        out = self._cache.get("labels")
        if out is None:
            out = self._cache["labels"] = self._labels()
        return list(out)

    def _labels(self) -> list[str]:
        if self.all_ip:
            return ["any"]
        out: list[str] = []
        for p in sorted(self.protos):
            out.append(_entry_label(p, None, None) if p in PORT_PROTOS else p.upper())
        for (p, src), dst in sorted(self.ports.items(), key=lambda kv: (kv[0][0], kv[0][1] or ())):
            if src is None:
                out.extend(f"{p.upper()} {interval_label(i)}" for i in dst)
            else:
                out.append(_entry_label(p, dst, src))
        for p, types in sorted(self.icmp.items()):
            out.extend(_icmp_label(p, t, c) for t, c in sorted(types, key=_icmp_key))
        return out

    def contains_port(self, port: int) -> bool:
        if self.all_ip:
            return True
        if any(p in self.protos for p in PORT_PROTOS):
            return True
        return any(a <= port <= b for dst in self.ports.values() for a, b in dst)


def _icmp_key(tc: tuple[int | None, int | None]) -> tuple[int, int]:
    t, c = tc
    return (-1 if t is None else t, -1 if c is None else c)


def _icmp_label(p: str, t: int | None, c: int | None) -> str:
    if t is None:
        return p.upper()
    if c is None:
        return f"{p.upper()} type {t}"
    return f"{p.upper()} type {t} code {c}"
