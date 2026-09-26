"""RunResult -> plain data ("session") consumed by the API, exports and project files.

Everything the UI shows comes from this structure, so a saved .sibit project
reopens exactly as it was, without re-parsing the (confidential) inputs.
"""
from __future__ import annotations

import uuid

from .compare.engine import Comparison, RulePair
from .model import Rule, ServiceSet
from .parsers.asa import AsaResult
from .parsers.ftd import FtdResult
from .pipeline import RunResult

SCHEMA_VERSION = 1


def rule_dict(r: Rule | None) -> dict | None:
    if r is None:
        return None
    return {
        "side": r.side,
        "uid": r.uid,
        "key": r.key,
        "acl": r.acl,
        "line_no": r.line_no,
        "line_no_ace": r.line_no_ace,
        "line_no_all": r.line_no_all,
        "position": r.position,
        "source_zone": r.source_zone,
        "dest_zone": r.dest_zone,
        "action": r.action,
        "action_text": r.action_text,
        "enabled": r.enabled,
        "log": r.log,
        "comment": r.comment,
        "raw_text": r.raw_text,
        "src_refs": r.src_refs,
        "dst_refs": r.dst_refs,
        "svc_refs": r.svc_refs,
        "src": r.src.labels(),
        "dst": r.dst.labels(),
        "services": r.services.labels(),
        "src_any": r.src.is_any,
        "dst_any": r.dst.is_any,
        "svc_any": r.services.is_any,
        "unresolved": r.unresolved,
        "ref_names": sorted(r.ref_names),
    }


def _short(items: list[str], n: int = 3) -> str:
    if not items:
        return ""
    s = ", ".join(items[:n])
    return s + (f" +{len(items) - n}" if len(items) > n else "")


def row_dict(p: RulePair) -> dict:
    r = p.ftd or p.asa
    assert r is not None
    return {
        "id": p.id,
        "status": p.status,
        "severity": p.severity,
        "key": p.key,
        "acl": p.acl,
        "zone": (p.asa.source_zone if p.asa else None) or (p.ftd.source_zone if p.ftd else None),
        "action": p.action,
        "action_text": (p.ftd.action_text if p.ftd else "") or p.action,
        "src": _short(r.src_refs),
        "dst": _short(r.dst_refs),
        "services": _short(r.svc_refs),
        "src_any": r.src.is_any,
        "dst_any": r.dst.is_any,
        "enabled": p.enabled,
        "asa_enabled": p.asa.enabled if p.asa else None,
        "ftd_enabled": p.ftd.enabled if p.ftd else None,
        "flags": [f.code for f in p.flags],
        "matched_by": p.matched_by,
        "asa_key": p.asa.key if p.asa else None,
        "ftd_key": p.ftd.key if p.ftd else None,
        "asa_line": p.asa.line_no if p.asa else None,
        "ftd_position": p.ftd.position if p.ftd else None,
        "changed_fields": [k for k, d in p.diffs.items() if d.changed and not d.ignored] if p.asa and p.ftd else [],
    }


def detail_dict(p: RulePair) -> dict:
    return {
        "id": p.id,
        "key": p.key,
        "acl": p.acl,
        "status": p.status,
        "severity": p.severity,
        "matched_by": p.matched_by,
        "flags": [f.to_dict() for f in p.flags],
        "diffs": {k: d.to_dict() for k, d in p.diffs.items()},
        "notes": p.notes,
        "explanation": p.explanation,
        "disabled_badge": p.disabled_badge,
        "asa": rule_dict(p.asa),
        "ftd": rule_dict(p.ftd),
    }


def _search_blob(p: RulePair) -> str:
    parts: list[str] = [p.key, p.acl]
    for r in (p.asa, p.ftd):
        if r is None:
            continue
        parts += [r.key, r.comment, r.action_text or r.action]
        parts += r.src_refs + r.dst_refs + r.svc_refs + sorted(r.ref_names)
        parts += r.services.labels()
    return " ".join(x for x in parts if x).lower()


