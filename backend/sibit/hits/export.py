"""Hit-count report: Excel (XlsxWriter low-memory mode, overflow sheets past Excel's row limit) and CSV."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import xlsxwriter

from .analyzer import GARBAGE, IN_USE, NO_DATA, HitResult

EXCEL_MAX_ROWS = 1_048_576
LABEL = {GARBAGE: "Garbage (0 hits)", IN_USE: "In use", NO_DATA: "No hit data"}

RULE_COLS = [("Verdict", 16), ("Rule name", 44), ("Rule-id", 14), ("ACL", 18), ("ACL line", 9), ("Action", 9),
             ("Total hits", 12), ("Hit values", 10), ("Lines", 8), ("Zero-hit element lines", 12),
             ("Element lines", 10), ("Sheet", 18), ("First row", 10)]
LINE_COLS = [("Rule name", 40), ("Rule-id", 14), ("Sheet", 18), ("Row", 10), ("Kind", 10), ("Line hits", 10),
             ("Hash", 13), ("Line text", 110)]


class _Sheets:
    """Appends rows, continuing on 'Name (2)', 'Name (3)'… at Excel's row limit (XlsxWriter, low-memory mode)."""

    def __init__(self, wb: xlsxwriter.Workbook, fmt: dict, title: str, cols: list[tuple[str, int]]) -> None:
        self.wb, self.fmt, self.title, self.cols, self.n, self.part = wb, fmt, title, cols, 0, 0
        self._new()

    def _new(self) -> None:
        self.part += 1
        name = self.title if self.part == 1 else f"{self.title[:26]} ({self.part})"
        self.ws = self.wb.add_worksheet(name)
        for i, (_, w) in enumerate(self.cols):
            self.ws.set_column(i, i, w)
        self.ws.freeze_panes(1, 0)
        self.ws.write_row(0, 0, [h for h, _ in self.cols], self.fmt["hdr"])
        self.n = 1

    def add(self, values: list, verdict: str | None = None) -> None:
        if self.n >= EXCEL_MAX_ROWS:
            self.close()
            self._new()
        # Only the first cell is coloured; plain values keep million-row exports fast.
        self.ws.write(self.n, 0, values[0], self.fmt.get(verdict))
        self.ws.write_row(self.n, 1, values[1:])
        self.n += 1

    def close(self) -> None:
        self.ws.autofilter(0, 0, max(self.n - 1, 1), len(self.cols) - 1)


def _rule_values(res: HitResult, i: int) -> list:
    r = res.rules[i]
    return [LABEL[r.verdict], r.name if r.named else f"(no name in file) {r.name}", r.rule_id, r.acl, r.acl_line, r.action, r.total_hits, r.hit_values,
            len(r.lines), r.zero_elements, r.elements, res.sheets[r.first_sheet] if res.sheets else "", r.first_row]


def write_hits_excel(res: HitResult, path: str | Path, ids: list[int] | None = None) -> Path:
    ids = list(range(len(res.rules))) if ids is None else ids
    out = Path(path)
    wb = xlsxwriter.Workbook(str(out), {"constant_memory": True, "strings_to_numbers": False,
                                        "strings_to_urls": False, "strings_to_formulas": False})
    fmt = {
        "hdr": wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1E3A8A"}),
        GARBAGE: wb.add_format({"bg_color": "#FDE2E7"}),
        IN_USE: wb.add_format({"bg_color": "#D1FAE5"}),
        NO_DATA: wb.add_format({"bg_color": "#FEF3C7"}),
        "title": wb.add_format({"bold": True, "font_size": 18, "font_color": "#1E3A8A"}),
        "wrap": wb.add_format({"text_wrap": True, "valign": "top"}),
    }
    counts = {GARBAGE: 0, IN_USE: 0, NO_DATA: 0}
    for i in ids:
        counts[res.rules[i].verdict] += 1
    ws = wb.add_worksheet("Summary")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 90)
    rows = [
        ("Sibit — Hit count analysis", None, "title"),
        ("File", res.file_name, None),
        ("Sheets", ", ".join(res.sheets), None),
        ("Generated", datetime.now().isoformat(timespec="seconds"), None),
        ("Rows read", res.rows_read, None),
        ("Rule lines found", len(res.lines), None),
        ("Rules", len(ids), None),
        (None, None, None),
        ("Garbage (0 hits)", counts[GARBAGE], GARBAGE),
        ("In use", counts[IN_USE], IN_USE),
        ("No hit data (not decided)", counts[NO_DATA], NO_DATA),
        (None, None, None),
        ("Rule", "GARBAGE = every hit count of every line of the rule, in every column, is 0. IN USE = at least "
                 "one hit count > 0. NO HIT DATA = rule lines without any hitcnt value.", "wrap"),
        ("Cross-check", "Verify before removing: counters must have run long enough, on every firewall of the pair.",
         "wrap"),
    ]
    for r, (a, b, f) in enumerate(rows):
        ws.write(r, 0, a, fmt.get(f) if f in (GARBAGE, IN_USE, NO_DATA, "title") else None)
        ws.write(r, 1, b, fmt["wrap"] if f == "wrap" else None)

    for verdict, title in ((GARBAGE, "Garbage (0 hits)"), (IN_USE, "In use"), (NO_DATA, "No hit data")):
        sh = _Sheets(wb, fmt, title, RULE_COLS)
        for i in ids:
            if res.rules[i].verdict == verdict:
                sh.add(_rule_values(res, i), verdict)
        sh.close()
    sh = _Sheets(wb, fmt, "Garbage rule lines", LINE_COLS)
    store = res.lines
    for i in ids:
        r = res.rules[i]
        if r.verdict != GARBAGE:
            continue
        for li in r.lines:
            sh.add([r.name if r.named else f"(no name in file) {r.name}", r.rule_id, res.sheets[store.sheet[li]], store.row[li], ("group", "element", "table")[store.kind[li]],
                    store.hit_sum[li], store.hash[li], store.text[li]], GARBAGE)
    sh.close()
    sh = _Sheets(wb, fmt, "Warnings", [("Sheet", 18), ("Row", 10), ("Message", 60), ("Text", 110)])
    for w in res.warnings:
        sh.add([w.sheet, w.row, w.message, w.text])
    sh.close()
    wb.close()
    return out


def write_hits_csv(res: HitResult, path: str | Path, ids: list[int] | None = None) -> Path:
    ids = list(range(len(res.rules))) if ids is None else ids
    out = Path(path)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([h for h, _ in RULE_COLS])
        for i in ids:
            w.writerow(_rule_values(res, i))
    return out
