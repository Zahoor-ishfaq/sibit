"""Field-by-field comparison of a matched ASA/FTD rule pair (spec section 6)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Rule
from ..parsers.ftd.values import name_convention_network, name_convention_port

FIELDS = ("action", "enabled", "src", "dst", "services", "log", "comment")
FIELD_LABELS = {
    "action": "Action",
    "enabled": "Enabled",
    "src": "Source",
    "dst": "Destination",
    "services": "Services",
    "log": "Logging",
    "comment": "Comment",
}


@dataclass
class FieldDiff:
    field: str
    asa: list[str]  # as written
    ftd: list[str]
    asa_expanded: list[str]
    ftd_expanded: list[str]
    removed: list[str] = field(default_factory=list)  # in ASA, not in FTD
    added: list[str] = field(default_factory=list)  # in FTD, not in ASA
    changed: bool = False
    ignored: bool = False  # changed, but excluded by an option (e.g. comments)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _yn(b: bool) -> str:
    return "Yes" if b else "No"


def rule_fields(r: Rule) -> dict[str, tuple[list[str], list[str]]]:
    """(as written, expanded) display values per field for one rule."""
    action = r.action_text if r.side == "FTD" and r.action_text else r.action
    return {
        "action": ([action], [r.action]),
        "enabled": ([_yn(r.enabled)], [_yn(r.enabled)]),
        "src": (r.src_refs, r.src.labels()),
        "dst": (r.dst_refs, r.dst.labels()),
        "services": (r.svc_refs, r.services.labels()),
        "log": ([_yn(r.log)], [_yn(r.log)]),
        "comment": ([r.comment] if r.comment else [], [r.comment] if r.comment else []),
    }


def diff_pair(asa: Rule, ftd: Rule, ignore_comments: bool = True) -> dict[str, FieldDiff]:
    fa, ff = rule_fields(asa), rule_fields(ftd)
    out: dict[str, FieldDiff] = {}
    for name in FIELDS:
        (aw, ae), (fw, fe) = fa[name], ff[name]
        d = FieldDiff(name, aw, fw, ae, fe)
        if name == "action":
            d.changed = asa.action != ftd.action
        elif name == "enabled":
            d.changed = asa.enabled != ftd.enabled
        elif name == "log":
            d.changed = asa.log != ftd.log
        elif name == "comment":
            d.changed = asa.comment != ftd.comment
            d.ignored = d.changed and ignore_comments
        elif name == "src":
            d.removed, d.added = asa.src.minus(ftd.src), ftd.src.minus(asa.src)
            d.changed = asa.src != ftd.src
        elif name == "dst":
            d.removed, d.added = asa.dst.minus(ftd.dst), ftd.dst.minus(asa.dst)
            d.changed = asa.dst != ftd.dst
        elif name == "services":
            d.removed, d.added = asa.services.minus(ftd.services), ftd.services.minus(asa.services)
            d.changed = asa.services != ftd.services
        if d.changed and name in ("action", "enabled", "log", "comment"):
            d.removed, d.added = list(ae), list(fe)
        out[name] = d
    return out


def merge_notes(asa: Rule, ftd: Rule, asa_object_names: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Why an otherwise identical pair is MATCH_MERGED (empty = plain MATCH).

    Merged: the leaf entries differ although the expanded sets are equal
    (e.g. 'SIEM-SRV' and 'host 192.0.2.20' became one entry).
    Renamed: FTD references a name that exists nowhere in the ASA config and
    is not one of the migration tool's literal-derived names. Reusing an
    existing ASA object for a literal is neither.
    """
    notes: list[str] = []
    for label, a, f, ar, fr in (("Source", asa.src_leaves, ftd.src_leaves, asa.src_refs, ftd.src_refs),
                                ("Destination", asa.dst_leaves, ftd.dst_leaves, asa.dst_refs, ftd.dst_refs),
                                ("Services", asa.svc_leaves, ftd.svc_leaves, asa.svc_refs, ftd.svc_refs)):
        # Same object kept on both sides: duplicates *inside* that object are the
        # ASA's own redundancy (e.g. 'tcp-udp eq 389' + 'tcp eq ldap'), not a migration merge.
        if _same_refs(ar, fr):
            continue
        if a != f:
            dup = [x for x in dict.fromkeys(a) if a.count(x) > 1]
            if dup and len(f) < len(a):
                notes.append(f"{label}: duplicate entries merged ({', '.join(dup[:5])}); {len(a)} → {len(f)} entries")
            else:
                notes.append(f"{label}: entries regrouped; {len(a)} → {len(f)} entries")
    renamed = sorted(
        n for n in ftd.ref_names - asa.ref_names
        if n not in asa_object_names and name_convention_network(n) is None and name_convention_port(n) is None
    )
    if renamed:
        notes.append(f"Objects renamed or new object names: {', '.join(renamed[:6])}")
    return notes


_PROTO_PREFIX = ("tcp ", "udp ", "tcp-udp ", "sctp ", "icmp ", "icmp6 ", "ip ")


def _same_refs(asa_refs: list[str], ftd_refs: list[str]) -> bool:
    def norm(r: str) -> str:
        for p in _PROTO_PREFIX:
            if r.startswith(p):
                return r[len(p):]
        return r

    return bool(asa_refs) and {norm(r) for r in asa_refs} == set(ftd_refs)
