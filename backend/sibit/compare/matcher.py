"""Match FTD rules to their ASA origin (spec section 4).

Primary key: FTD rule name '<ACL>_#<N>' = ACL name + ASA line number, where
the line numbering strategy is verified per ACL, not assumed:
  ace_only  — count ACE lines only, skip remarks (1-based)  [default]
  all_lines — count remarks too
Auto-calibration tries both on the first 50 FTD rules of each ACL and keeps the
one with the higher content-match rate. Rules still unmatched are paired by a
content fingerprint (ACL + action + expanded source + services).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Rule

STRATEGIES = ("ace_only", "all_lines")
CALIBRATION_SAMPLE = 50


@dataclass
class AclCalibration:
    acl: str
    strategy: str
    scores: dict[str, int]
    sample: int
    matched_by_name: int = 0
    matched_by_content: int = 0
    asa_rules: int = 0
    ftd_rules: int = 0


@dataclass
class MatchResult:
    pairs: list[tuple[Rule | None, Rule | None, str | None]]  # (asa, ftd, matched_by)
    calibration: dict[str, AclCalibration] = field(default_factory=dict)
    requested: str = "auto"

    @property
    def matched_by_name(self) -> int:
        return sum(1 for _, _, m in self.pairs if m == "name")

    @property
    def matched_by_content(self) -> int:
        return sum(1 for _, _, m in self.pairs if m == "content")

    def strategy_label(self) -> str:
        used = {c.strategy for c in self.calibration.values() if c.ftd_rules}
        if not used:
            return "ACE-only" if self.requested != "all_lines" else "All lines"
        if used == {"ace_only"}:
            return "ACE-only"
        if used == {"all_lines"}:
            return "All lines"
        return "Mixed (per ACL)"


def _line_no(rule: Rule, strategy: str) -> int | None:
    return rule.line_no_ace if strategy == "ace_only" else rule.line_no_all


def _index(asa: list[Rule], strategy: str) -> dict[int, Rule]:
    out: dict[int, Rule] = {}
    for r in asa:
        n = _line_no(r, strategy)
        if n is not None:
            out[n] = r
    return out


def calibrate(acl: str, asa: list[Rule], ftd: list[Rule], requested: str) -> AclCalibration:
    sample = sorted((r for r in ftd if r.line_no), key=lambda r: r.line_no)[:CALIBRATION_SAMPLE]
    scores: dict[str, int] = {}
    for strat in STRATEGIES:
        idx = _index(asa, strat)
        score = 0
        for f in sample:
            a = idx.get(f.line_no)
            if a is not None and a.content_fingerprint() == f.content_fingerprint():
                score += 1
        scores[strat] = score
    if requested in STRATEGIES:
        chosen = requested
    else:
        chosen = "all_lines" if scores["all_lines"] > scores["ace_only"] else "ace_only"
    return AclCalibration(acl, chosen, scores, len(sample), asa_rules=len(asa), ftd_rules=len(ftd))


def match_rules(asa_rules: list[Rule], ftd_rules: list[Rule], strategy: str = "auto") -> MatchResult:
    asa_by_acl: dict[str, list[Rule]] = {}
    for r in asa_rules:
        asa_by_acl.setdefault(r.acl, []).append(r)
    ftd_by_acl: dict[str, list[Rule]] = {}
    for r in ftd_rules:
        ftd_by_acl.setdefault(r.acl, []).append(r)

    result = MatchResult([], requested=strategy)
    matched_asa: set[int] = set()
    matched_ftd: set[int] = set()
    pair_of_ftd: dict[int, tuple[Rule, str]] = {}

    for acl, asa in asa_by_acl.items():
        ftd = ftd_by_acl.get(acl, [])
        cal = calibrate(acl, asa, ftd, strategy)
        result.calibration[acl] = cal
        # Re-key ASA rules under the chosen strategy (display + key matching).
        for r in asa:
            n = _line_no(r, cal.strategy)
            if n is not None:
                r.line_no = n
                r.key = f"{acl}_#{n}"
        idx = _index(asa, cal.strategy)
        for f in ftd:
            if not f.line_no:
                continue
            a = idx.get(f.line_no)
            if a is None or id(a) in matched_asa:
                continue
            matched_asa.add(id(a))
            matched_ftd.add(id(f))
            pair_of_ftd[id(f)] = (a, "name")
            cal.matched_by_name += 1

    # Content fallback, in policy order, first-come first-served.
    pool: dict[tuple, list[Rule]] = {}
    for a in asa_rules:
        if id(a) not in matched_asa:
            pool.setdefault(a.content_fingerprint(), []).append(a)
    for f in ftd_rules:
        if id(f) in matched_ftd or not f.acl:
            continue
        cands = pool.get(f.content_fingerprint())
        if cands:
            a = cands.pop(0)
            matched_asa.add(id(a))
            matched_ftd.add(id(f))
            pair_of_ftd[id(f)] = (a, "content")
            if a.acl in result.calibration:
                result.calibration[a.acl].matched_by_content += 1

    # Assemble pairs: ASA order first (matched + missing), then extra FTD rules.
    ftd_for_asa: dict[int, tuple[Rule, str]] = {}
    for f in ftd_rules:
        if id(f) in pair_of_ftd:
            a, how = pair_of_ftd[id(f)]
            ftd_for_asa[id(a)] = (f, how)
    for a in asa_rules:
        if id(a) in ftd_for_asa:
            f, how = ftd_for_asa[id(a)]
            result.pairs.append((a, f, how))
        else:
            result.pairs.append((a, None, None))
    for f in ftd_rules:
        if id(f) not in matched_ftd:
            result.pairs.append((None, f, None))
    return result