def _ranges(p: RulePair) -> list[tuple[int, int, int]]:
    """(version, first, last) IP ranges touched by either side of the pair."""
    out: list[tuple[int, int, int]] = []
    for r in (p.asa, p.ftd):
        if r is None:
            continue
        for s in (r.src, r.dst):
            for rng in s.ranges():
                out.append((rng.version, int(rng.first), int(rng.last)))
    return out


def _ports(p: RulePair) -> list[tuple[int, int]]:
    """Port intervals of either side ([(1, 65535)] when any tcp/udp port is allowed)."""
    out: list[tuple[int, int]] = []
    for r in (p.asa, p.ftd):
        if r is None:
            continue
        s: ServiceSet = r.services
        if s.all_ip or any(x in s.protos for x in ("tcp", "udp", "sctp")):
            out.append((1, 65535))
        for ivs in s.ports.values():
            out += list(ivs)
    return out


# --------------------------------------------------------------------------- #
# Objects (Objects screen)
# --------------------------------------------------------------------------- #
def _asa_objects(asa: AsaResult, used_by: dict[str, list[int]]) -> list[dict]:
    d, res = asa.defs, asa.resolver
    out: list[dict] = []
    for name, o in d.net_objects.items():
        exp = res.network_object(name)
        out.append({"side": "ASA", "name": name, "kind": "network object", "line": o.line,
                    "members": [{"text": f"{o.kind} {_val(o.value)}" if o.kind else "(empty)", "ref": None}],
                    "expanded": exp.addrs.labels(), "unresolved": exp.unresolved, "used_by": used_by.get(name, [])})
    for name, g in d.net_groups.items():
        exp = res.network_group(name)
        members = []
        for kind, val in g.members:
            if kind == "net":
                members.append({"text": _val(val), "ref": None})
            else:
                members.append({"text": f"{'object' if kind == 'object' else 'group-object'} {val}", "ref": str(val)})
        out.append({"side": "ASA", "name": name, "kind": "network group", "line": g.line, "members": members,
                    "expanded": exp.addrs.labels(), "unresolved": exp.unresolved, "used_by": used_by.get(name, [])})
    for name, o in d.svc_objects.items():
        exp = res.service_object(name)
        out.append({"side": "ASA", "name": name, "kind": "service object", "line": o.line,
                    "members": [{"text": f"service {o.spec.text()}" if o.spec else "(empty)", "ref": None}],
                    "expanded": ServiceSet.from_entries(exp.entries).labels(), "unresolved": exp.unresolved,
                    "used_by": used_by.get(name, [])})
    for name, g in d.svc_groups.items():
        exp = res.service_group(name)
        members = []
        for kind, val in g.members:
            if kind == "port":
                members.append({"text": f"port-object {val.text()}", "ref": None})  # type: ignore[union-attr]
            elif kind == "svc":
                members.append({"text": f"service-object {val.text()}", "ref": None})  # type: ignore[union-attr]
            elif kind == "object":
                members.append({"text": f"service-object object {val}", "ref": str(val)})
            else:
                members.append({"text": f"group-object {val}", "ref": str(val)})
        out.append({"side": "ASA", "name": name, "kind": f"service group{' (' + g.typed + ')' if g.typed else ''}",
                    "line": g.line, "members": members,
                    "expanded": ServiceSet.from_entries(exp.entries).labels(), "unresolved": exp.unresolved,
                    "used_by": used_by.get(name, [])})
    for name, g in d.proto_groups.items():
        members = [{"text": f"protocol-object {v}" if k == "proto" else f"group-object {v}",
                    "ref": v if k == "group" else None} for k, v in g.members]
        out.append({"side": "ASA", "name": name, "kind": "protocol group", "line": g.line, "members": members,
                    "expanded": [p.upper() for p in res.protocol_group(name)], "unresolved": [],
                    "used_by": used_by.get(name, [])})
    for name, g in d.icmp_groups.items():
        members = [{"text": f"icmp-object {v}" if k == "type" else f"group-object {v}",
                    "ref": v if k == "group" else None} for k, v in g.members]
        types, bad = res.icmp_group(name, "icmp")
        out.append({"side": "ASA", "name": name, "kind": "icmp-type group", "line": g.line, "members": members,
                    "expanded": [f"ICMP type {t}" for t in types], "unresolved": bad,
                    "used_by": used_by.get(name, [])})
    return out


