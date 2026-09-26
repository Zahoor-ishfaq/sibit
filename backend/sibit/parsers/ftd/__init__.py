"""FTD Access Control Policy parser (spec section 3).

    result = parse_ftd(PdfFtdSource("after.pdf"))
    result.rules -> list[Rule] (side="FTD"), in policy order
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ...model import Rule
from ..common import ParseWarning, ProgressFn, UnresolvedRef
from .pdf_reader import pdf_info
from .referenced_objects import FtdObject
from .resolver import FtdResolver
from .fmc_json import FmcJsonSource, looks_like_fmc_json
from .source import FtdPolicy, FtdSource, NotAnFmcReport, PdfFtdSource

__all__ = ["parse_ftd", "FtdResult", "FtdSource", "PdfFtdSource", "FmcJsonSource", "NotAnFmcReport", "pdf_info",
           "open_source", "looks_like_fmc_json"]


def open_source(path: str) -> FtdSource:
    """PDF report or FMC REST API JSON export, chosen by content."""
    with open(path, "rb") as f:
        head = f.read(4096)
    if not head.startswith(b"%PDF") and looks_like_fmc_json(head):
        return FmcJsonSource(path)
    return PdfFtdSource(path)


@dataclass
class FtdResult:
    rules: list[Rule]
    policy: FtdPolicy
    resolver: FtdResolver
    warnings: list[ParseWarning]
    unresolved: list[UnresolvedRef]

    @property
    def objects(self) -> dict[str, FtdObject]:
        return self.policy.objects

    def summary(self) -> dict:
        acls: dict[str, int] = {}
        for r in self.rules:
            acls[r.acl or "(unnamed)"] = acls.get(r.acl or "(unnamed)", 0) + 1
        sections: dict[str, int] = {}
        for o in self.policy.objects.values():
            sections[o.section] = sections.get(o.section, 0) + 1
        return {
            "policy": self.policy.policy_name,
            "hostname": self.policy.hostname,
            "pages": self.policy.page_count,
            "rules": len(self.rules),
            "rules_disabled": sum(1 for r in self.rules if not r.enabled),
            "acls": acls,
            "referenced_objects": len(self.policy.objects),
            "objects_by_section": sections,
            "unresolved": len(self.unresolved),
            "resolved_by_name_convention": len(self.resolver.convention_names),
            "warnings": len(self.warnings),
        }


def parse_ftd(
    source: FtdSource,
    *,
    progress: ProgressFn | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> FtdResult:
    policy = source.load(progress, is_cancelled)
    warnings = list(policy.warnings)
    resolver = FtdResolver(policy.objects, warnings)
    rules: list[Rule] = []
    for raw in policy.raw_rules:
        try:
            rules.append(resolver.to_rule(raw))
        except Exception as e:  # noqa: BLE001 - never crash on unknown content
            warnings.append(ParseWarning("FTD", raw.page, f"{raw.position}:{raw.name}", f"Could not build rule: {e}"))
    for name in sorted(resolver.convention_names):
        warnings.append(ParseWarning("FTD", None, name,
                                     "Not in Referenced Objects; value derived from the migration tool's naming convention"))
    used_by: dict[str, list[str]] = {}
    for r in rules:
        for u in r.unresolved:
            used_by.setdefault(u, []).append(r.uid)
    unresolved = [UnresolvedRef("FTD", n, reason, used_by.get(n, []))
                  for n, reason in sorted(resolver.unresolved_names.items())]
    if progress:
        progress("ftd_done", {"rules": len(rules), "objects": len(policy.objects)})
    return FtdResult(rules, policy, resolver, warnings, unresolved)
