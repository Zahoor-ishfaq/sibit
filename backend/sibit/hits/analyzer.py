"""Hit-count analysis: which rules were hit, and which have 0 hits ("garbage").

The input is `show access-list` output (FTD/ASA) pasted into Excel with the
words spread over cells in varying columns, possibly over many sheets. Column
positions are therefore ignored: each row is joined into one line of words and
the Cisco keywords are found wherever they are:

    RULE: Outside-In_migration_1_#12                        -> starts a rule block
    Inside object-group DM_INLINE_NETWORK_1 host 198.51.100.80 eq https
        rule-id 268435460 (hitcnt=0) 0x1a2b3c4d (hitcnt=0) ... -> one ACE line

Every `hitcnt=N` in a row counts (extra columns = more devices/snapshots).
Lines are grouped into rules by `rule-id` (FTD), else `access-list X line N`
(ASA), else the current `RULE:` block. Table-style exports (a header row with
"Rule" and "Hit Count" columns within the first 50 rows of a sheet) are read
by column instead.

Verdict per rule (the decision rule requested for this feature):
    GARBAGE  hit data present and every hit count is 0
    IN_USE   at least one hit count > 0
    NO_DATA  lines found but no hit count at all (cannot decide)

Built for millions of rows: rows stream from the reader, the common row type
takes a fast path, and lines are stored column-wise in compact arrays.
"""
from __future__ import annotations

import re
import time
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..parsers.common import Cancelled
from .reader import cell_text, iter_raw_rows, sheet_names

# 'RULE: name' / 'Rule Name: name' anywhere in a row (the name may sit in any later column).
_RULE_HDR = re.compile(r"(?:^|\s)rule(?:\s*name)?\s*[:=]\s*(?P<name>\S.*?)\s*$", re.IGNORECASE)
# FTD 'show access-list' names rules in remark lines:
#   access-list CSM_FW_ACL_ line 11 remark rule-id 268435460: L7 RULE: Outside-In_migration_1_#12
_REMARK_NAME = re.compile(r"\brule-id\s*[:=]?\s*(?P<id>\d+)\s*:\s*(?:L[47]\s+)?RULE\s*:\s*(?P<name>\S.*?)\s*$",
                          re.IGNORECASE)
_RULE_ID = re.compile(r"\brule-id\s*[:=]?\s*(\d+)", re.IGNORECASE)
_HITCNT = re.compile(r"hitcnt\s*=\s*(\d+)", re.IGNORECASE)
_HASH = re.compile(r"\b0x[0-9a-fA-F]{4,16}\b")
_ACL_LINE = re.compile(r"\baccess-list\s+(\S+)\s+line\s+(\d+)\b", re.IGNORECASE)
_SUMMARY = re.compile(r"\b(object-group|object)\s+\S+", re.IGNORECASE)
_ACTION = re.compile(r"\b(permit|deny|trust|allow|block)\b", re.IGNORECASE)
_HIT_HEADER = re.compile(r"^(hit\s*count(s)?|hits?|hitcnt|hit\s*cnt)$", re.IGNORECASE)
_RULE_HEADER = re.compile(r"^(rule(\s*name)?|name|policy\s*rule|access\s*rule)$", re.IGNORECASE)
_NAME_HEADER = re.compile(r"^(rule\s*name|name|policy\s*rule\s*name|access\s*rule\s*name)$", re.IGNORECASE)
_ID_HEADER = re.compile(r"^(rule[\s_-]*id|id)$", re.IGNORECASE)

GARBAGE, IN_USE, NO_DATA = "GARBAGE", "IN_USE", "NO_DATA"
KINDS = ("summary", "element", "table")
HEADER_SCAN_ROWS = 50
MAX_TEXT = 400


@dataclass(slots=True)
class HitRule:
    key: str  # grouping key: 'id:268435460' | 'acl:Outside-In:12' | 'name:...'
    name: str
    rule_id: str | None = None
    acl: str | None = None
    acl_line: int | None = None
    action: str | None = None
    lines: array = field(default_factory=lambda: array("I"))  # indexes into LineStore
    total_hits: int = 0
    hit_values: int = 0  # how many hitcnt values were seen
    zero_elements: int = 0  # element lines with 0 hits (partial clean-up info)
    elements: int = 0
    first_sheet: int = 0
    first_row: int = 0
    named: bool = False  # False: the file never gave this rule a name (a rule-id placeholder is shown)

    @property
    def verdict(self) -> str:
        if self.hit_values == 0:
            return NO_DATA
        return IN_USE if self.total_hits > 0 else GARBAGE


