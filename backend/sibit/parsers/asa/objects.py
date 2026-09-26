"""Object and object-group definitions (spec 2.2), parsed but not yet expanded."""
from __future__ import annotations

from dataclasses import dataclass, field

from netaddr import IPNetwork, IPRange

from ...ports import PORT_MAX, PORT_MIN, PortResolver, icmp_type, protocol_name
from ..common import ParseWarning
from .tokenizer import is_ip, is_ipv6_prefix, mask_to_net

PORT_OPS = ("eq", "lt", "gt", "neq", "range")


@dataclass(frozen=True)
class PortOp:
    kind: str  # eq | lt | gt | neq | range
    args: tuple[str, ...]

    def text(self) -> str:
        return f"{self.kind} {' '.join(self.args)}"

    def intervals(self, proto: str, ports: PortResolver) -> tuple[tuple[tuple[int, int], ...] | None, list[str]]:
        """Resolve to port intervals for ``proto``. Returns (intervals|None, unresolved names)."""
        vals: list[int] = []
        bad: list[str] = []
        for a in self.args:
            v = ports.port(a, proto)
            if v is None:
                bad.append(a)
            else:
                vals.append(v)
        if bad:
            return None, bad
        k = self.kind
        if k == "eq":
            x = vals[0]
            return ((x, x),), []
        if k == "range":
            a, b = sorted(vals[:2])
            return ((max(a, PORT_MIN), b),), []
        if k == "lt":
            x = vals[0]
            return (((PORT_MIN, x - 1),) if x - 1 >= PORT_MIN else ()), []
        if k == "gt":
            x = vals[0]
            return (((x + 1, PORT_MAX),) if x < PORT_MAX else ()), []
        if k == "neq":
            x = vals[0]
            out = []
            if x - 1 >= PORT_MIN:
                out.append((PORT_MIN, x - 1))
            if x + 1 <= PORT_MAX:
                out.append((x + 1, PORT_MAX))
            return tuple(out), []
        return None, [self.text()]


def parse_port_op(tokens: list[str], i: int) -> tuple[PortOp | None, int]:
    """Parse a port operator at tokens[i]. Returns (op, next index) or (None, i)."""
    if i >= len(tokens):
        return None, i
    k = tokens[i].lower()
    if k == "range" and i + 2 < len(tokens):
        return PortOp("range", (tokens[i + 1], tokens[i + 2])), i + 3
    if k in ("eq", "lt", "gt", "neq") and i + 1 < len(tokens):
        return PortOp(k, (tokens[i + 1],)), i + 2
    return None, i


@dataclass(frozen=True)
class SvcSpec:
    """One service definition: 'tcp source eq 1 destination range 2 3', 'icmp echo 0', 'ip'."""

    proto: str  # canonical protocol name, 'tcp-udp' or 'ip'
    src: PortOp | None = None
    dst: PortOp | None = None
    icmp_type: str | None = None
    icmp_code: str | None = None

    def text(self) -> str:
        parts = [self.proto]
        if self.src:
            parts += ["source", self.src.text()]
        if self.dst:
            parts += ["destination", self.dst.text()]
        if self.icmp_type:
            parts.append(self.icmp_type)
        if self.icmp_code:
            parts.append(self.icmp_code)
        return " ".join(parts)


def parse_svc_tokens(tokens: list[str]) -> SvcSpec:
    """Parse '<proto> [source OP] [destination OP]' or '<icmp> [type [code]]'.

    Accepts the legacy form without the 'destination' keyword
    ('tcp eq 80' means destination port 80). Raises ValueError.
    """
    if not tokens:
        raise ValueError("empty service")
    proto = protocol_name(tokens[0])
    if proto is None:
        raise ValueError(f"unknown protocol '{tokens[0]}'")
    rest = tokens[1:]
    if proto in ("icmp", "icmp6"):
        if not rest:
            return SvcSpec(proto)
        t = rest[0]
        if icmp_type(t, proto) is None:
            raise ValueError(f"unknown icmp type '{t}'")
        code = rest[1] if len(rest) > 1 and rest[1].isdigit() else None
        return SvcSpec(proto, icmp_type=t, icmp_code=code)
    src = dst = None
    i = 0
    while i < len(rest):
        kw = rest[i].lower()
        if kw == "source":
            src, j = parse_port_op(rest, i + 1)
            if src is None:
                raise ValueError("bad source port")
            i = j
        elif kw == "destination":
            dst, j = parse_port_op(rest, i + 1)
            if dst is None:
                raise ValueError("bad destination port")
            i = j
        elif kw in PORT_OPS:
            dst, j = parse_port_op(rest, i)
            if dst is None:
                raise ValueError("bad port")
            i = j
        else:
            raise ValueError(f"unexpected token '{rest[i]}'")
    if (src or dst) and proto not in ("tcp", "udp", "tcp-udp", "sctp"):
        raise ValueError(f"ports not allowed for protocol {proto}")
    return SvcSpec(proto, src=src, dst=dst)


