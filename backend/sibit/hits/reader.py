"""Row readers for hit-count files: Excel (all sheets), CSV and plain text.

Every reader yields (sheet name, 1-based row number, [cell strings by column]);
empty cells are '' so column positions are preserved for table-style files.
Excel is read with python-calamine (Rust) row by row, so files with millions
of rows stream instead of being loaded whole.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator

EXCEL_EXT = {".xlsx", ".xlsm", ".xlsb", ".xls", ".ods"}
TEXT_EXT = {".txt", ".log", ".cfg"}


def cell_text(v: object) -> str:
    if v is None:
        return ""
    if type(v) is str:
        return v.strip()
    if isinstance(v, float):
        # Excel stores 268435460 as 268435460.0 — keep integers exact.
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v).strip()


def sheet_names(path: str | Path) -> list[str]:
    p = Path(path)
    if p.suffix.lower() in EXCEL_EXT:
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(p))
        try:
            return list(wb.sheet_names)
        finally:
            wb.close()
    return [p.name]


def iter_rows(path: str | Path) -> Iterator[tuple[str, int, list[str]]]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in EXCEL_EXT:
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(p))
        try:
            for name in wb.sheet_names:
                sheet = wb.get_sheet_by_name(name)
                for i, row in enumerate(sheet.iter_rows(), 1):
                    cells = [cell_text(v) for v in row]
                    if any(cells):
                        yield name, i, cells
        finally:
            wb.close()
        return
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    if ext == ".csv" or (ext not in TEXT_EXT and text[:4096].count(",") > text[:4096].count(" ")):
        for i, row in enumerate(csv.reader(io.StringIO(text)), 1):
            cells = [c.strip() for c in row]
            if any(cells):
                yield p.name, i, cells
        return
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            yield p.name, i, [line.strip()]


def iter_raw_rows(path: str | Path) -> Iterator[tuple[str, int, list]]:
    """Like iter_rows, but Excel cells stay raw (str/float/int/None) — convert with cell_text().

    Avoids converting every cell of every row on the fast path.
    """
    p = Path(path)
    if p.suffix.lower() in EXCEL_EXT:
        from python_calamine import CalamineWorkbook

        wb = CalamineWorkbook.from_path(str(p))
        try:
            for name in wb.sheet_names:
                for i, row in enumerate(wb.get_sheet_by_name(name).iter_rows(), 1):
                    for v in row:
                        if v != "" and v is not None:
                            yield name, i, row
                            break
        finally:
            wb.close()
        return
    yield from iter_rows(p)