class LineStore:
    """Column-wise storage for millions of rule lines."""

    __slots__ = ("sheet", "row", "hit_sum", "hit_n", "kind", "hash", "text")

    def __init__(self) -> None:
        self.sheet = array("H")
        self.row = array("I")
        self.hit_sum = array("Q")
        self.hit_n = array("H")
        self.kind = bytearray()
        self.hash: list[str | None] = []
        self.text: list[str] = []

    def __len__(self) -> int:
        return len(self.row)

    def add(self, sheet: int, row: int, text: str, hits: list[int], h: str | None, kind: int) -> int:
        self.sheet.append(sheet)
        self.row.append(row)
        self.hit_sum.append(sum(hits))
        self.hit_n.append(min(len(hits), 65535))
        self.kind.append(kind)
        self.hash.append(h)
        self.text.append(text[:MAX_TEXT])
        return len(self.row) - 1

    def get(self, i: int) -> dict:
        return {
            "sheet": self.sheet[i], "row": self.row[i], "hit_sum": self.hit_sum[i], "hit_n": self.hit_n[i],
            "hits": [int(x) for x in _HITCNT.findall(self.text[i])] if self.kind[i] != 2 else None,
            "kind": KINDS[self.kind[i]], "hash": self.hash[i], "text": self.text[i],
        }


@dataclass
class HitWarning:
    sheet: str
    row: int
    text: str
    message: str


@dataclass
class HitResult:
    file_name: str
    sheets: list[str]
    rules: list[HitRule]
    lines: LineStore
    warnings: list[HitWarning]
    rows_read: int
    rows_used: int
    seconds: float

    def counts(self) -> dict:
        c = {GARBAGE: 0, IN_USE: 0, NO_DATA: 0}
        for r in self.rules:
            c[r.verdict] += 1
        return c

    def line(self, i: int) -> dict:
        return self.lines.get(i)


def _table_header(cells: list[str]) -> dict | None:
    """Detect table headers.

    'Rule Name | ... | Hit Count'  -> hit table
    'Rule ID | Rule Name'          -> name table (maps rule-ids to names, e.g. an FMC export sheet)
    """
    low = [c.strip() for c in cells]
    hit_cols = [i for i, c in enumerate(low) if _HIT_HEADER.match(c)]
    id_cols = [i for i, c in enumerate(low) if _ID_HEADER.match(c)]
    if hit_cols:
        rule_cols = [i for i, c in enumerate(low) if _RULE_HEADER.match(c)]
        if not rule_cols:
            return None
        return {"kind": "hits", "rule": rule_cols[0], "hits": hit_cols, "id": id_cols[0] if id_cols else None}
    name_cols = [i for i, c in enumerate(low) if _NAME_HEADER.match(c)]
    if id_cols and name_cols:
        return {"kind": "names", "id": id_cols[0], "name": name_cols[0]}
    return None