# --------------------------------------------------------------------------- #
# Definitions
# --------------------------------------------------------------------------- #
@dataclass
class NetworkObject:
    name: str
    line: int
    kind: str | None = None  # host | subnet | range | fqdn
    value: object = None  # IPNetwork | IPRange | str


@dataclass
class NetworkGroup:
    name: str
    line: int
    # (kind, value): ('net', IPNetwork) | ('object', name) | ('group', name)
    members: list[tuple[str, object]] = field(default_factory=list)


@dataclass
class ServiceObject:
    name: str
    line: int
    spec: SvcSpec | None = None


@dataclass
class ServiceGroup:
    name: str
    line: int
    typed: str | None = None  # tcp | udp | tcp-udp for "port-object" groups
    # ('port', PortOp) | ('svc', SvcSpec) | ('object', name) | ('group', name)
    members: list[tuple[str, object]] = field(default_factory=list)


@dataclass
class ProtocolGroup:
    name: str
    line: int
    members: list[tuple[str, str]] = field(default_factory=list)  # ('proto', p) | ('group', name)


@dataclass
class IcmpGroup:
    name: str
    line: int
    members: list[tuple[str, str]] = field(default_factory=list)  # ('type', t) | ('group', name)


@dataclass
class Interface:
    hw: str
    nameif: str | None = None
    ip: str | None = None


@dataclass
class Definitions:
    net_objects: dict[str, NetworkObject] = field(default_factory=dict)
    net_groups: dict[str, NetworkGroup] = field(default_factory=dict)
    svc_objects: dict[str, ServiceObject] = field(default_factory=dict)
    svc_groups: dict[str, ServiceGroup] = field(default_factory=dict)
    proto_groups: dict[str, ProtocolGroup] = field(default_factory=dict)
    icmp_groups: dict[str, IcmpGroup] = field(default_factory=dict)
    interfaces: dict[str, Interface] = field(default_factory=dict)  # by nameif
    other_groups: set[str] = field(default_factory=set)  # user/security groups (unsupported)

    def group_kind(self, name: str) -> str | None:
        if name in self.net_groups:
            return "network"
        if name in self.svc_groups:
            return "service"
        if name in self.proto_groups:
            return "protocol"
        if name in self.icmp_groups:
            return "icmp-type"
        if name in self.other_groups:
            return "other"
        return None

    def object_kind(self, name: str) -> str | None:
        if name in self.net_objects:
            return "network"
        if name in self.svc_objects:
            return "service"
        return None


def _net_member(tokens: list[str]) -> tuple[str, object]:
    """Parse 'host IP' | 'IP MASK' | 'IPv6/len' | 'object NAME'."""
    if not tokens:
        raise ValueError("empty network-object")
    k = tokens[0].lower()
    if k == "host" and len(tokens) >= 2 and is_ip(tokens[1]):
        return "net", IPNetwork(tokens[1])
    if k == "object" and len(tokens) >= 2:
        return "object", tokens[1]
    if is_ip(tokens[0]) and len(tokens) >= 2 and is_ip(tokens[1]):
        return "net", mask_to_net(tokens[0], tokens[1])
    if is_ipv6_prefix(tokens[0]):
        return "net", IPNetwork(tokens[0])
    if is_ip(tokens[0]) and len(tokens) == 1:
        return "net", IPNetwork(tokens[0])
    raise ValueError("unrecognised network-object")


