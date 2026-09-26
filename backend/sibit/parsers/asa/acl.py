"""Extended access-list line parser (spec 2.2 'Access-list line')."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...ports import is_icmp_type_name, protocol_name
from .objects import Definitions, PortOp, parse_port_op
from .tokenizer import is_ip, is_ipv6_prefix

LOG_LEVELS = {
    "emergencies", "alerts", "critical", "errors", "warnings",
    "notifications", "informational", "debugging",
}


@dataclass(frozen=True)
class AddrRef:
    kind: str  # any | any4 | any6 | host | net | object | group | interface
    value: str = ""

    def text(self) -> str:
        if self.kind in ("any", "any4", "any6"):
            return self.kind
        if self.kind == "host":
            return f"host {self.value}"
        if self.kind == "net":
            return self.value
        if self.kind == "object":
            return f"object {self.value}"
        if self.kind == "group":
            return f"object-group {self.value}"
        return f"interface {self.value}"

    def display(self) -> str:
        """Short 'as written' form for the UI (names without the keyword)."""
        if self.kind in ("object", "group", "interface", "host", "net"):
            return self.value
        return self.kind


@dataclass(frozen=True)
class PortRef:
    kind: str  # op | group
    op: PortOp | None = None
    group: str = ""

    def text(self) -> str:
        return self.op.text() if self.op else f"object-group {self.group}"

    def display(self) -> str:
        return self.op.text() if self.op else self.group


@dataclass
class Ace:
    acl: str
    action: str  # permit | deny
    proto_kind: str  # proto | svc_object | svc_group | proto_group
    proto: str  # protocol name or object/group name
    src: AddrRef
    dst: AddrRef
    src_port: PortRef | None = None
    dst_port: PortRef | None = None
    icmp_type: str | None = None
    icmp_code: str | None = None
    icmp_group: str | None = None
    log: bool = False
    inactive: bool = False
    time_range: str | None = None
    line: int = 0
    raw: str = ""
    remark: str = ""
    line_no_ace: int = 0
    line_no_all: int = 0
    notes: list[str] = field(default_factory=list)


class AceSyntaxError(ValueError):
    pass


def _parse_addr(t: list[str], i: int, defs: Definitions) -> tuple[AddrRef, int]:
    if i >= len(t):
        raise AceSyntaxError("missing address")
    k = t[i].lower()
    if k in ("any", "any4", "any6"):
        return AddrRef(k), i + 1
    if k == "host" and i + 1 < len(t):
        return AddrRef("host", t[i + 1]), i + 2
    if k == "object" and i + 1 < len(t):
        return AddrRef("object", t[i + 1]), i + 2
    if k == "object-group" and i + 1 < len(t):
        return AddrRef("group", t[i + 1]), i + 2
    if k == "interface" and i + 1 < len(t):
        return AddrRef("interface", t[i + 1]), i + 2
    if is_ip(t[i]) and i + 1 < len(t) and is_ip(t[i + 1]):
        return AddrRef("net", f"{t[i]} {t[i + 1]}"), i + 2
    if is_ipv6_prefix(t[i]):
        return AddrRef("net", t[i]), i + 1
    if k in ("object-group-user", "user", "user-group", "object-group-security", "security-group"):
        raise AceSyntaxError(f"identity/security-group match '{t[i]}' is not supported")
    raise AceSyntaxError(f"unexpected address token '{t[i]}'")


def _is_port_group(name: str, defs: Definitions) -> bool:
    return name in defs.svc_groups


def _parse_port(t: list[str], i: int, defs: Definitions) -> tuple[PortRef | None, int]:
    if i >= len(t):
        return None, i
    k = t[i].lower()
    if k in ("eq", "lt", "gt", "neq", "range"):
        op, j = parse_port_op(t, i)
        if op is None:
            raise AceSyntaxError("bad port operator")
        return PortRef("op", op=op), j
    if k == "object-group" and i + 1 < len(t) and _is_port_group(t[i + 1], defs):
        return PortRef("group", group=t[i + 1]), i + 2
    return None, i


def parse_ace(tokens: list[str], defs: Definitions) -> Ace:
    """Parse the tokens of 'access-list ACL extended ...'. Raises AceSyntaxError."""
    acl = tokens[1]
    t = tokens[3:]
    if not t or t[0].lower() not in ("permit", "deny"):
        raise AceSyntaxError("expected permit/deny")
    action = t[0].lower()
    i = 1
    if i >= len(t):
        raise AceSyntaxError("missing protocol")
    k = t[i].lower()
    ports_allowed = False
    proto_for_icmp: str | None = None
    if k == "object" and i + 1 < len(t):
        proto_kind, proto = "svc_object", t[i + 1]
        i += 2
    elif k == "object-group" and i + 1 < len(t):
        name = t[i + 1]
        if name in defs.proto_groups:
            proto_kind, proto = "proto_group", name
            ports_allowed = True
        else:
            proto_kind, proto = "svc_group", name
        i += 2
    else:
        p = protocol_name(t[i])
        if p is None:
            raise AceSyntaxError(f"unknown protocol '{t[i]}'")
        proto_kind, proto = "proto", p
        ports_allowed = p in ("tcp", "udp", "tcp-udp", "sctp")
        if p in ("icmp", "icmp6"):
            proto_for_icmp = p
        i += 1

    src, i = _parse_addr(t, i, defs)
    src_port = None
    if ports_allowed:
        src_port, i = _parse_port(t, i, defs)
    dst, i = _parse_addr(t, i, defs)
    dst_port = None
    if ports_allowed:
        dst_port, i = _parse_port(t, i, defs)

    ace = Ace(acl=acl, action=action, proto_kind=proto_kind, proto=proto, src=src, dst=dst,
              src_port=src_port, dst_port=dst_port)

    if proto_for_icmp and i < len(t):
        tok = t[i]
        if tok.lower() == "object-group" and i + 1 < len(t) and t[i + 1] in defs.icmp_groups:
            ace.icmp_group = t[i + 1]
            i += 2
        elif tok.isdigit() or is_icmp_type_name(tok, proto_for_icmp):
            ace.icmp_type = tok
            i += 1
            if i < len(t) and t[i].isdigit():
                ace.icmp_code = t[i]
                i += 1

    # Trailing options.
    while i < len(t):
        k = t[i].lower()
        if k == "log":
            i += 1
            ace.log = True
            if i < len(t) and t[i].lower() == "disable":
                ace.log = False
                i += 1
                continue
            if i < len(t) and t[i].lower() == "default":
                i += 1
                continue
            if i < len(t) and (t[i].isdigit() or t[i].lower() in LOG_LEVELS):
                i += 1
            if i + 1 < len(t) and t[i].lower() == "interval":
                i += 2
        elif k == "time-range" and i + 1 < len(t):
            ace.time_range = t[i + 1]
            i += 2
        elif k == "inactive":
            ace.inactive = True
            i += 1
        else:
            raise AceSyntaxError(f"unexpected token '{t[i]}'")
    return ace
