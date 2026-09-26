"""Comparison engine: match → diff → status → risk → order check."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..model import Rule
from ..parsers.common import ParseWarning, ProgressFn, UnresolvedRef
from .differ import FieldDiff, diff_pair, merge_notes, rule_fields
from .matcher import AclCalibration, MatchResult, match_rules
from .order_check import OrderChange, check_order
from .splits import merge_split_rules
from .risk import SEVERITY_RANK, Flag, explain, flags_for_pair, max_severity

STATUSES = ("MATCH", "MATCH_MERGED", "CHANGED", "MISSING_IN_FTD", "EXTRA_IN_FTD", "UNRESOLVED")
SEVERITIES = ("critical", "high", "medium", "low", "none")


@dataclass
class CompareOptions:
    numbering: str = "auto"  # auto | ace_only | all_lines
    include_disabled: bool = True
    ignore_comments: bool = True

    def to_dict(self) -> dict:
        return {"numbering": self.numbering, "include_disabled": self.include_disabled,
                "ignore_comments": self.ignore_comments}


@dataclass
class RulePair:
    id: int
    asa: Rule | None
    ftd: Rule | None
    matched_by: str | None  # 'name' | 'content' | None
    status: str = "MATCH"
    severity: str = "none"
    flags: list[Flag] = field(default_factory=list)
    diffs: dict[str, FieldDiff] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def key(self) -> str:
        if self.ftd is not None and self.asa is not None and self.matched_by == "content":
            return self.ftd.key
        return (self.ftd or self.asa).key  # type: ignore[union-attr]

    @property
    def acl(self) -> str:
        r = self.asa or self.ftd
        return (r.acl if r else "") or "(unnamed)"

    @property
    def enabled(self) -> bool:
        if self.ftd is not None:
            return self.ftd.enabled
        return bool(self.asa and self.asa.enabled)

    @property
    def action(self) -> str:
        r = self.ftd or self.asa
        return r.action if r else ""

    @property
    def disabled_badge(self) -> bool:
        return self.ftd is not None and not self.ftd.enabled


@dataclass
class Comparison:
    pairs: list[RulePair]
    match: MatchResult
    order_changes: list[OrderChange]
    options: CompareOptions
    warnings: list[ParseWarning]
    unresolved: list[UnresolvedRef]
    excluded_disabled: int = 0

    def counts(self) -> dict:
        by_status = {s: 0 for s in STATUSES}
        by_sev = {s: 0 for s in SEVERITIES}
        for p in self.pairs:
            by_status[p.status] += 1
            by_sev[p.severity if p.severity in by_sev else "none"] += 1
        return {"total": len(self.pairs), "status": by_status, "severity": by_sev}

    def per_acl(self) -> list[dict]:
        acc: dict[str, dict] = {}
        for p in self.pairs:
            d = acc.setdefault(p.acl, {"acl": p.acl, **{s: 0 for s in STATUSES}, "critical": 0, "total": 0})
            d[p.status] += 1
            d["total"] += 1
            if p.severity == "critical":
                d["critical"] += 1
        return sorted(acc.values(), key=lambda d: -d["total"])

    def calibration(self) -> dict:
        asa_total = sum(1 for p in self.pairs if p.asa is not None)
        by_name = sum(1 for p in self.pairs if p.matched_by == "name")
        by_content = sum(1 for p in self.pairs if p.matched_by == "content")
        return {
            "requested": self.match.requested,
            "strategy": self.match.strategy_label(),
            "match_rate": round(100.0 * by_name / asa_total, 1) if asa_total else 0.0,
            "matched_by_name": by_name,
            "matched_by_content": by_content,
            "asa_rules": asa_total,
            "acls": [
                {"acl": c.acl, "strategy": c.strategy, "scores": c.scores, "sample": c.sample,
                 "matched_by_name": c.matched_by_name, "matched_by_content": c.matched_by_content,
                 "asa_rules": c.asa_rules, "ftd_rules": c.ftd_rules}
                for c in self.match.calibration.values()
            ],
        }


_UNRELIABLE_WHEN_UNRESOLVED = {"SCOPE_WIDENED", "SCOPE_NARROWED", "DENY_SCOPE_WIDENED", "DENY_SCOPE_NARROWED"}


def _evaluate(p: RulePair, opts: CompareOptions, asa_names: frozenset[str]) -> None:
    a, f = p.asa, p.ftd
    if a is not None and f is not None:
        p.diffs = diff_pair(a, f, opts.ignore_comments)
        p.flags = flags_for_pair(a, f, p.diffs, opts.ignore_comments)
        changed = any(d.changed and not d.ignored for d in p.diffs.values())
        if a.unresolved or f.unresolved:
            p.status = "UNRESOLVED"
            # Set differences are meaningless when one side could not be expanded.
            p.flags = [fl for fl in p.flags if fl.code not in _UNRELIABLE_WHEN_UNRESOLVED]
            un = list(dict.fromkeys(a.unresolved + f.unresolved))
            p.flags.append(Flag("UNRESOLVED_OBJECTS", "medium", f"Unresolved: {', '.join(un[:6])}"))
        elif changed:
            p.status = "CHANGED"
        else:
            p.notes = merge_notes(a, f, asa_names)
            p.status = "MATCH_MERGED" if p.notes else "MATCH"
    elif a is not None:
        p.status = "MISSING_IN_FTD"
        p.flags = flags_for_pair(a, None, None)
        p.diffs = _one_sided(a, None)
    else:
        assert f is not None
        p.status = "EXTRA_IN_FTD"
        p.flags = flags_for_pair(None, f, None)
        p.diffs = _one_sided(None, f)
    p.flags.sort(key=lambda fl: -SEVERITY_RANK[fl.severity])
    p.severity = max_severity(p.flags)
    p.explanation = explain(a, f, p.flags, p.status, p.notes)


def _one_sided(a: Rule | None, f: Rule | None) -> dict[str, FieldDiff]:
    r = a or f
    assert r is not None
    vals = rule_fields(r)
    out = {}
    for name, (w, e) in vals.items():
        if a is not None:
            out[name] = FieldDiff(name, w, [], e, [], removed=list(e), changed=True)
        else:
            out[name] = FieldDiff(name, [], w, [], e, added=list(e), changed=True)
    return out


def compare(
    asa_rules: list[Rule],
    ftd_rules: list[Rule],
    options: CompareOptions | None = None,
    *,
    warnings: list[ParseWarning] | None = None,
    asa_object_names: frozenset[str] | set[str] = frozenset(),
    unresolved: list[UnresolvedRef] | None = None,
    progress: ProgressFn | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> Comparison:
    opts = options or CompareOptions()
    if progress:
        progress("matching", {"asa": len(asa_rules), "ftd": len(ftd_rules)})
    ftd_rules = merge_split_rules(ftd_rules)
    m = match_rules(asa_rules, ftd_rules, opts.numbering)
    pairs: list[RulePair] = []
    excluded = 0
    for a, f, how in m.pairs:
        if not opts.include_disabled:
            a_off = a is None or not a.enabled
            f_off = f is None or not f.enabled
            if a_off and f_off:
                excluded += 1
                continue
        pairs.append(RulePair(len(pairs), a, f, how))
    if progress:
        progress("comparing", {"pairs": len(pairs)})
    for i, p in enumerate(pairs):
        if i % 2000 == 0:
            if is_cancelled and is_cancelled():
                from ..parsers.common import Cancelled
                raise Cancelled()
            if progress and i:
                progress("comparing", {"done": i, "pairs": len(pairs)})
        _evaluate(p, opts, frozenset(asa_object_names))
    order = check_order(pairs)
    return Comparison(pairs, m, order, opts, list(warnings or []), list(unresolved or []), excluded)