def parse_block(
    header: str,
    children: list[tuple[int, str]],
    line_no: int,
    defs: Definitions,
    warnings: list[ParseWarning],
) -> None:
    """Parse one 'object ...' / 'object-group ...' / 'interface ...' block into ``defs``."""
    h = header.split()
    kw = h[0].lower()

    def warn(ln: int, text: str, msg: str) -> None:
        warnings.append(ParseWarning("ASA", ln, text.strip(), msg))

    if kw == "interface":
        itf = Interface(hw=" ".join(h[1:]))
        for ln, text in children:
            t = text.split()
            if not t:
                continue
            if t[0].lower() == "nameif" and len(t) > 1:
                itf.nameif = t[1]
            elif t[0].lower() == "ip" and len(t) > 2 and t[1].lower() == "address" and is_ip(t[2]):
                itf.ip = t[2]
        if itf.nameif:
            defs.interfaces[itf.nameif] = itf
        return

    if kw == "object" and len(h) >= 3:
        otype, name = h[1].lower(), h[2]
        if otype == "network":
            obj = NetworkObject(name, line_no)
            for ln, text in children:
                t = text.split()
                if not t:
                    continue
                k = t[0].lower()
                try:
                    if k == "host" and len(t) >= 2:
                        obj.kind, obj.value = "host", IPNetwork(t[1])
                    elif k == "subnet" and len(t) >= 3:
                        obj.kind, obj.value = "subnet", mask_to_net(t[1], t[2])
                    elif k == "subnet" and len(t) == 2:
                        obj.kind, obj.value = "subnet", IPNetwork(t[1])
                    elif k == "range" and len(t) >= 3:
                        obj.kind, obj.value = "range", IPRange(t[1], t[2])
                    elif k == "fqdn" and len(t) >= 2:
                        obj.kind, obj.value = "fqdn", t[-1]
                    elif k in ("description", "nat"):
                        continue
                    else:
                        warn(ln, text, f"Unsupported line in object network {name}")
                except Exception:  # noqa: BLE001 - never crash on bad syntax
                    warn(ln, text, f"Invalid value in object network {name}")
            defs.net_objects[name] = obj
        elif otype == "service":
            obj = ServiceObject(name, line_no)
            for ln, text in children:
                t = text.split()
                if not t or t[0].lower() == "description":
                    continue
                if t[0].lower() == "service":
                    try:
                        obj.spec = parse_svc_tokens(t[1:])
                    except ValueError as e:
                        warn(ln, text, f"object service {name}: {e}")
                else:
                    warn(ln, text, f"Unsupported line in object service {name}")
            defs.svc_objects[name] = obj
        return

    # Comment lines inside blocks ('! ...') and trailing ' ! comment' are not configuration.
    children = [(ln, text.split(" !", 1)[0].rstrip()) for ln, text in children if not text.lstrip().startswith("!")]

    if kw == "object-group" and len(h) >= 4 and h[1].lower() == "group":
        # Legacy form 'object-group group <type> NAME' holding only group-objects.
        h = [h[0], h[2], h[3]]
    if kw == "object-group" and len(h) >= 3:
        gtype, name = h[1].lower(), h[2]
        if gtype == "network":
            grp = NetworkGroup(name, line_no)
            for ln, text in children:
                t = text.split()
                if not t or t[0].lower() == "description":
                    continue
                k = t[0].lower()
                try:
                    if k == "network-object":
                        grp.members.append(_net_member(t[1:]))
                    elif k == "group-object" and len(t) >= 2:
                        grp.members.append(("group", t[1]))
                    else:
                        warn(ln, text, f"Unsupported line in object-group network {name}")
                except Exception as e:  # noqa: BLE001
                    warn(ln, text, f"object-group network {name}: {e}")
            defs.net_groups[name] = grp
        elif gtype == "service":
            typed = h[3].lower() if len(h) >= 4 else None
            grp = ServiceGroup(name, line_no, typed=typed)
            for ln, text in children:
                t = text.split()
                if not t or t[0].lower() == "description":
                    continue
                k = t[0].lower()
                try:
                    if k == "port-object":
                        op, _ = parse_port_op(t, 1)
                        if op is None:
                            raise ValueError("bad port-object")
                        grp.members.append(("port", op))
                    elif k == "service-object" and len(t) >= 3 and t[1].lower() == "object":
                        grp.members.append(("object", t[2]))
                    elif k == "service-object":
                        grp.members.append(("svc", parse_svc_tokens(t[1:])))
                    elif k == "group-object" and len(t) >= 2:
                        grp.members.append(("group", t[1]))
                    else:
                        warn(ln, text, f"Unsupported line in object-group service {name}")
                except ValueError as e:
                    warn(ln, text, f"object-group service {name}: {e}")
            defs.svc_groups[name] = grp
        elif gtype == "protocol":
            grp = ProtocolGroup(name, line_no)
            for ln, text in children:
                t = text.split()
                if not t or t[0].lower() == "description":
                    continue
                k = t[0].lower()
                if k == "protocol-object" and len(t) >= 2:
                    p = protocol_name(t[1])
                    if p is None:
                        warn(ln, text, f"Unknown protocol in object-group protocol {name}")
                    else:
                        grp.members.append(("proto", p))
                elif k == "group-object" and len(t) >= 2:
                    grp.members.append(("group", t[1]))
                else:
                    warn(ln, text, f"Unsupported line in object-group protocol {name}")
            defs.proto_groups[name] = grp
        elif gtype == "icmp-type":
            grp = IcmpGroup(name, line_no)
            for ln, text in children:
                t = text.split()
                if not t or t[0].lower() == "description":
                    continue
                k = t[0].lower()
                if k == "icmp-object" and len(t) >= 2:
                    grp.members.append(("type", t[1]))
                elif k == "group-object" and len(t) >= 2:
                    grp.members.append(("group", t[1]))
                else:
                    warn(ln, text, f"Unsupported line in object-group icmp-type {name}")
            defs.icmp_groups[name] = grp
        else:
            defs.other_groups.add(name)
            warnings.append(
                ParseWarning("ASA", line_no, header.strip(), f"object-group type '{gtype}' is not supported; ignored")
            )
