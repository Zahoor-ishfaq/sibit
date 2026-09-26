"""FtdSource interface (spec 3.3) and the FMC PDF report implementation.

The comparison engine only sees ``FtdPolicy``. A future FMC REST API source
implements ``FtdSource.load`` returning the same structure.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from ..common import Cancelled, ParseWarning, ProgressFn
from .pdf_reader import iter_pages, page_cells
from .referenced_objects import FtdObject, ReferencedObjectsParser
from .rule_block import RawFtdRule, RuleBlockParser


@dataclass
class FtdPolicy:
    policy_name: str | None
    hostname: str | None
    page_count: int
    raw_rules: list[RawFtdRule]
    objects: dict[str, FtdObject]
    warnings: list[ParseWarning] = field(default_factory=list)
    has_rules_section: bool = False
    has_referenced_objects: bool = False


class FtdSource(ABC):
    @abstractmethod
    def load(self, progress: ProgressFn | None = None, is_cancelled: Callable[[], bool] | None = None) -> FtdPolicy:
        ...


class NotAnFmcReport(ValueError):
    pass


class PdfFtdSource(FtdSource):
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self, progress: ProgressFn | None = None, is_cancelled: Callable[[], bool] | None = None) -> FtdPolicy:
        rules = RuleBlockParser()
        refs = ReferencedObjectsParser()
        in_refs = False
        policy_name = hostname = None
        header_lines: list[str] = []
        page_count = 0
        saw_report_title = False
        saw_rules_heading = False
        saw_refs = False
        for page_no, total, lines in iter_pages(self.path):
            page_count = total
            if is_cancelled and is_cancelled():
                raise Cancelled()
            if progress and (page_no == 1 or page_no % 5 == 0 or page_no == total):
                progress("ftd_pages", {"page": page_no, "pages": total, "rules": len(rules.rules)})
            for ln in lines:
                if page_no <= 2 and len(header_lines) < 40:
                    header_lines.append(ln.text)
            for cell in page_cells(lines):
                text = cell.label if cell.kind != "cont" else ""
                if text == "Access Control Policy Report":
                    saw_report_title = True
                if text == "Rules":
                    saw_rules_heading = True
                if text == "Referenced Objects" and cell.kind == "heading":
                    # The TOC also lists this heading; the real section always follows the rules.
                    if rules.rules or rules.in_rule:
                        rules.feed(text, page_no)  # closes the last rule
                        in_refs = True
                        saw_refs = True
                        continue
                if in_refs:
                    refs.feed_cell(cell)
                    continue
                # Rules mode: re-serialise the cell as 'Label value' + one line per extra value,
                # which is exactly the text layout the rule-block state machine expects.
                if cell.kind == "cont":
                    for v in cell.values:
                        rules.feed(v, page_no)
                elif cell.values:
                    rules.feed(f"{cell.label} {cell.values[0]}", page_no)
                    for v in cell.values[1:]:
                        rules.feed(v, page_no)
                else:
                    rules.feed(cell.label, page_no)
        raw_rules = rules.finish()
        objects = refs.finish()

        for i, t in enumerate(header_lines):
            if t == "Access Control Policy Report" and i + 1 < len(header_lines):
                policy_name = header_lines[i + 1]
            m = re.search(r"source with hostname\s+(\S+)", t)
            if m:
                hostname = m.group(1)
        if not saw_report_title and not raw_rules:
            raise NotAnFmcReport(
                "This PDF doesn't look like an FMC Access Control Policy report. Expected an "
                "'Access Control Policy Report' title and a 'Rules' section."
            )
        if not raw_rules:
            raise NotAnFmcReport(
                "This PDF doesn't look like an FMC Access Control Policy report. Expected a 'Rules' section."
            )
        warnings: list[ParseWarning] = []
        if not saw_refs:
            warnings.append(ParseWarning("FTD", None, "Referenced Objects",
                                         "No 'Referenced Objects' section found; named objects cannot be expanded"))
        return FtdPolicy(policy_name, hostname, page_count, raw_rules, objects, warnings,
                         has_rules_section=saw_rules_heading, has_referenced_objects=saw_refs)
