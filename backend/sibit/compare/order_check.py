"""Relative-order check around deny rules (spec 6.3).

Within each ACL, for every matched pair R and every matched deny pair D, the
relation 'R is above D' must be the same on the ASA (line order) and on FTD
(policy position). A flip can change which rule shadows the other.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderChange:
    acl: str
    rule_id: int
    rule_key: str
    deny_id: int
    deny_key: str
    asa_relation: str  # 'above' | 'below' (rule relative to the deny rule)
    ftd_relation: str
    asa_rule_line: int
    asa_deny_line: int
    ftd_rule_position: int
    ftd_deny_position: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def check_order(pairs: list, max_results: int = 20000) -> list[OrderChange]:
    """``pairs``: RulePair objects (see engine). Returns order changes."""
    by_acl: dict[str, list] = {}
    for p in pairs:
        if p.asa is not None and p.ftd is not None:
            by_acl.setdefault(p.asa.acl, []).append(p)
    out: list[OrderChange] = []
    for acl, items in by_acl.items():
        denies = [p for p in items if p.asa.action == "deny" or p.ftd.action == "deny"]
        if not denies:
            continue
        for d in denies:
            da, df = d.asa.line_no_ace or d.asa.line_no, d.ftd.position or 0
            for r in items:
                if r is d:
                    continue
                ra, rf = r.asa.line_no_ace or r.asa.line_no, r.ftd.position or 0
                asa_above = ra < da
                ftd_above = rf < df
                if asa_above != ftd_above:
                    # Report each unordered pair once (from the deny's point of view).
                    if r in denies and r.id < d.id:
                        continue
                    out.append(OrderChange(
                        acl, r.id, r.key, d.id, d.key,
                        "above" if asa_above else "below", "above" if ftd_above else "below",
                        ra, da, rf, df,
                    ))
                    if len(out) >= max_results:
                        return out
    return out
