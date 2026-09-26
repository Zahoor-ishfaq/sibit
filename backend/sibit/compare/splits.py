"""Merge FTD rules that the migration tool split from one ASA line.

Observed in real FMC migrations:
  INSIDE-IN_#1-1, INSIDE-IN_#1_2       one ASA ACE split by service type
  PARTNER-IN_#2-Copy-1640 (+ PARTNER-IN_#2)      an extra copy of the same ACE
  DMZ-IN_#5-1, DMZ-IN_2_UNSUPPORTED_2
                                             the unsupported part loses the line number and
                                             directly follows its '-1' sibling (disabled)

The parts are merged into one virtual FTD rule whose sets are the union of the
ENABLED parts (the traffic FTD actually allows). Disabled parts are listed so
the loss of access is explained, not hidden.
"""
from __future__ import annotations

import re

from ..model import AddressBuilder, Rule, ServiceSet

_BASE = re.compile(r"^(?P<acl>.+)_#(?P<n>\d+)$")
_PART = re.compile(r"^(?P<acl>.+)_#(?P<n>\d+)(?:[-_](?P<part>\d+)|-Copy-\d+)$")
_UNSUPPORTED = re.compile(r"^(?P<acl>.+)_\d+_UNSUPPORTED_\d+$")


def _key(r: Rule) -> tuple[str, int] | None:
    m = _BASE.match(r.key) or _PART.match(r.key)
    return (m.group("acl"), int(m.group("n"))) if m else None


def merge_split_rules(ftd: list[Rule]) -> list[Rule]:
    ordered = sorted(ftd, key=lambda r: r.position or 0)
    groups: dict[tuple[str, int], list[Rule]] = {}
    is_part: set[int] = set()
    prev_part_key: tuple[str, int] | None = None
    for r in ordered:
        if _PART.match(r.key):
            k = _key(r)
            groups.setdefault(k, []).append(r)
            is_part.add(id(r))
            prev_part_key = k
            continue
        m = _UNSUPPORTED.match(r.key)
        if m and prev_part_key and prev_part_key[0] == m.group("acl"):
            groups[prev_part_key].append(r)
            is_part.add(id(r))
            continue
        prev_part_key = None
        k = _key(r)
        if k is not None:
            groups.setdefault(k, []).append(r)
    merged_for: dict[int, Rule] = {}
    drop: set[int] = set()
    for (acl, n), rules in groups.items():
        if len(rules) < 2 and not any(id(r) in is_part for r in rules):
            continue
        m = _merge(acl, n, rules)
        merged_for[id(rules[0])] = m
        drop.update(id(r) for r in rules)
    out: list[Rule] = []
    for r in ftd:
        if id(r) in merged_for:
            out.append(merged_for[id(r)])
        elif id(r) not in drop:
            out.append(r)
    return out


def _merge(acl: str, n: int, rules: list[Rule]) -> Rule:
    rules = sorted(rules, key=lambda r: r.position or 0)
    live = [r for r in rules if r.enabled] or rules
    src, dst = AddressBuilder(), AddressBuilder()
    for r in live:
        src.add_set(r.src)
        dst.add_set(r.dst)

    def cat(attr: str) -> list[str]:
        return list(dict.fromkeys(v for r in live for v in getattr(r, attr)))

    first = rules[0]
    return Rule(
        side="FTD",
        key=f"{acl}_#{n}",
        acl=acl,
        line_no=n,
        position=first.position,
        source_zone=first.source_zone,
        action=live[0].action,
        enabled=any(r.enabled for r in rules),
        log=any(r.log for r in live),
        comment=next((r.comment for r in live if r.comment), ""),
        raw_text="\n\n".join(r.raw_text for r in rules),
        src_refs=cat("src_refs"),
        dst_refs=cat("dst_refs"),
        svc_refs=cat("svc_refs"),
        src=src.build(),
        dst=dst.build(),
        services=ServiceSet.union(r.services for r in live),
        unresolved=cat("unresolved"),
        src_leaves=_leaves(live, "src_leaves"),
        dst_leaves=_leaves(live, "dst_leaves"),
        svc_leaves=_leaves(live, "svc_leaves"),
        ref_names=frozenset().union(*(r.ref_names for r in live)),
        action_text=live[0].action_text,
        dest_zone=first.dest_zone,
        uid="FTD:" + "+".join(str(r.position) for r in rules),
        parts=tuple(r.key for r in rules),
        disabled_parts=tuple(r.key for r in rules if not r.enabled),
    )


def _leaves(rules: list[Rule], attr: str) -> tuple[str, ...]:
    """Concatenate the parts' leaves, counting a leaf list repeated verbatim in every part once."""
    distinct = list(dict.fromkeys(getattr(r, attr) for r in rules))
    return tuple(sorted(v for leaves in distinct for v in leaves))