def _val(v: object) -> str:
    return str(v)


def _ftd_objects(ftd: FtdResult, used_by: dict[str, list[int]]) -> list[dict]:
    from .parsers.ftd.values import parse_port_literal

    res = ftd.resolver
    out: list[dict] = []
    for name, o in ftd.objects.items():
        is_port = o.section == "port" or any(parse_port_literal(v) is not None for v in o.values)
        if is_port:
            entries, un = res.port_name(name)
            expanded = ServiceSet.from_entries(entries).labels()
        else:
            s, _, un = res.network_name(name)
            expanded = s.labels()
        members = [{"text": v, "ref": v if v in ftd.objects else None} for v in o.values]
        kind = {"group": "object group", "network": "network object", "port": "port object"}.get(o.section, o.section)
        out.append({"side": "FTD", "name": name, "kind": kind + (f" ({o.type})" if o.type else ""),
                    "line": o.page, "members": members, "expanded": expanded, "unresolved": un,
                    "used_by": used_by.get(name, [])})
    return out


# --------------------------------------------------------------------------- #
def build_session(rr: RunResult, name: str | None = None) -> dict:
    comp: Comparison = rr.comparison
    pairs = comp.pairs
    used_asa: dict[str, list[int]] = {}
    used_ftd: dict[str, list[int]] = {}
    for p in pairs:
        if p.asa is not None:
            for n in p.asa.ref_names:
                used_asa.setdefault(n, []).append(p.id)
        if p.ftd is not None:
            for n in p.ftd.ref_names:
                used_ftd.setdefault(n, []).append(p.id)
    uid_to_pair = {r.uid: p.id for p in pairs for r in (p.asa, p.ftd) if r is not None}
    asa_s = rr.asa.summary()
    ftd_s = rr.ftd.summary()
    meta = {
        "schema": SCHEMA_VERSION,
        "id": uuid.uuid4().hex[:12],
        "name": name or _default_name(rr),
        "asa_name": rr.asa_name,
        "ftd_name": rr.ftd_name,
        "created": rr.created,
        "options": comp.options.to_dict(),
        "asa_summary": asa_s,
        "ftd_summary": ftd_s,
        "seconds": rr.seconds,
        "calibration": comp.calibration(),
        "counts": comp.counts(),
        "per_acl": comp.per_acl(),
        "order_change_count": len(comp.order_changes),
        "excluded_disabled": comp.excluded_disabled,
    }
    return {
        "meta": meta,
        "rows": [row_dict(p) for p in pairs],
        "details": [detail_dict(p) for p in pairs],
        "order_changes": [o.to_dict() for o in comp.order_changes],
        "warnings": [w.to_dict() for w in comp.warnings],
        "unresolved": [
            u.to_dict() | {"used_by": [uid_to_pair[x] for x in u.used_by if x in uid_to_pair]}
            for u in comp.unresolved
        ],
        "objects": _asa_objects(rr.asa, used_asa) + _ftd_objects(rr.ftd, used_ftd),
        "search": [{"text": _search_blob(p), "ranges": _ranges(p), "ports": _ports(p)} for p in pairs],
    }


def _default_name(rr: RunResult) -> str:
    host = rr.asa.hostname or rr.ftd.policy.hostname or "Comparison"
    return f"{host} — ASA → FTD"
