"""Risk flags, severities and plain-English explanations (spec 6.1 / 6.2)."""
from __future__ import annotations

from dataclasses import dataclass

from ..model import AddressSet, Rule
from .differ import FieldDiff

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0, "none": -1}
# 'info' flags explain a rule (e.g. SPLIT_IN_FTD) but never raise its severity.


@dataclass
class Flag:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


FLAG_SEVERITY = {
    "DST_WIDENED_TO_ANY": "critical",
    "SRC_WIDENED_TO_ANY": "critical",
    "DENY_BECAME_PERMIT": "critical",
    "SCOPE_WIDENED": "high",
    "DISABLED_BECAME_ENABLED": "high",
    "ANY_ANY_PERMIT": "high",
    "SCOPE_NARROWED": "medium",
    "MISSING_IN_FTD": "medium",  # 'high' for deny rules (set per rule)
    "ENABLED_BECAME_DISABLED": "medium",
    "LOGGING_CHANGED": "low",
    "COMMENT_CHANGED": "low",
    # Extensions (docs/DECISIONS.md)
    "PERMIT_BECAME_DENY": "medium",
    "ACTION_CHANGED": "medium",
    "DENY_SCOPE_NARROWED": "high",
    "DENY_SCOPE_WIDENED": "medium",
    "EXTRA_IN_FTD": "medium",  # 'low' for deny rules
    "UNRESOLVED_OBJECTS": "medium",
    "SPLIT_IN_FTD": "info",
}


def _is_any_any(r: Rule) -> bool:
    return r.src.is_any and r.dst.is_any


def describe_addrs(s: AddressSet, limit: int = 4) -> str:
    if s.is_any:
        return "ANY"
    labels = s.labels()
    hosts = all("/" not in x and "-" not in x and not x.startswith("fqdn:") for x in labels)
    noun = "host" if hosts else "item"
    head = ", ".join(labels[:limit]) + (f", +{len(labels) - limit} more" if len(labels) > limit else "")
    return f"{len(labels)} {noun}{'s' if len(labels) != 1 else ''} ({head})"


def _svc_text(r: Rule, limit: int = 6) -> str:
    labels = r.services.labels()
    if r.services.is_any:
        return "any protocol/port"
    head = ", ".join(labels[:limit]) + (f", +{len(labels) - limit} more" if len(labels) > limit else "")
    return head


def flags_for_pair(asa: Rule | None, ftd: Rule | None, diffs: dict[str, FieldDiff] | None,
                   ignore_comments: bool = True) -> list[Flag]:
    flags: list[Flag] = []

    def add(code: str, msg: str, severity: str | None = None) -> None:
        flags.append(Flag(code, severity or FLAG_SEVERITY[code], msg))

    if asa is not None and ftd is None:
        if asa.action == "deny":
            add("MISSING_IN_FTD", "Deny rule has no FTD counterpart; traffic it blocked may now be allowed.", "high")
        else:
            add("MISSING_IN_FTD", "Permit rule has no FTD counterpart; traffic it allowed may now be blocked.")
        return flags
    if ftd is not None and asa is None:
        if ftd.action == "permit":
            add("EXTRA_IN_FTD", "FTD rule has no ASA origin and permits traffic.")
        else:
            add("EXTRA_IN_FTD", "FTD rule has no ASA origin.", "low")
        if ftd.action == "permit" and _is_any_any(ftd):
            add("ANY_ANY_PERMIT", "FTD rule permits any source to any destination.")
        return flags
    assert asa is not None and ftd is not None and diffs is not None

    # Action
    if asa.action == "deny" and ftd.action == "permit":
        add("DENY_BECAME_PERMIT", f"ASA denied this traffic; FTD action is '{ftd.action_text or 'Allow'}'.")
    elif asa.action == "permit" and ftd.action == "deny":
        add("PERMIT_BECAME_DENY", f"ASA permitted this traffic; FTD action is '{ftd.action_text or 'Block'}'.")
    elif asa.action != ftd.action:
        sev = "high" if asa.action == "deny" else "medium"
        add("ACTION_CHANGED", f"Action changed from {asa.action} to '{ftd.action_text}'.", sev)

    permit_rule = ftd.action == "permit"
    if permit_rule:
        to_any: set[str] = set()
        if ftd.dst.is_any and not asa.dst.is_any and not asa.dst.is_empty:
            to_any.add("dst")
            add("DST_WIDENED_TO_ANY", f"Destination widened from {describe_addrs(asa.dst)} to ANY.")
        if ftd.src.is_any and not asa.src.is_any and not asa.src.is_empty:
            to_any.add("src")
            add("SRC_WIDENED_TO_ANY", f"Source widened from {describe_addrs(asa.src)} to ANY.")
        wider = [f for f in ("src", "dst", "services") if diffs[f].added and f not in to_any]
        if wider:
            parts = [f"{_label(f)} +{', +'.join(diffs[f].added[:5])}" for f in wider]
            add("SCOPE_WIDENED", "FTD allows more: " + "; ".join(parts) + ".")
        narrower = [f for f in ("src", "dst", "services") if diffs[f].removed]
        if narrower:
            parts = [f"{_label(f)} −{', −'.join(diffs[f].removed[:5])}" for f in narrower]
            add("SCOPE_NARROWED", "FTD allows less (may break services): " + "; ".join(parts) + ".")
        if _is_any_any(ftd) and not _is_any_any(asa):
            add("ANY_ANY_PERMIT", "FTD rule permits any source to any destination.")
    else:
        # For a deny rule, matching less traffic opens access.
        narrower = [f for f in ("src", "dst", "services") if diffs[f].removed]
        if narrower:
            parts = [f"{_label(f)} −{', −'.join(diffs[f].removed[:5])}" for f in narrower]
            add("DENY_SCOPE_NARROWED", "Deny rule matches less traffic; previously blocked traffic may be allowed: "
                + "; ".join(parts) + ".")
        wider = [f for f in ("src", "dst", "services") if diffs[f].added]
        if wider:
            parts = [f"{_label(f)} +{', +'.join(diffs[f].added[:5])}" for f in wider]
            add("DENY_SCOPE_WIDENED", "Deny rule matches more traffic (may block legitimate traffic): "
                + "; ".join(parts) + ".")

    if not asa.enabled and ftd.enabled:
        add("DISABLED_BECAME_ENABLED", "Rule was inactive on the ASA but is enabled on FTD.")
    elif asa.enabled and not ftd.enabled:
        add("ENABLED_BECAME_DISABLED", "Rule was active on the ASA but is disabled on FTD.")
    if ftd.parts:
        msg = f"The ASA rule was split into {len(ftd.parts)} FTD rules ({', '.join(ftd.parts)}); compared as their union."
        if ftd.disabled_parts:
            msg += f" Disabled on FTD: {', '.join(ftd.disabled_parts)} — its traffic is not allowed."
        add("SPLIT_IN_FTD", msg, "info")
    if asa.log != ftd.log:
        add("LOGGING_CHANGED", f"Logging changed from {'on' if asa.log else 'off'} to {'on' if ftd.log else 'off'}.")
    if diffs["comment"].changed and not ignore_comments:
        add("COMMENT_CHANGED", "Comment text differs.")
    return flags


