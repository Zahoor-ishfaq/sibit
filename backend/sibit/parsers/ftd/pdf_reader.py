"""Streaming PDF line extraction with PyMuPDF (spec 3.2).

Pages are processed one at a time; only the current page's text is in memory.
Each yielded line keeps its spans' x positions, which the Referenced Objects
parser uses to tell the Name column from the Value column.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterator

import pymupdf as fitz

_PAGE_NO = re.compile(r"^\s*\d+\s*$")
_PAGE_OF = re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE)
MARGIN_PT = 40.0  # header/footer band height used for repeated-line detection
FOOTER_BAND_PT = 60.0  # band where page numbers are recognised


@dataclass
class Span:
    x0: float
    text: str
    y: float = 0.0  # vertical centre
    size: float = 0.0  # font size


@dataclass
class PdfLine:
    page: int  # 1-based
    y: float
    spans: list[Span]

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.spans).strip()

    @property
    def x0(self) -> float:
        return self.spans[0].x0 if self.spans else 0.0


def _page_lines(page: fitz.Page, page_no: int) -> list[PdfLine]:
    """Extract lines, merging fragments that share a baseline (label + value)."""
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    raw: list[tuple[float, float, float, str, float]] = []  # (y_mid, x0, x1, text, size)
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            x0 = spans[0]["bbox"][0]
            x1 = spans[-1]["bbox"][2]
            y0 = min(s["bbox"][1] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            # Keep internal spacing of a line; spans in one PDF line are one text run.
            text = "".join(s["text"] for s in spans)
            size = max(s.get("size", 0.0) for s in spans)
            raw.append(((y0 + y1) / 2, x0, x1, " ".join(text.split()), size))
    raw.sort(key=lambda r: (round(r[0], 0), r[1]))
    out: list[PdfLine] = []
    for y, x0, _x1, text, size in raw:
        if out and abs(out[-1].y - y) <= 2.5 and x0 >= out[-1].spans[-1].x0:
            out[-1].spans.append(Span(x0, text, y, size))
        else:
            out.append(PdfLine(page_no, y, [Span(x0, text, y, size)]))
    return out


# --------------------------------------------------------------------------- #
# Two-column table cells
# --------------------------------------------------------------------------- #
# The FMC report renders rules and Referenced Objects as a two-column table:
# labels (or object names) on the left, values on the right. In a multi-line
# cell the label is vertically CENTRED on its value list, so reading text in
# y order interleaves labels and values. ``page_cells`` rebuilds the cells:
# value lines are grouped by vertical gap (lines inside a cell are ~9.6 pt
# apart, rows >= 14 pt), and each group is attached to the label whose y lies
# within it. A group at the top of a page with no label continues the last
# cell of the previous page.
LABEL_MAX_X = 150.0  # left column ends here
CELL_GAP = 12.0  # larger vertical gap between value lines = new cell
HEADING_SIZE = 9.5  # section headings use a larger font than table text


@dataclass
class Cell:
    kind: str  # 'heading' | 'cell' | 'cont'
    label: str
    values: list[str]
    y: float
    page: int


def page_cells(lines: list[PdfLine], label_max_x: float = LABEL_MAX_X) -> list[Cell]:
    if not lines:
        return []
    page = lines[0].page
    labels: list[Span] = []
    headings: list[Span] = []
    values: list[Span] = []
    for ln in lines:
        for sp in ln.spans:
            if sp.x0 < label_max_x:
                (headings if sp.size >= HEADING_SIZE else labels).append(sp)
            else:
                values.append(sp)
    values.sort(key=lambda s: (s.y, s.x0))
    groups: list[list[Span]] = []
    for sp in values:
        if groups and sp.y - groups[-1][-1].y <= CELL_GAP:
            groups[-1].append(sp)
        else:
            groups.append([sp])
    labels.sort(key=lambda s: s.y)
    owner: dict[int, list[list[Span]]] = {}
    conts: list[list[Span]] = []
    first_label_y = labels[0].y if labels else float("inf")
    for g in groups:
        top, bot = g[0].y, g[-1].y
        inside = [i for i, lb in enumerate(labels) if top - 3 <= lb.y <= bot + 3]
        if inside:
            mid = (top + bot) / 2
            i = min(inside, key=lambda k: abs(labels[k].y - mid))
            owner.setdefault(i, []).append(g)
        elif top < first_label_y:
            conts.append(g)
        else:
            above = [i for i, lb in enumerate(labels) if lb.y < top]
            owner.setdefault(above[-1], []).append(g)
    out: list[Cell] = [Cell("cont", "", [s.text for s in g], g[0].y, page) for g in conts]
    out += [Cell("heading", h.text, [], h.y, page) for h in headings]
    for i, lb in enumerate(labels):
        vals = [s.text for g in owner.get(i, []) for s in g]
        y = min([lb.y] + [g[0].y for g in owner.get(i, [])])
        out.append(Cell("cell", lb.text, vals, y, page))
    out.sort(key=lambda c: (c.kind != "cont", c.y))
    return out


def _is_noise(line: PdfLine, page_h: float, repeated: set[str]) -> bool:
    t = line.text
    if not t:
        return True
    # Page numbers live in the header/footer bands only: real reports contain
    # port objects named with bare numbers ('49342') inside the tables.
    in_band = line.y < FOOTER_BAND_PT or line.y > page_h - FOOTER_BAND_PT
    if in_band and (_PAGE_NO.match(t) or _PAGE_OF.match(t)):
        return True
    in_margin = line.y < MARGIN_PT or line.y > page_h - MARGIN_PT
    return in_margin and t in repeated


def detect_repeated_margin_lines(doc: fitz.Document, sample: int = 30) -> set[str]:
    """Lines that appear in the header/footer band on most sampled pages."""
    n = min(sample, doc.page_count)
    if n < 3:
        return set()
    counts: Counter[str] = Counter()
    for i in range(n):
        page = doc.load_page(i)
        h = page.rect.height
        seen = {ln.text for ln in _page_lines(page, i + 1) if ln.y < MARGIN_PT or ln.y > h - MARGIN_PT}
        counts.update(seen)
    return {t for t, c in counts.items() if c >= max(3, int(n * 0.6))}


def iter_pages(path: str) -> Iterator[tuple[int, int, list[PdfLine]]]:
    """Yield (page_no, page_count, clean_lines) one page at a time."""
    doc = fitz.open(path)
    try:
        repeated = detect_repeated_margin_lines(doc)
        total = doc.page_count
        for i in range(total):
            page = doc.load_page(i)
            h = page.rect.height
            lines = [ln for ln in _page_lines(page, i + 1) if not _is_noise(ln, h, repeated)]
            yield i + 1, total, lines
            page = None  # release page resources early
    finally:
        doc.close()


def pdf_info(path: str) -> dict:
    """Cheap type check for the upload screen: page count + header lines."""
    doc = fitz.open(path)
    try:
        head = ""
        for i in range(min(2, doc.page_count)):
            head += doc.load_page(i).get_text("text") + "\n"
        ok = "Access Control Policy" in head
        policy = hostname = None
        lines = [line.strip() for line in head.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            if line.startswith("Access Control Policy Report") and i + 1 < len(lines):
                policy = lines[i + 1]
            m = re.search(r"source with hostname\s+(\S+)", line)
            if m:
                hostname = m.group(1)
        return {"ok": ok, "pages": doc.page_count, "policy": policy, "hostname": hostname}
    finally:
        doc.close()
