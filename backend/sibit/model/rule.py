"""The normalized Rule produced by both parsers (spec section 5)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .sets import AddressSet, ServiceSet

Side = Literal["ASA", "FTD"]
Action = Literal["permit", "deny"]


@dataclass
class Rule:
    side: Side
    key: str  # "OUTSIDE-IN_#161" (ASA: key under the chosen numbering strategy)
    acl: str
    line_no: int
    position: int | None
    source_zone: str | None
    action: Action
    enabled: bool
    log: bool
    comment: str
    raw_text: str
    src_refs: list[str]
    dst_refs: list[str]
    svc_refs: list[str]
    src: AddressSet
    dst: AddressSet
    services: ServiceSet
    unresolved: list[str] = field(default_factory=list)

    # Extras beyond the spec model -----------------------------------------
    # Canonical leaf items before merging; equal sets with different leaves
    # means the migration tool renamed/merged objects (MATCH_MERGED).
    src_leaves: tuple[str, ...] = ()
    dst_leaves: tuple[str, ...] = ()
    svc_leaves: tuple[str, ...] = ()
    # Every object/group name the rule references, including nested members
    # (ASA) or the named values it lists (FTD). Used to tell renames apart
    # from the migration tool's flattening.
    ref_names: frozenset[str] = frozenset()
    # ASA only: line number under both numbering strategies (1-based, per ACL).
    line_no_ace: int | None = None
    line_no_all: int | None = None
    # FTD only: raw action text ("Allow", "Block with reset", ...).
    action_text: str = ""
    dest_zone: str | None = None
    uid: str = ""  # stable id: "ASA:<acl>:<ace idx>" / "FTD:<position>"
    # FTD only: when the migration tool split one ASA line into several FTD
    # rules, the merged rule lists the original rule names.
    parts: tuple[str, ...] = ()
    disabled_parts: tuple[str, ...] = ()

    def content_fingerprint(self) -> tuple:
        """Fallback matching fingerprint: ACL + action + expanded source + services."""
        return (self.acl, self.action, self.src.fingerprint(), self.services.fingerprint())

    def semantic_fingerprint(self) -> tuple:
        return (
            self.action,
            self.enabled,
            self.src.fingerprint(),
            self.dst.fingerprint(),
            self.services.fingerprint(),
        )


_BY_SUFFIX = re.compile(r"\s*\(by\s+[^()]*?\s+on\s+[^()]*\)\s*$", re.IGNORECASE)


def normalize_comment(text: str) -> str:
    """Strip FMC's '(by admin on 2026-3-03 07:39:18)' audit suffixes and whitespace.

    FMC may append the suffix to each comment; ASA remarks joined with ' | '
    compare equal to FTD comments joined the same way.
    """
    parts = []
    for part in re.split(r"\s*\|\s*|\n", text or ""):
        p = part.strip()
        while True:
            q = _BY_SUFFIX.sub("", p)
            if q == p:
                break
            p = q.strip()
        if p:
            parts.append(" ".join(p.split()))
    return " | ".join(parts)