def _label(f: str) -> str:
    return {"src": "source", "dst": "destination", "services": "services"}[f]


def max_severity(flags: list[Flag]) -> str:
    flags = [f for f in flags if f.severity != "info"]
    if not flags:
        return "none"
    return max(flags, key=lambda f: SEVERITY_RANK[f.severity]).severity


def explain(asa: Rule | None, ftd: Rule | None, flags: list[Flag], status: str, notes: list[str]) -> str:
    """Plain-English summary for the diff drawer and 'Copy finding'."""
    codes = {f.code for f in flags}
    parts: list[str] = []
    if status == "MISSING_IN_FTD" and asa is not None:
        return (f"ASA rule {asa.key} ({asa.action} {describe_addrs(asa.src)} → {describe_addrs(asa.dst)}, "
                f"{_svc_text(asa)}) has no counterpart in the FTD policy. " + flags[0].message)
    if status == "EXTRA_IN_FTD" and ftd is not None:
        return (f"FTD rule {ftd.key} ({ftd.action_text or ftd.action} {describe_addrs(ftd.src)} → "
                f"{describe_addrs(ftd.dst)}, {_svc_text(ftd)}) has no ASA origin. "
                + " ".join(f.message for f in flags[1:]))
    assert asa is not None and ftd is not None
    if "DST_WIDENED_TO_ANY" in codes:
        parts.append(f"Destination widened from {describe_addrs(asa.dst)} to ANY. Traffic on {_svc_text(ftd)} "
                     f"from the source is now allowed to every destination.")
    if "SRC_WIDENED_TO_ANY" in codes:
        parts.append(f"Source widened from {describe_addrs(asa.src)} to ANY. Every source can now reach "
                     f"{describe_addrs(ftd.dst)} on {_svc_text(ftd)}.")
    for f in flags:
        if f.code not in ("DST_WIDENED_TO_ANY", "SRC_WIDENED_TO_ANY", "SPLIT_IN_FTD"):
            parts.append(f.message)
    if not ftd.enabled and any(SEVERITY_RANK[f.severity] >= 3 for f in flags):
        parts.append("The FTD rule is disabled, but enabling it later would open this access.")
    if status == "UNRESOLVED":
        un = list(dict.fromkeys(asa.unresolved + ftd.unresolved))
        parts.insert(0, f"Could not fully compare: unresolved object(s) {', '.join(un[:6])}.")
    if status in ("MATCH", "MATCH_MERGED") and not parts:
        parts.append("Semantically identical after expanding all objects.")
        if notes:
            parts.append("Objects were renamed or merged by the migration (informational).")
    parts += [f.message for f in flags if f.code == "SPLIT_IN_FTD"]
    return " ".join(parts)
