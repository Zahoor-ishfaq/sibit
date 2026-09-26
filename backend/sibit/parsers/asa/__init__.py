"""Cisco ASA running-config parser (spec section 2).

    result = parse_asa(text)
    result.rules      -> list[Rule] (side="ASA"), in config order
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ciscoconfparse2 import CiscoConfParse

from ...model import Rule, ServiceSet, normalize_comment
from ...ports import PortResolver
from ..common import Cancelled, ParseWarning, ProgressFn, UnresolvedRef
from .acl import Ace, AceSyntaxError, parse_ace
from .objects import Definitions, parse_block
from .resolver import AsaResolver
from .tokenizer import apply_names, collect_names, sanitize_lines

__all__ = ["parse_asa", "AsaResult", "detect_asa"]

_VERSION_RE = re.compile(r"^ASA Version\s+(\S+)", re.IGNORECASE)
_BLOCK_KW = ("object ", "object-group ", "interface ")


@dataclass
class AsaResult:
    rules: list[Rule]
    defs: Definitions
    resolver: AsaResolver
    warnings: list[ParseWarning]
    unresolved: list[UnresolvedRef]
    zones: dict[str, str]  # ACL -> nameif
    hostname: str | None = None
    version: str | None = None
    secret_lines_removed: int = 0
    skipped_acl_lines: dict[str, int] = field(default_factory=dict)  # 'standard' -> count
    line_count: int = 0

    def summary(self) -> dict:
        acls: dict[str, int] = {}
        for r in self.rules:
            acls[r.acl] = acls.get(r.acl, 0) + 1
        d = self.defs
        return {
            "hostname": self.hostname,
            "version": self.version,
            "lines": self.line_count,
            "rules": len(self.rules),
            "rules_inactive": sum(1 for r in self.rules if not r.enabled),
            "acls": acls,
            "zones": self.zones,
            "network_objects": len(d.net_objects),
            "network_groups": len(d.net_groups),
            "service_objects": len(d.svc_objects),
            "service_groups": len(d.svc_groups),
            "protocol_groups": len(d.proto_groups),
            "icmp_groups": len(d.icmp_groups),
            "interfaces": len(d.interfaces),
            "unresolved": len(self.unresolved),
            "warnings": len(self.warnings),
            "secret_lines_removed": self.secret_lines_removed,
            "skipped_acl_lines": self.skipped_acl_lines,
        }


def detect_asa(head: str) -> dict:
    """Cheap type check on the first KB of a file for the upload screen."""
    m = re.search(r"^ASA Version\s+(\S+)", head, re.IGNORECASE | re.MULTILINE)
    ok = bool(m) or bool(re.search(r"^(access-list|object-group|object network|nameif)\b", head, re.MULTILINE))
    version = m.group(1) if m else None
    short = None
    if version:
        mm = re.match(r"(\d+\.\d+)", version)
        short = mm.group(1) if mm else version
    return {"ok": ok, "version": version, "label": f"Cisco ASA {short} config detected" if short else ("Cisco ASA config detected" if ok else None)}


def _svc_refs(ace: Ace) -> list[str]:
    if ace.proto_kind in ("svc_object", "svc_group"):
        return [ace.proto]
    base = ace.proto
    out = []
    if ace.src_port:
        out.append(f"{base} src {ace.src_port.display()}")
    if ace.dst_port:
        out.append(f"{base} {ace.dst_port.display()}")
    if ace.icmp_group:
        out.append(f"{base} {ace.icmp_group}")
    elif ace.icmp_type:
        out.append(f"{base} {ace.icmp_type}" + (f" {ace.icmp_code}" if ace.icmp_code else ""))
    if not out:
        out.append(base)
    return out


def parse_asa(
    text: str,
    *,
    ports: PortResolver | None = None,
    progress: ProgressFn | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> AsaResult:
    ports = ports or PortResolver()
    lines, removed = sanitize_lines(text)
    warnings: list[ParseWarning] = []
    defs = Definitions()
    hostname = version = None
    total = len(lines)

    def report(step: str, **kw: object) -> None:
        if progress:
            progress(step, dict(kw))

    def check_cancel() -> None:
        if is_cancelled and is_cancelled():
            raise Cancelled()

    report("asa_read", lines=total)
    names = collect_names(lines)
    if names:
        lines = [apply_names(ln, names) if not ln.startswith("name ") else ln for ln in lines]

    # Split the config: multi-line blocks (object/object-group/interface) go to
    # ciscoconfparse2 for the parent/child tree; single-line top-level commands
    # (access-list, access-group, hostname, ...) have no children and are
    # handled directly, which keeps 30k-line configs fast.
    block_lines: list[str] = []
    block_linenos: list[int] = []
    acl_lines: list[tuple[int, str]] = []
    access_groups: dict[str, str] = {}
    in_block = False
    for i, t in enumerate(lines):
        ln = i + 1
        if t[:1] in (" ", "	"):
            if in_block:
                block_lines.append(t)
                block_linenos.append(ln)
            continue
        low = t.lower()
        in_block = low.startswith(_BLOCK_KW)
        if in_block:
            block_lines.append(t)
            block_linenos.append(ln)
        elif low.startswith("access-list "):
            acl_lines.append((ln, t.strip()))
        elif low.startswith("access-group "):
            tk = t.split()
            if len(tk) >= 5 and tk[2].lower() == "in" and tk[3].lower() == "interface":
                access_groups[tk[1]] = tk[4]
            elif len(tk) >= 3 and tk[2].lower() == "global":
                access_groups[tk[1]] = "global"
            elif len(tk) >= 5 and tk[2].lower() == "out" and tk[3].lower() == "interface":
                access_groups.setdefault(tk[1], tk[4])
                warnings.append(ParseWarning("ASA", ln, t.strip(), "Outbound access-group: zone recorded as the interface"))
        elif low.startswith("hostname "):
            hostname = t.split(None, 1)[1].strip()
        elif version is None and (m := _VERSION_RE.match(t)):
            version = m.group(1)

    # Pass 1: definitions (objects must be known before ACEs are tokenised,
    # because 'object-group X' after an address is a port group only if X is
    # a service group).
    check_cancel()
    parse = CiscoConfParse(block_lines, syntax="asa", ignore_blank_lines=False) if block_lines else None
    top = [o for o in parse.objs if o.indent == 0] if parse else []
    for n, o in enumerate(top):
        if n % 2000 == 0:
            check_cancel()
            report("asa_objects", done=n, total=len(top))
        t = o.text
        ln = block_linenos[o.linenum]
        children = [(block_linenos[c.linenum], c.text) for c in o.children]
        try:
            parse_block(t, children, ln, defs, warnings)
        except Exception as e:  # noqa: BLE001 - never crash on unknown syntax
            warnings.append(ParseWarning("ASA", ln, t.strip(), f"Could not parse block: {e}"))

    resolver = AsaResolver(defs, ports, warnings)

    # Pass 2: ACEs.
    rules: list[Rule] = []
    ace_idx: dict[str, int] = {}
    all_idx: dict[str, int] = {}
    pending_remark: dict[str, list[str]] = {}
    skipped: dict[str, int] = {}
    for n, (ln, t) in enumerate(acl_lines):
        if n % 1000 == 0:
            check_cancel()
            report("asa_rules", done=n, total=len(acl_lines), rules=len(rules))
        tk = t.split()
        if len(tk) < 3:
            warnings.append(ParseWarning("ASA", ln, t, "Truncated access-list line"))
            continue
        acl, kind = tk[1], tk[2].lower()
        if kind == "remark":
            all_idx[acl] = all_idx.get(acl, 0) + 1
            text = t.split(None, 3)[3] if len(tk) > 3 else ""
            pending_remark.setdefault(acl, []).append(text.strip())
            continue
        if kind in ("standard", "webtype", "ethertype"):
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        if kind != "extended":
            warnings.append(ParseWarning("ASA", ln, t, f"Unsupported access-list type '{tk[2]}'"))
            continue
        all_idx[acl] = all_idx.get(acl, 0) + 1
        ace_idx[acl] = ace_idx.get(acl, 0) + 1
        remark = " | ".join(pending_remark.pop(acl, []))
        try:
            ace = parse_ace(tk, defs)
        except AceSyntaxError as e:
            warnings.append(ParseWarning("ASA", ln, t, f"Could not parse ACE: {e}"))
            continue
        ace.line, ace.raw, ace.remark = ln, t, remark
        ace.line_no_ace, ace.line_no_all = ace_idx[acl], all_idx[acl]
        rules.append(_to_rule(ace, resolver, access_groups.get(acl)))

    for kind, cnt in skipped.items():
        warnings.append(ParseWarning("ASA", None, f"{cnt} line(s)", f"Skipped {kind} access-list lines (not compared)"))

    used_by: dict[str, list[str]] = {}
    for r in rules:
        for u in r.unresolved:
            used_by.setdefault(u, []).append(r.uid)
    unresolved = [
        UnresolvedRef("ASA", name, reason, used_by.get(name, []))
        for name, reason in sorted(resolver.unresolved_names.items())
    ]
    report("asa_done", rules=len(rules), objects=len(defs.net_objects) + len(defs.svc_objects),
           groups=len(defs.net_groups) + len(defs.svc_groups))
    return AsaResult(
        rules=rules,
        defs=defs,
        resolver=resolver,
        warnings=warnings,
        unresolved=unresolved,
        zones=access_groups,
        hostname=hostname,
        version=version,
        secret_lines_removed=removed,
        skipped_acl_lines=skipped,
        line_count=total,
    )


def _closure(defs: Definitions, name: str, out: set[str]) -> None:
    if name in out:
        return
    out.add(name)
    for grp in (defs.net_groups.get(name), defs.svc_groups.get(name), defs.proto_groups.get(name), defs.icmp_groups.get(name)):
        if grp is None:
            continue
        for kind, val in grp.members:
            if kind in ("object", "group"):
                _closure(defs, str(val), out)


def _ref_names(ace: Ace, defs: Definitions) -> frozenset[str]:
    out: set[str] = set()
    for ref in (ace.src, ace.dst):
        if ref.kind in ("object", "group"):
            _closure(defs, ref.value, out)
    if ace.proto_kind != "proto":
        _closure(defs, ace.proto, out)
    for pref in (ace.src_port, ace.dst_port):
        if pref is not None and pref.group:
            _closure(defs, pref.group, out)
    if ace.icmp_group:
        _closure(defs, ace.icmp_group, out)
    return frozenset(out)


def _to_rule(ace: Ace, resolver: AsaResolver, zone: str | None) -> Rule:
    src = resolver.address(ace.src)
    dst = resolver.address(ace.dst)
    svc = resolver.ace_services(ace)
    unresolved = list(dict.fromkeys(src.unresolved + dst.unresolved + svc.unresolved))
    return Rule(
        side="ASA",
        key=f"{ace.acl}_#{ace.line_no_ace}",
        acl=ace.acl,
        line_no=ace.line_no_ace,
        position=None,
        source_zone=zone,
        action=ace.action,  # type: ignore[arg-type]
        enabled=not ace.inactive,
        log=ace.log,
        comment=normalize_comment(ace.remark),
        raw_text=ace.raw,
        src_refs=[ace.src.display()],
        dst_refs=[ace.dst.display()],
        svc_refs=_svc_refs(ace),
        src=src.addrs,
        dst=dst.addrs,
        services=ServiceSet.from_entries(svc.entries),
        unresolved=unresolved,
        src_leaves=tuple(sorted(src.leaves)),
        dst_leaves=tuple(sorted(dst.leaves)),
        svc_leaves=tuple(sorted(e.leaf() for e in svc.entries)),
        ref_names=_ref_names(ace, resolver.defs),
        line_no_ace=ace.line_no_ace,
        line_no_all=ace.line_no_all,
        uid=f"ASA:{ace.acl}:{ace.line_no_ace}",
    )
