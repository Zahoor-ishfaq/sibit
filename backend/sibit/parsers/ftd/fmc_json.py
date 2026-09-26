"""FMC REST API source (spec 3.3): reads a JSON export instead of the PDF report.

Accepted inputs (UTF-8 JSON):
  * a Sibit bundle written by ``python -m sibit.parsers.ftd.fmc_api`` —
      {"format": "sibit-fmc-bundle", "policy": {...}, "accessrules": [...], "objects": {type: [...]}}
  * a raw ``GET .../accesspolicies/{id}/accessrules?expanded=true`` response ({"items": [...]}),
    optionally with an "objects" key added by hand.

Rules are converted into the same RawFtdRule/FtdObject structures the PDF parser
produces (values in the report's text format, e.g. 'TCP (6):22'), so the
resolver and comparison engine are shared unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ...ports import PROTOCOLS
from ..common import Cancelled, ParseWarning, ProgressFn
from .referenced_objects import FtdObject
from .rule_block import RawFtdRule
from .source import FtdPolicy, FtdSource, NotAnFmcReport

ACTIONS = {
    "ALLOW": "Allow",
    "TRUST": "Trust",
    "BLOCK": "Block",
    "BLOCK_RESET": "Block with reset",
    "MONITOR": "Monitor",
    "BLOCK_INTERACTIVE": "Interactive Block",
    "BLOCK_RESET_INTERACTIVE": "Interactive Block with reset",
}
_PROTO_NUM = {k.upper(): v for k, v in PROTOCOLS.items()}
_PROTO_LABEL = {6: "TCP", 17: "UDP", 1: "ICMP", 58: "IPV6-ICMP", 47: "GRE", 132: "SCTP"}


def _port_text(proto: str | int | None, port: str | None = None, icmp_type: str | None = None,
               code: str | None = None) -> str:
    """FMC protocol/port -> report text ('TCP (6):22', 'ICMP (1):8:0', 'GRE (47)')."""
    if proto is None or str(proto) == "":
        return "any"
    p = str(proto).strip()
    num = int(p) if p.isdigit() else _PROTO_NUM.get(p.upper().replace("IPV6-ICMP", "ICMP6"), 0)
    label = _PROTO_LABEL.get(num, p.upper() if not p.isdigit() else f"PROTO{num}")
    base = f"{label} ({num})"
    if num in (1, 58):
        if icmp_type not in (None, ""):
            return f"{base}:{icmp_type}" + (f":{code}" if code not in (None, "") else "")
        return base
    if port not in (None, ""):
        return f"{base}:{port}"
    return base


def _names_and_literals(block: dict | None, kind: str) -> list[str]:
    """Rule field ({'objects': [...], 'literals': [...]}) -> report-style values."""
    if not block:
        return []
    out = [o.get("name", "") for o in block.get("objects", []) if o.get("name")]
    for lit in block.get("literals", []):
        if kind == "network":
            v = lit.get("value")
            if v:
                out.append(v)
        else:
            out.append(_port_text(lit.get("protocol"), lit.get("port"), lit.get("icmpType"), lit.get("code")))
    return out


def _object(o: dict, otype: str) -> FtdObject | None:
    name = o.get("name")
    if not name:
        return None
    t = otype.lower()
    if t in ("networks", "hosts", "ranges", "fqdns", "networkaddresses"):
        return FtdObject(name, "network", [o["value"]] if o.get("value") else [], o.get("type"))
    if t == "networkgroups":
        vals = [x["name"] for x in o.get("objects", []) if x.get("name")] + \
               [x["value"] for x in o.get("literals", []) if x.get("value")]
        return FtdObject(name, "network", vals, "NetworkGroup")
    if t == "protocolportobjects":
        return FtdObject(name, "port", [_port_text(o.get("protocol"), o.get("port"))], "ProtocolPortObject")
    if t in ("icmpv4objects", "icmpv6objects"):
        proto = 1 if t == "icmpv4objects" else 58
        return FtdObject(name, "port", [_port_text(proto, None, o.get("icmpType"), o.get("code"))], o.get("type"))
    if t == "portobjectgroups":
        vals = [x["name"] for x in o.get("objects", []) if x.get("name")]
        return FtdObject(name, "port", vals, "PortObjectGroup")
    return None


def rule_from_json(item: dict, position: int) -> RawFtdRule:
    meta = item.get("metadata") or {}
    pos = int(meta.get("ruleIndex") or position)
    r = RawFtdRule(pos, item.get("name", f"rule-{pos}"), not item.get("enabled", True), page=0)
    f = r.fields
    f["Action"] = [ACTIONS.get(str(item.get("action", "")).upper(), str(item.get("action", "")).title())]
    zones = [z.get("name", "") for z in (item.get("sourceZones") or {}).get("objects", [])]
    f["Source Zones"] = [", ".join(zones) or "any"]
    dzones = [z.get("name", "") for z in (item.get("destinationZones") or {}).get("objects", [])]
    f["Destination Zones"] = [", ".join(dzones) or "any"]
    f["Source Networks"] = _names_and_literals(item.get("sourceNetworks"), "network") or ["any"]
    f["Destination Networks"] = _names_and_literals(item.get("destinationNetworks"), "network") or ["any"]
    f["Source Ports"] = _names_and_literals(item.get("sourcePorts"), "port") or ["any"]
    f["Destination Ports"] = _names_and_literals(item.get("destinationPorts"), "port") or ["any"]
    f["Log at Beginning of Connection"] = ["Yes" if item.get("logBegin") else "No"]
    f["Log at End of Connection"] = ["Yes" if item.get("logEnd") else "No"]
    comments = [c.get("comment", "") for c in item.get("commentHistoryList", []) if c.get("comment")]
    if comments:
        f["Comments"] = comments
    r.lines = [f"{pos}:{r.name}" + ("(disable)" if r.disabled else "")] + [
        f"{k} {', '.join(v)}" for k, v in f.items()
    ]
    return r


def looks_like_fmc_json(head: bytes) -> bool:
    h = head[:4096].decode("utf-8", errors="ignore")
    return h.lstrip().startswith("{") and ('"accessrules"' in h or ('"items"' in h and '"action"' in h)
                                           or '"sibit-fmc-bundle"' in h)


class FmcJsonSource(FtdSource):
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self, progress: ProgressFn | None = None, is_cancelled: Callable[[], bool] | None = None) -> FtdPolicy:
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise NotAnFmcReport(f"This JSON file could not be read as an FMC export: {e}") from e
        if isinstance(data, list):
            items = data
            data = {}
        else:
            items = data.get("accessrules") or data.get("items") or []
        if not items or not isinstance(items, list) or not isinstance(items[0], dict) or "action" not in items[0]:
            raise NotAnFmcReport("This JSON doesn't look like an FMC access rules export. Expected 'accessrules' or 'items'.")
        rules: list[RawFtdRule] = []
        for i, item in enumerate(items, 1):
            if i % 500 == 0:
                if is_cancelled and is_cancelled():
                    raise Cancelled()
                if progress:
                    progress("ftd_pages", {"page": i, "pages": len(items), "rules": len(rules)})
            rules.append(rule_from_json(item, i))
        rules.sort(key=lambda r: r.position)
        objects: dict[str, FtdObject] = {}
        warnings: list[ParseWarning] = []
        for otype, objs in (data.get("objects") or {}).items():
            for o in objs:
                fo = _object(o, otype)
                if fo is not None:
                    objects[fo.name] = fo
        if not objects:
            warnings.append(ParseWarning("FTD", None, Path(self.path).name,
                                         "No object definitions in the JSON export; named objects cannot be expanded"))
        policy = data.get("policy") or {}
        return FtdPolicy(policy.get("name"), policy.get("hostname"), len(items), rules, objects, warnings,
                         has_rules_section=True, has_referenced_objects=bool(objects))
