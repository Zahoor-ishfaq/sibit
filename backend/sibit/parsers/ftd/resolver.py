"""Resolves FTD rule values (literals + Referenced Objects) into normalized Rules."""
from __future__ import annotations

import re

from ...model import AddressBuilder, AddressSet, Rule, ServiceEntry, ServiceSet, net_label, normalize_comment, range_label
from ...model.sets import ANY_V4
from ..common import ParseWarning
from .referenced_objects import FtdObject
from .rule_block import RawFtdRule
from .values import (
    BUILTIN_NETWORKS,
    BUILTIN_PORTS,
    name_convention_network,
    name_convention_port,
    parse_network_literal,
    parse_port_literal,
    split_values,
)

ACTION_MAP = {
    "allow": "permit",
    "trust": "permit",
    "block": "deny",
    "block with reset": "deny",
    "interactive block": "deny",
    "interactive block with reset": "deny",
    "monitor": "monitor",
}
_KEY_RE = re.compile(r"^(?P<acl>.+)_#(?P<n>\d+)$")


def parse_rule_name(name: str) -> tuple[str | None, int | None]:
    m = _KEY_RE.match(name.strip())
    if not m:
        return None, None
    return m.group("acl"), int(m.group("n"))


class FtdResolver:
    def __init__(self, objects: dict[str, FtdObject], warnings: list[ParseWarning]) -> None:
        self.objects = objects
        self.warnings = warnings
        self._net_cache: dict[str, tuple[AddressSet, list[str], list[str]]] = {}
        self._port_cache: dict[str, tuple[list[ServiceEntry], list[str]]] = {}
        self._stack: list[str] = []
        self.unresolved_names: dict[str, str] = {}
        self.convention_names: set[str] = set()

    # -------------------------------------------------------------- networks
    def network_values(self, values: list[str]) -> tuple[AddressSet, list[str], list[str]]:
        b = AddressBuilder()
        leaves: list[str] = []
        unresolved: list[str] = []
        for v in values:
            s, lv, un = self.network_value(v)
            b.add_set(s)
            leaves += lv
            unresolved += un
        return b.build(), leaves, unresolved

    def network_value(self, v: str) -> tuple[AddressSet, list[str], list[str]]:
        b = AddressBuilder()
        if v.lower() == "any":
            b.add_net(ANY_V4)
            return b.build(), ["any"], []
        lit = parse_network_literal(v)
        if lit is not None:
            if hasattr(lit, "prefixlen"):
                b.add_net(lit)  # type: ignore[arg-type]
                return b.build(), [net_label(lit)], []  # type: ignore[arg-type]
            b.add_range(lit)  # type: ignore[arg-type]
            return b.build(), [range_label(lit)], []  # type: ignore[arg-type]
        return self.network_name(v)

    def network_name(self, name: str) -> tuple[AddressSet, list[str], list[str]]:
        if name in self._net_cache:
            return self._net_cache[name]
        if name in self._stack:
            self.unresolved_names[name] = "circular object group reference"
            self.warnings.append(ParseWarning("FTD", None, name, "Circular object group reference"))
            return AddressSet(), [], [name]
        obj = self.objects.get(name)
        if obj is not None and obj.values:
            self._stack.append(name)
            try:
                res = self.network_values(obj.values)
            finally:
                self._stack.pop()
        elif name in BUILTIN_NETWORKS:
            b = AddressBuilder()
            for c in BUILTIN_NETWORKS[name]:
                lit = parse_network_literal(c)
                b.add_net(lit)  # type: ignore[arg-type]
            leaves = ["any"] if name in ("any", "any-ipv4") else (["any6"] if name == "any-ipv6" else list(BUILTIN_NETWORKS[name]))
            res = (b.build(), leaves, [])
        elif (net := name_convention_network(name)) is not None:
            b = AddressBuilder()
            b.add_net(net)
            self.convention_names.add(name)
            res = (b.build(), [net_label(net)], [])
        elif obj is not None and obj.section == "other":
            res = (AddressSet(), [], [name])
            self.unresolved_names.setdefault(name, f"object is not a network object ({obj.type or 'other'})")
        else:
            res = (AddressSet(), [], [name])
            self.unresolved_names.setdefault(name, "not found in Referenced Objects")
        self._net_cache[name] = res
        return res

    # ----------------------------------------------------------------- ports
    def port_values(self, values: list[str]) -> tuple[list[ServiceEntry], list[str]]:
        out: list[ServiceEntry] = []
        unresolved: list[str] = []
        for v in values:
            e, un = self.port_value(v)
            out += e
            unresolved += un
        return out, unresolved

    def port_value(self, v: str) -> tuple[list[ServiceEntry], list[str]]:
        if v.lower() == "any":
            return [ServiceEntry("ip")], []
        lit = parse_port_literal(v)
        if lit is not None:
            return lit, []
        return self.port_name(v)

    def port_name(self, name: str) -> tuple[list[ServiceEntry], list[str]]:
        if name in self._port_cache:
            return self._port_cache[name]
        if name in self._stack:
            self.unresolved_names[name] = "circular object group reference"
            return [], [name]
        obj = self.objects.get(name)
        if obj is not None and obj.values:
            self._stack.append(name)
            try:
                res = self.port_values(obj.values)
            finally:
                self._stack.pop()
        elif name in BUILTIN_PORTS:
            res = self.port_values(BUILTIN_PORTS[name])
        elif (conv := name_convention_port(name)) is not None:
            self.convention_names.add(name)
            res = (conv, [])
        else:
            res = ([], [name])
            self.unresolved_names.setdefault(name, "not found in Referenced Objects")
        self._port_cache[name] = res
        return res

    # ------------------------------------------------------------------ rule
    def services(self, src_vals: list[str], dst_vals: list[str]) -> tuple[list[ServiceEntry], list[str]]:
        dst_any = not dst_vals or all(v.lower() == "any" for v in dst_vals)
        src_any = not src_vals or all(v.lower() == "any" for v in src_vals)
        dst_entries, un1 = ([ServiceEntry("ip")], []) if dst_any else self.port_values(dst_vals)
        if src_any:
            return dst_entries, un1
        src_entries, un2 = self.port_values(src_vals)
        out: list[ServiceEntry] = []
        for s in src_entries:
            if dst_any:
                out.append(ServiceEntry(s.proto, dst=None, src=s.dst))
                continue
            for d in dst_entries:
                if d.proto == "ip":
                    out.append(ServiceEntry(s.proto, dst=None, src=s.dst))
                elif d.proto == s.proto:
                    out.append(ServiceEntry(s.proto, dst=d.dst, src=s.dst))
        return out, un1 + un2

    def to_rule(self, raw: RawFtdRule) -> Rule:
        def vals(label: str) -> list[str]:
            out: list[str] = []
            for line in raw.value(label):
                out += split_values(line)
            return out

        acl, n = parse_rule_name(raw.name)
        action_text = raw.text("Action")
        action = ACTION_MAP.get(action_text.lower())
        if action is None:
            self.warnings.append(ParseWarning("FTD", raw.page, f"{raw.position}:{raw.name} Action {action_text}",
                                              "Unknown action; treated as permit"))
            action = "permit"
        src_v, dst_v = vals("Source Networks"), vals("Destination Networks")
        sp_v, dp_v = vals("Source Ports"), vals("Destination Ports")
        src, src_leaves, un1 = self.network_values(src_v or ["any"])
        dst, dst_leaves, un2 = self.network_values(dst_v or ["any"])
        entries, un3 = self.services(sp_v, dp_v)
        log = raw.text("Log at Beginning of Connection").lower() == "yes" or raw.text("Log at End of Connection").lower() == "yes"
        svc_refs = [v for v in (dp_v or ["any"])]
        if sp_v and not all(v.lower() == "any" for v in sp_v):
            svc_refs = [f"src {v}" for v in sp_v] + svc_refs
        unresolved = list(dict.fromkeys(un1 + un2 + un3))
        ref_names = frozenset(
            v for v in src_v + dst_v + sp_v + dp_v
            if v.lower() != "any" and parse_network_literal(v) is None and parse_port_literal(v) is None
        )
        return Rule(
            side="FTD",
            key=raw.name,
            acl=acl or "",
            line_no=n or 0,
            position=raw.position,
            source_zone=raw.text("Source Zones") or None,
            action=action,  # type: ignore[arg-type]
            enabled=not raw.disabled,
            log=log,
            comment=normalize_comment(raw.text("Comments", sep="\n")),
            raw_text="\n".join(raw.lines),
            src_refs=src_v or ["any"],
            dst_refs=dst_v or ["any"],
            svc_refs=svc_refs,
            src=src,
            dst=dst,
            services=ServiceSet.from_entries(entries),
            unresolved=unresolved,
            src_leaves=tuple(sorted(src_leaves)),
            dst_leaves=tuple(sorted(dst_leaves)),
            svc_leaves=tuple(sorted(e.leaf() for e in entries)),
            ref_names=ref_names,
            action_text=action_text,
            dest_zone=raw.text("Destination Zones") or None,
            uid=f"FTD:{raw.position}",
        )