def analyze(
    path: str | Path,
    file_name: str | None = None,
    progress: Callable[[str, dict], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> HitResult:
    t0 = time.perf_counter()
    path = Path(path)
    sheets = sheet_names(path)
    sheet_idx = {s: i for i, s in enumerate(sheets)}
    rules: dict[str, HitRule] = {}
    store = LineStore()
    warnings: list[HitWarning] = []
    rows_read = rows_used = 0
    current_name: str | None = None
    current_sheet = None
    table: dict | None = None
    id_names: dict[str, str] = {}  # rule-id -> name, from remarks, RULE: headers or a names table
    header_rid: str | None = None  # the rule-id the current RULE: header was bound to
    si = 0

    def rule_for(key: str, name: str, row: int) -> HitRule:
        r = rules.get(key)
        if r is None:
            r = rules[key] = HitRule(key, name, first_sheet=si, first_row=row)
        return r

    def add_line(r: HitRule, row: int, text: str, hits: list[int], h: str | None, kind: int) -> None:
        r.lines.append(store.add(si, row, text, hits, h, kind))
        r.hit_values += len(hits)
        s = sum(hits)
        r.total_hits += s

    for sheet, row_no, raw in iter_raw_rows(path):
        rows_read += 1
        if rows_read % 20000 == 0:
            if is_cancelled and is_cancelled():
                raise Cancelled()
            if progress:
                progress("hits_rows", {"rows": rows_read, "sheet": sheet, "rules": len(rules)})
        if sheet != current_sheet:
            current_sheet, current_name, table, header_rid = sheet, None, None, None
            si = sheet_idx.get(sheet, 0)

        # --- table-style export (needs cell positions) -----------------------------------
        if table is not None or row_no <= HEADER_SCAN_ROWS:
            cells = [cell_text(v) for v in raw]
            text = " ".join(c for c in cells if c)
            if "hitcnt" not in text.lower():
                if table is None:
                    hdr = _table_header(cells)
                    if hdr is not None:
                        table = hdr
                        continue
                elif table["kind"] == "names":
                    rid = cells[table["id"]] if table["id"] < len(cells) else ""
                    nm = cells[table["name"]] if table["name"] < len(cells) else ""
                    if rid.isdigit() and nm:
                        id_names[rid] = nm
                    continue
                else:
                    name = cells[table["rule"]] if table["rule"] < len(cells) else ""
                    hits: list[int] = []
                    for c in table["hits"]:
                        v = cells[c].replace(",", "") if c < len(cells) else ""
                        if v.isdigit():
                            hits.append(int(v))
                        elif v:
                            warnings.append(HitWarning(sheet, row_no, text[:200], f"Hit count '{v}' is not a number"))
                    if not name:
                        continue
                    rid = cells[table["id"]] if table["id"] is not None and table["id"] < len(cells) else ""
                    r = rule_for(f"id:{rid}" if rid else f"name:{name}", name, row_no)
                    r.rule_id = r.rule_id or rid or None
                    r.named = True
                    add_line(r, row_no, text, hits, None, 2)
                    rows_used += 1
                    continue
        else:
            # Fast path: plain words, no positions needed.
            text = " ".join([cell_text(v) for v in raw if v != "" and v is not None])

        # --- show access-list text --------------------------------------------------------
        low = text.lower()
        has_hits = "hitcnt" in low
        has_rid = "rule-id" in low
        if " remark " in f" {low} " and not has_hits:
            # Remarks are never rule lines; 'remark rule-id N: L7 RULE: name' names rule N.
            if has_rid and (m := _REMARK_NAME.search(text)):
                id_names[m.group("id")] = m.group("name").strip()
            continue
        if not has_hits and not has_rid:
            if "rule" in low and (m := _RULE_HDR.search(text)):
                current_name, header_rid = m.group("name").strip(), None
                continue
            if "access-list" not in low:
                continue  # titles and unrelated rows
        elif not has_hits and (m := _REMARK_NAME.search(text)):
            # 'rule-id N: L7 RULE: name' pasted into cells without the word 'remark'
            id_names[m.group("id")] = m.group("name").strip()
            continue
        hits = [int(h) for h in _HITCNT.findall(text)] if has_hits else []
        rid_m = _RULE_ID.search(text) if has_rid else None
        acl_m = _ACL_LINE.search(text) if "access-list" in low else None
        if not hits and not rid_m and not acl_m:
            continue
        rid = rid_m.group(1) if rid_m else None
        if rid:
            key = "id:" + rid
            # A RULE: header names the rule-id that follows it — never a different rule-id later on.
            if current_name and header_rid in (None, rid):
                header_rid = rid
                id_names.setdefault(rid, current_name)
            name = id_names.get(rid) or f"rule-id {rid}"
        elif acl_m:
            key = f"acl:{acl_m.group(1)}:{acl_m.group(2)}"
            name = current_name or f"{acl_m.group(1)} line {acl_m.group(2)}"
        elif current_name:
            key = "name:" + current_name
            name = current_name
        else:
            warnings.append(HitWarning(sheet, row_no, text[:200],
                                       "Hit count found but no rule-id, access-list line or RULE: header"))
            continue
        r = rule_for(key, name, row_no)
        known = id_names.get(rid) if rid else current_name
        if not r.named and known:
            r.name, r.named = known, True
        elif not r.named and acl_m and not rid:
            r.named = True  # ASA: 'ACL line N' is the rule's identity
        if rid:
            r.rule_id = rid
        if acl_m and r.acl is None:
            r.acl, r.acl_line = acl_m.group(1), int(acl_m.group(2))
        if r.action is None and ("permit" in low or "deny" in low or "allow" in low or "block" in low
                                 or "trust" in low) and (a := _ACTION.search(text)):
            r.action = a.group(1).lower()
        h = _HASH.search(text)
        kind = 0 if ("object" in low and _SUMMARY.search(text)) else 1
        if not hits:
            warnings.append(HitWarning(sheet, row_no, text[:200], "Rule line without a hit count"))
        add_line(r, row_no, text, hits, h.group(0) if h else None, kind)
        rows_used += 1

    for r in rules.values():
        if not r.named and r.rule_id and r.rule_id in id_names:
            r.name, r.named = id_names[r.rule_id], True
    unnamed = sum(1 for r in rules.values() if not r.named)
    if unnamed:
        warnings.append(HitWarning("", 0, f"{unnamed} rule(s)",
                                   "No rule name in the file for these rules (shown by rule-id). Names are read from "
                                   "'RULE: name' rows, 'remark rule-id N: L7 RULE: name' lines, or a sheet with "
                                   "'Rule ID' and 'Rule Name' columns."))
    _count_elements(rules.values(), store)
    if progress:
        progress("hits_done", {"rows": rows_read, "rules": len(rules)})
    return HitResult(file_name or path.name, sheets, list(rules.values()), store, warnings, rows_read, rows_used,
                     round(time.perf_counter() - t0, 2))


def _count_elements(rules, store: LineStore) -> None:
    """Distinct element lines per rule, keyed by ACE hash (else text), summed over every
    sheet/column: the same element seen on two devices is one element, and it is a
    zero-hit element only if it is 0 everywhere."""
    for r in rules:
        sums: dict[str, int] = {}
        seen: dict[str, int] = {}
        for i in r.lines:
            if store.kind[i] != 1:
                continue
            k = store.hash[i] or store.text[i]
            sums[k] = sums.get(k, 0) + store.hit_sum[i]
            seen[k] = seen.get(k, 0) + store.hit_n[i]
        r.elements = len(sums)
        r.zero_elements = sum(1 for k, v in sums.items() if v == 0 and seen[k] > 0)
