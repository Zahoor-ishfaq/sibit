"""Expands ASA objects/groups into AddressSets and ServiceEntries.

Every group is resolved once and memoized; circular group-object references
are detected and reported instead of recursing forever.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from netaddr import IPNetwork, IPRange

from ...model import AddressBuilder, AddressSet, ServiceEntry, net_label, range_label
from ...model.sets import ANY_V4, ANY_V6
from ...ports import PortResolver, icmp_type
from ..common import ParseWarning
from .acl import AddrRef, Ace, PortRef
from .objects import Definitions, PortOp, SvcSpec
from .tokenizer import mask_to_net


@dataclass
class Expanded:
    addrs: AddressSet
    leaves: list[str]
    unresolved: list[str] = field(default_factory=list)


@dataclass
class ExpandedSvc:
    entries: list[ServiceEntry]
    unresolved: list[str] = field(default_factory=list)


class AsaResolver:
    def __init__(self, defs: Definitions, ports: PortResolver, warnings: list[ParseWarning]) -> None:
        self.defs = defs
        self.ports = ports
        self.warnings = warnings
        self._net_cache: dict[str, Expanded] = {}
        self._svc_cache: dict[str, ExpandedSvc] = {}
        self._port_cache: dict[tuple[str, str], tuple[list[tuple[int, int]], list[str], list[str]]] = {}
        self._proto_cache: dict[str, list[str]] = {}
        self._icmp_cache: dict[str, list[str]] = {}
        self._stack: list[str] = []
        self.unresolved_names: dict[str, str] = {}  # name -> reason
        self.cycles_reported: set[str] = set()
        self._warned: set[str] = set()

    # ------------------------------------------------------------------ utils
    def _cycle(self, name: str, kind: str) -> bool:
        if name in self._stack:
            if name not in self.cycles_reported:
                self.cycles_reported.add(name)
                chain = " -> ".join(self._stack[self._stack.index(name):] + [name])
                d = self.defs
                grp = d.net_groups.get(name) or d.svc_groups.get(name) or d.proto_groups.get(name) or d.icmp_groups.get(name)
                line = grp.line if grp else None
                self.warnings.append(ParseWarning("ASA", line, chain, f"Circular group-object reference in {kind} group"))
                self.unresolved_names[name] = "circular group-object reference"
            return True
        return False

    def _warn_once(self, name: str, msg: str) -> None:
        if name not in self._warned:
            self._warned.add(name)
            self.warnings.append(ParseWarning("ASA", None, name, f"'{name}' {msg}"))

    def _missing(self, name: str, reason: str) -> str:
        self.unresolved_names.setdefault(name, reason)
        return name

    # --------------------------------------------------------------- network
    def network_object(self, name: str) -> Expanded:
        obj = self.defs.net_objects.get(name)
        if obj is None or obj.kind is None:
            reason = "network object not defined" if obj is None else "network object has no address"
            return Expanded(AddressSet(), [], [self._missing(name, reason)])
        b = AddressBuilder()
        if obj.kind in ("host", "subnet"):
            net: IPNetwork = obj.value  # type: ignore[assignment]
            b.add_net(net)
            return Expanded(b.build(), [net_label(net)])
        if obj.kind == "range":
            r: IPRange = obj.value  # type: ignore[assignment]
            b.add_range(r)
            return Expanded(b.build(), [range_label(r)])
        # fqdn: kept as an unresolved FQDN (no DNS lookups — offline tool)
        b.add_fqdn(str(obj.value))
        return Expanded(b.build(), [f"fqdn:{str(obj.value).lower()}"])

    def network_group(self, name: str) -> Expanded:
        if name in self._net_cache:
            return self._net_cache[name]
        grp = self.defs.net_groups.get(name)
        if grp is None:
            if name in self.defs.net_objects:
                self._warn_once(name, "referenced as object-group but defined as 'object network'; using the object")
                return self.network_object(name)
            return Expanded(AddressSet(), [], [self._missing(name, "network object-group not defined")])
        if self._cycle(name, "network"):
            return Expanded(AddressSet(), [], [name])
        self._stack.append(name)
        try:
            b = AddressBuilder()
            leaves: list[str] = []
            unresolved: list[str] = []
            for kind, val in grp.members:
                if kind == "net":
                    b.add_net(val)  # type: ignore[arg-type]
                    leaves.append(net_label(val))  # type: ignore[arg-type]
                    continue
                sub = self.network_object(val) if kind == "object" else self.network_group(val)  # type: ignore[arg-type]
                b.add_set(sub.addrs)
                leaves += sub.leaves
                unresolved += sub.unresolved
            res = Expanded(b.build(), leaves, unresolved)
        finally:
            self._stack.pop()
        self._net_cache[name] = res
        return res

    def address(self, ref: AddrRef) -> Expanded:
        b = AddressBuilder()
        k = ref.kind
        if k in ("any", "any4"):
            b.add_net(ANY_V4)
            return Expanded(b.build(), ["any"])
        if k == "any6":
            b.add_net(ANY_V6)
            return Expanded(b.build(), ["any6"])
        if k == "host":
            net = IPNetwork(ref.value)
            b.add_net(net)
            return Expanded(b.build(), [net_label(net)])
        if k == "net":
            parts = ref.value.split()
            try:
                net = mask_to_net(parts[0], parts[1]) if len(parts) == 2 else IPNetwork(parts[0])
            except (ValueError, IndexError):
                return Expanded(AddressSet(), [], [self._missing(ref.value, "invalid network/mask")])
            b.add_net(net)
            return Expanded(b.build(), [net_label(net)])
        if k == "object":
            return self.network_object(ref.value)
        if k == "group":
            return self.network_group(ref.value)
        if k == "interface":
            itf = self.defs.interfaces.get(ref.value)
            if itf is None or itf.ip is None:
                return Expanded(AddressSet(), [], [self._missing(f"interface {ref.value}", "interface has no IP address")])
            net = IPNetwork(itf.ip)
            b.add_net(net)
            return Expanded(b.build(), [net_label(net)])
        return Expanded(AddressSet(), [], [self._missing(ref.text(), "unsupported address")])

    # --------------------------------------------------------------- services
    def _port_intervals(self, op: PortOp, proto: str) -> tuple[tuple[tuple[int, int], ...] | None, list[str]]:
        ivs, bad = op.intervals(proto, self.ports)
        for n in bad:
            self._missing(f"{proto}/{n}", "unknown port name")
        return ivs, [f"{proto}/{n}" for n in bad]

    def spec_entries(self, spec: SvcSpec) -> ExpandedSvc:
        protos = ["tcp", "udp"] if spec.proto == "tcp-udp" else [spec.proto]
        out: list[ServiceEntry] = []
        unresolved: list[str] = []
        for p in protos:
            if p in ("icmp", "icmp6"):
                t = icmp_type(spec.icmp_type, p) if spec.icmp_type else None
                if spec.icmp_type and t is None:
                    unresolved.append(self._missing(spec.icmp_type, "unknown icmp type"))
                    continue
                code = int(spec.icmp_code) if spec.icmp_code else None
                out.append(ServiceEntry(p, icmp_type=t, icmp_code=code))
                continue
            src = dst = None
            ok = True
            if spec.src:
                src, bad = self._port_intervals(spec.src, p)
                unresolved += bad
                ok = ok and src is not None
            if spec.dst:
                dst, bad = self._port_intervals(spec.dst, p)
                unresolved += bad
                ok = ok and dst is not None
            if ok:
                out.append(ServiceEntry(p, dst=dst, src=src))
        return ExpandedSvc(out, unresolved)

    def service_object(self, name: str) -> ExpandedSvc:
        obj = self.defs.svc_objects.get(name)
        if obj is None or obj.spec is None:
            reason = "service object not defined" if obj is None else "service object has no service line"
            return ExpandedSvc([], [self._missing(name, reason)])
        return self.spec_entries(obj.spec)

    def service_group(self, name: str) -> ExpandedSvc:
        if name in self._svc_cache:
            return self._svc_cache[name]
        grp = self.defs.svc_groups.get(name)
        if grp is None:
            if name in self.defs.proto_groups:
                return ExpandedSvc([ServiceEntry(p) for p in self.protocol_group(name)])
            if name in self.defs.svc_objects:
                # Referenced as 'object-group' but defined as 'object service' (seen in real configs).
                self._warn_once(name, "referenced as object-group but defined as 'object service'; using the object")
                return self.service_object(name)
            return ExpandedSvc([], [self._missing(name, "service object-group not defined")])
        if self._cycle(name, "service"):
            return ExpandedSvc([], [name])
        self._stack.append(name)
        try:
            entries: list[ServiceEntry] = []
            unresolved: list[str] = []
            typed_protos = (["tcp", "udp"] if grp.typed == "tcp-udp" else [grp.typed]) if grp.typed else []
            for kind, val in grp.members:
                if kind == "port":
                    for p in typed_protos:
                        ivs, bad = self._port_intervals(val, p)  # type: ignore[arg-type]
                        unresolved += bad
                        if ivs is not None:
                            entries.append(ServiceEntry(p, dst=ivs))
                elif kind == "svc":
                    sub = self.spec_entries(val)  # type: ignore[arg-type]
                    entries += sub.entries
                    unresolved += sub.unresolved
                elif kind == "object":
                    sub = self.service_object(val)  # type: ignore[arg-type]
                    entries += sub.entries
                    unresolved += sub.unresolved
                else:
                    sub = self.service_group(val)  # type: ignore[arg-type]
                    entries += sub.entries
                    unresolved += sub.unresolved
            res = ExpandedSvc(entries, unresolved)
        finally:
            self._stack.pop()
        self._svc_cache[name] = res
        return res

    def port_group(self, name: str, proto: str) -> tuple[list[tuple[int, int]], list[str], list[str]]:
        """Port intervals of a (typed) service group used as an ACE port. -> (intervals, leaves, unresolved)."""
        key = (name, proto)
        if key in self._port_cache:
            return self._port_cache[key]
        grp = self.defs.svc_groups.get(name)
        if grp is None:
            return [], [], [self._missing(name, "port object-group not defined")]
        if self._cycle(name, "service"):
            return [], [], [name]
        self._stack.append(name)
        try:
            ivs_out: list[tuple[int, int]] = []
            leaves: list[str] = []
            unresolved: list[str] = []
            for kind, val in grp.members:
                if kind == "port":
                    ivs, bad = self._port_intervals(val, proto)  # type: ignore[arg-type]
                    unresolved += bad
                    if ivs is not None:
                        ivs_out += ivs
                        leaves += [f"{a}-{b}" if a != b else str(a) for a, b in ivs]
                elif kind == "group":
                    a, lv, u = self.port_group(val, proto)  # type: ignore[arg-type]
                    ivs_out += a
                    leaves += lv
                    unresolved += u
                else:
                    sub = self.spec_entries(val) if kind == "svc" else self.service_object(val)  # type: ignore[arg-type]
                    unresolved += sub.unresolved
                    for e in sub.entries:
                        if e.proto == proto and e.dst is not None:
                            ivs_out += e.dst
                            leaves += [f"{a}-{b}" if a != b else str(a) for a, b in e.dst]
            res = (ivs_out, leaves, unresolved)
        finally:
            self._stack.pop()
        self._port_cache[key] = res
        return res

    def protocol_group(self, name: str) -> list[str]:
        if name in self._proto_cache:
            return self._proto_cache[name]
        grp = self.defs.proto_groups.get(name)
        if grp is None or self._cycle(name, "protocol"):
            self._missing(name, "protocol object-group not defined")
            return []
        self._stack.append(name)
        try:
            out: list[str] = []
            for kind, val in grp.members:
                out += [val] if kind == "proto" else self.protocol_group(val)
        finally:
            self._stack.pop()
        self._proto_cache[name] = out
        return out

    def icmp_group(self, name: str, proto: str) -> tuple[list[int], list[str]]:
        grp = self.defs.icmp_groups.get(name)
        if grp is None or self._cycle(name, "icmp-type"):
            return [], [self._missing(name, "icmp-type object-group not defined")]
        self._stack.append(name)
        try:
            out: list[int] = []
            bad: list[str] = []
            for kind, val in grp.members:
                if kind == "type":
                    t = icmp_type(val, proto)
                    if t is None:
                        bad.append(self._missing(val, "unknown icmp type"))
                    else:
                        out.append(t)
                else:
                    a, b = self.icmp_group(val, proto)
                    out += a
                    bad += b
        finally:
            self._stack.pop()
        return out, bad

    def _ace_ports(self, ref: PortRef | None, proto: str) -> tuple[tuple[tuple[int, int], ...] | None, bool, list[str]]:
        """-> (intervals or None for any, ok, unresolved)"""
        if ref is None:
            return None, True, []
        if ref.op is not None:
            ivs, bad = self._port_intervals(ref.op, proto)
            return ivs, ivs is not None, bad
        ivs, _, bad = self.port_group(ref.group, proto)
        return tuple(ivs), not bad or bool(ivs), bad

    def ace_services(self, ace: Ace) -> ExpandedSvc:
        if ace.proto_kind == "svc_object":
            return self.service_object(ace.proto)
        if ace.proto_kind == "svc_group":
            return self.service_group(ace.proto)
        if ace.proto_kind == "proto_group":
            protos = self.protocol_group(ace.proto)
        else:
            protos = ["tcp", "udp"] if ace.proto == "tcp-udp" else [ace.proto]
        entries: list[ServiceEntry] = []
        unresolved: list[str] = []
        for p in protos:
            if p in ("tcp", "udp", "sctp"):
                src, ok1, b1 = self._ace_ports(ace.src_port, p)
                dst, ok2, b2 = self._ace_ports(ace.dst_port, p)
                unresolved += b1 + b2
                if ok1 and ok2:
                    # An ACE port group expands to one leaf per port item.
                    if ace.dst_port is not None and ace.dst_port.group and dst:
                        entries += [ServiceEntry(p, dst=(iv,), src=src) for iv in dst]
                    else:
                        entries.append(ServiceEntry(p, dst=dst, src=src))
            elif p in ("icmp", "icmp6"):
                if ace.icmp_group:
                    types, bad = self.icmp_group(ace.icmp_group, p)
                    unresolved += bad
                    entries += [ServiceEntry(p, icmp_type=t) for t in types]
                elif ace.icmp_type:
                    t = icmp_type(ace.icmp_type, p)
                    if t is None:
                        unresolved.append(self._missing(ace.icmp_type, "unknown icmp type"))
                    else:
                        code = int(ace.icmp_code) if ace.icmp_code else None
                        entries.append(ServiceEntry(p, icmp_type=t, icmp_code=code))
                else:
                    entries.append(ServiceEntry(p))
            else:
                entries.append(ServiceEntry(p))
        return ExpandedSvc(entries, unresolved)
