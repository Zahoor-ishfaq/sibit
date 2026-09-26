"""Excel report (spec section 10), built from a session so saved projects export too.

Uses openpyxl write-only mode so 10k+ rule reports stay fast and small in memory.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BRAND = "1E3A8A"
FILL = {
    "critical": PatternFill("solid", fgColor="FDE2E7"),
    "high": PatternFill("solid", fgColor="FFEDD5"),
    "medium": PatternFill("solid", fgColor="FEF3C7"),
    "low": PatternFill("solid", fgColor="E0F2FE"),
    "none": None,
    "removed": PatternFill("solid", fgColor="FCD5DC"),
    "added": PatternFill("solid", fgColor="D1FAE5"),
    "both": PatternFill("solid", fgColor="FDE68A"),
    "header": PatternFill("solid", fgColor=BRAND),
    "match": PatternFill("solid", fgColor="D1FAE5"),
}
SEV_FONT = {
    "critical": Font(bold=True, color="BE123C"),
    "high": Font(bold=True, color="C2410C"),
    "medium": Font(bold=True, color="A16207"),
    "low": Font(color="0369A1"),
}
STATUS_LABEL = {
    "MATCH": "Match",
    "MATCH_MERGED": "Match (merged)",
    "CHANGED": "Changed",
    "MISSING_IN_FTD": "Missing in FTD",
    "EXTRA_IN_FTD": "Extra in FTD",
    "UNRESOLVED": "Unresolved",
}
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
THIN = Border(bottom=Side(style="thin", color="E3E8F0"))


def diff_text(d: dict | None, asa: dict | None, ftd: dict | None, field: str) -> str:
    """'- 192.0.2.11, - 192.0.2.10, + ANY' style text for a changed field."""
    if not d or not d.get("changed") or d.get("ignored"):
        return ""
    if field in ("src", "dst") and asa and ftd:
        if ftd.get(f"{field}_any") and not asa.get(f"{field}_any"):
            return ", ".join([f"- {x}" for x in asa[field]] + ["+ ANY"])
    return ", ".join([f"- {x}" for x in d.get("removed", [])] + [f"+ {x}" for x in d.get("added", [])])


def _diff_fill(d: dict | None, asa: dict | None = None, ftd: dict | None = None) -> PatternFill | None:
    if not d or not d.get("changed") or d.get("ignored"):
        return None
    r, a = bool(d.get("removed")), bool(d.get("added"))
    field = d.get("field")
    if field in ("src", "dst") and asa and ftd and ftd.get(f"{field}_any") and not asa.get(f"{field}_any"):
        r = a = True  # widened to ANY: written as '- old…, + ANY'

    if r and a:
        return FILL["both"]
    return FILL["removed"] if r else (FILL["added"] if a else FILL["both"])


RULE_COLUMNS: list[tuple[str, int]] = [
    ("ID", 6), ("Status", 16), ("Severity", 10), ("Key", 22), ("ACL", 16), ("Matched by", 11), ("Flags", 34),
    ("ASA key", 20), ("ASA action", 10), ("ASA enabled", 10), ("ASA source", 34), ("ASA destination", 34),
    ("ASA services", 30), ("ASA log", 8), ("ASA comment", 30),
    ("FTD position", 9), ("FTD name", 22), ("FTD action", 11), ("FTD enabled", 10), ("FTD source", 34),
    ("FTD destination", 34), ("FTD services", 30), ("FTD log", 8), ("FTD comment", 30),
    ("Source diff", 34), ("Destination diff", 34), ("Services diff", 34), ("Explanation", 70),
]


def _cell(ws, value, *, fill=None, font=None, align=WRAP) -> WriteOnlyCell:
    c = WriteOnlyCell(ws, value=value)
    if fill is not None:
        c.fill = fill
    if font is not None:
        c.font = font
    c.alignment = align
    return c


def _setup(ws, columns: list[tuple[str, int]]) -> None:
    for i, (_, w) in enumerate(columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _header(ws, columns: list[tuple[str, int]]) -> None:
    ws.append([_cell(ws, name, fill=FILL["header"], font=HEADER_FONT, align=Alignment(vertical="center"))
               for name, _ in columns])


def _j(items: list[str] | None) -> str:
    return "\n".join(items or [])


def _rule_row(ws, det: dict) -> list:
    a, f, diffs = det.get("asa"), det.get("ftd"), det.get("diffs", {})
    sev = det["severity"]

    def side(r: dict | None, field: str, expanded: bool = False) -> str:
        if r is None:
            return ""
        if field in ("src", "dst", "services"):
            written = r[{"src": "src_refs", "dst": "dst_refs", "services": "svc_refs"}[field]]
            exp = r[field]
            if written == exp:
                return _j(written)
            return _j(written) + ("\n= " + ", ".join(exp[:30]) + (" …" if len(exp) > 30 else "") if exp else "")
        return str(r.get(field, ""))

    def fld(field: str, which: str) -> PatternFill | None:
        d = diffs.get(field)
        if not d or not d.get("changed") or d.get("ignored") or not (a and f):
            return None
        if which == "asa" and d.get("removed"):
            return FILL["removed"]
        if which == "ftd" and d.get("added"):
            return FILL["added"]
        if field in ("action", "enabled", "log", "comment") or (field in ("src", "dst") and f.get(f"{field}_any")):
            return FILL["removed"] if which == "asa" else FILL["added"]
        return None

    def yn(r: dict | None, k: str) -> str:
        return "" if r is None else ("Yes" if r[k] else "No")

    return [
        _cell(ws, det["id"], align=TOP),
        _cell(ws, STATUS_LABEL.get(det["status"], det["status"]), align=TOP,
              fill=FILL["match"] if det["status"] in ("MATCH", "MATCH_MERGED") else None),
        _cell(ws, sev.capitalize() if sev != "none" else "", fill=FILL.get(sev), font=SEV_FONT.get(sev), align=TOP),
        _cell(ws, det["key"], align=TOP),
        _cell(ws, det["acl"], align=TOP),
        _cell(ws, det.get("matched_by") or "", align=TOP),
        _cell(ws, ", ".join(fl["code"] for fl in det["flags"])),
        _cell(ws, a["key"] if a else "", align=TOP),
        _cell(ws, a["action"] if a else "", fill=fld("action", "asa"), align=TOP),
        _cell(ws, yn(a, "enabled"), fill=fld("enabled", "asa"), align=TOP),
        _cell(ws, side(a, "src"), fill=fld("src", "asa")),
        _cell(ws, side(a, "dst"), fill=fld("dst", "asa")),
        _cell(ws, side(a, "services"), fill=fld("services", "asa")),
        _cell(ws, yn(a, "log"), fill=fld("log", "asa"), align=TOP),
        _cell(ws, a["comment"] if a else "", fill=fld("comment", "asa")),
        _cell(ws, f["position"] if f else None, align=TOP),
        _cell(ws, f["key"] if f else "", align=TOP),
        _cell(ws, (f["action_text"] or f["action"]) if f else "", fill=fld("action", "ftd"), align=TOP),
        _cell(ws, yn(f, "enabled"), fill=fld("enabled", "ftd"), align=TOP),
        _cell(ws, side(f, "src"), fill=fld("src", "ftd")),
        _cell(ws, side(f, "dst"), fill=fld("dst", "ftd")),
        _cell(ws, side(f, "services"), fill=fld("services", "ftd")),
        _cell(ws, yn(f, "log"), fill=fld("log", "ftd"), align=TOP),
        _cell(ws, f["comment"] if f else "", fill=fld("comment", "ftd")),
        _cell(ws, diff_text(diffs.get("src"), a, f, "src") if a and f else "", fill=_diff_fill(diffs.get("src"), a, f) if a and f else None),
        _cell(ws, diff_text(diffs.get("dst"), a, f, "dst") if a and f else "", fill=_diff_fill(diffs.get("dst"), a, f) if a and f else None),
        _cell(ws, diff_text(diffs.get("services"), a, f, "services") if a and f else "",
              fill=_diff_fill(diffs.get("services"), a, f) if a and f else None),
        _cell(ws, det["explanation"]),
    ]


def _rules_sheet(wb: Workbook, title: str, details: Iterable[dict]) -> None:
    ws = wb.create_sheet(title)
    _setup(ws, RULE_COLUMNS)
    _header(ws, RULE_COLUMNS)
    n = 0
    for det in details:
        ws.append(_rule_row(ws, det))
        n += 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(RULE_COLUMNS))}{max(n + 1, 2)}"


def _table_sheet(wb: Workbook, title: str, columns: list[tuple[str, int]], rows: Iterable[list]) -> None:
    ws = wb.create_sheet(title)
    _setup(ws, columns)
    _header(ws, columns)
    n = 0
    for row in rows:
        ws.append([_cell(ws, v) for v in row])
        n += 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(n + 1, 2)}"


def write_excel(session: dict, path: str | Path, ids: list[int] | None = None) -> Path:
    meta = session["meta"]
    details = session["details"]
    if ids is not None:
        keep = set(ids)
        details = [d for d in details if d["id"] in keep]
    wb = Workbook(write_only=True)

    # 1. Summary ------------------------------------------------------------
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 60
    for col in "CDEFGHI":
        ws.column_dimensions[col].width = 14

    def line(*vals, font=None, fill=None):
        ws.append([_cell(ws, v, font=font, fill=fill, align=TOP) for v in vals])

    line("Sibit", font=Font(bold=True, size=22, color=BRAND))
    line("See every rule. Miss nothing.", font=Font(italic=True, color="5B6B85"))
    line("Firewall Migration Rule Verifier — ASA → FTD comparison report", font=Font(color="5B6B85"))
    line()
    line("Project", meta["name"])
    line("ASA config (before)", meta["asa_name"])
    line("FTD policy report (after)", meta["ftd_name"])
    line("Compared", meta["created"])
    line("Report generated", datetime.now().isoformat(timespec="seconds"))
    if ids is not None:
        line("Scope", f"Filtered view: {len(details)} of {len(session['details'])} rules")
    cal = meta["calibration"]
    line("Numbering strategy", f"{cal['strategy']} (requested: {cal['requested']})")
    line("Matched by name", f"{cal['match_rate']}% of ASA rules ({cal['matched_by_name']} of {cal['asa_rules']})")
    line("Matched by content", cal["matched_by_content"])
    line()
    counts = meta["counts"]
    line("Key figures", font=Font(bold=True, size=13, color=BRAND))
    line("Total rules", counts["total"], font=Font(bold=True))
    for s, label in STATUS_LABEL.items():
        line(label, counts["status"].get(s, 0))
    line("Critical risks", counts["severity"].get("critical", 0), font=SEV_FONT["critical"], fill=FILL["critical"])
    line("High risks", counts["severity"].get("high", 0), font=SEV_FONT["high"], fill=FILL["high"])
    line("Medium risks", counts["severity"].get("medium", 0), font=SEV_FONT["medium"], fill=FILL["medium"])
    line("Low", counts["severity"].get("low", 0))
    line("Order changes around deny rules", meta.get("order_change_count", 0))
    line()
    line("Per ACL", font=Font(bold=True, size=13, color=BRAND))
    hdr = ["ACL", "Total", "Match", "Merged", "Changed", "Missing", "Extra", "Unresolved", "Critical"]
    ws.append([_cell(ws, h, fill=FILL["header"], font=HEADER_FONT) for h in hdr])
    for a in meta["per_acl"]:
        line(a["acl"], a["total"], a["MATCH"], a["MATCH_MERGED"], a["CHANGED"], a["MISSING_IN_FTD"],
             a["EXTRA_IN_FTD"], a["UNRESOLVED"], a["critical"])

    # 2-7. Rule sheets -------------------------------------------------------
    _rules_sheet(wb, "All Rules", details)
    _rules_sheet(wb, "Critical & High", (d for d in details if d["severity"] in ("critical", "high")))
    _rules_sheet(wb, "Changed", (d for d in details if d["status"] == "CHANGED"))
    _rules_sheet(wb, "Missing in FTD", (d for d in details if d["status"] == "MISSING_IN_FTD"))
    _rules_sheet(wb, "Extra in FTD", (d for d in details if d["status"] == "EXTRA_IN_FTD"))

    keep_ids = {d["id"] for d in details}
    _table_sheet(
        wb, "Order Changes",
        [("ACL", 16), ("Rule", 24), ("Deny rule", 24), ("ASA: rule is", 12), ("FTD: rule is", 12),
         ("ASA rule line", 12), ("ASA deny line", 12), ("FTD rule position", 14), ("FTD deny position", 14)],
        ([o["acl"], o["rule_key"], o["deny_key"], f"{o['asa_relation']} deny", f"{o['ftd_relation']} deny",
          o["asa_rule_line"], o["asa_deny_line"], o["ftd_rule_position"], o["ftd_deny_position"]]
         for o in session["order_changes"] if o["rule_id"] in keep_ids or o["deny_id"] in keep_ids),
    )
    _table_sheet(
        wb, "Unresolved Objects",
        [("Side", 8), ("Name", 34), ("Reason", 44), ("Used by (rules)", 12), ("Rule keys", 60)],
        ([u["side"], u["name"], u["reason"], len(u["used_by"]),
          ", ".join(session["rows"][i]["key"] for i in u["used_by"][:50])] for u in session["unresolved"]),
    )
    out = Path(path)
    wb.save(out)
    return out
