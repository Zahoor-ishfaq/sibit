"""FTD rule block parsing (spec 3.1 / 3.2).

A rule starts with '<pos>:<name>[(disable)]' immediately followed by an
'Action ...' line. Field values start after the label (same line or next line)
and continue until the next known label. Page-number noise has already been
removed by the reader, so a page break inside a value list is invisible here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

RULE_HEADER = re.compile(r"^(\d+):(.+?)(\(disable\))?$")

# Fixed field labels (spec 3.1) plus a few that newer FMC versions emit.
FIELD_LABELS = [
    "Action",
    "Source Zones",
    "Destination Zones",
    "Source Tunnels",
    "Source Networks",
    "Original Client Networks",
    "Destination Networks",
    "Source Dynamic Attributes",
    "Destination Dynamic Attributes",
    "Safe Search",
    "Youtube EDU",
    "VLAN Tags",
    "Users",
    "Applications",
    "Application Filters",
    "Source Ports",
    "Destination Ports",
    "Source ISE Metadata",
    "Destination ISE Metadata",
    "Security Group Tag",
    "Time Range",
    "URLs",
    "Intrusion Policy",
    "Variable Set",
    "File Policy",
    "Log at Beginning of Connection",
    "Log at End of Connection",
    "Log File Events",
    "Send Events to Defense Center",
    "Send using specific syslog alert",
    "Send using specific SNMP alert",
    "Comments",
]
# Longest first so 'Source ISE Metadata' wins over shorter prefixes.
_LABELS_SORTED = sorted(FIELD_LABELS, key=len, reverse=True)
_LABEL_RE = re.compile(r"^(" + "|".join(re.escape(label) for label in _LABELS_SORTED) + r")(?:\s+(.*))?$")

# Section headings that end the Rules section / close the current rule.
SECTION_HEADINGS = {
    "Advanced Settings",
    "Logging Policy",
    "Referenced Objects",
    "Policy Information",
    "Device Targets",
    "HTTP Block Response",
    "Security Intelligence",
    "Default Action",
    "Rules",
    "Table of Contents",
}
# Rule-category separator rows ('Mandatory', 'Default', 'Mandatory - Policy (1-20)').
_CATEGORY_RE = re.compile(r"^(Mandatory|Default)(\s+-\s+.*)?$")


def match_label(line: str) -> tuple[str, str] | None:
    m = _LABEL_RE.match(line)
    if not m:
        return None
    return m.group(1), (m.group(2) or "").strip()


@dataclass
class RawFtdRule:
    position: int
    name: str
    disabled: bool
    page: int
    fields: dict[str, list[str]] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)

    def value(self, label: str) -> list[str]:
        return self.fields.get(label, [])

    def text(self, label: str, sep: str = " ") -> str:
        return sep.join(self.value(label)).strip()


class RuleBlockParser:
    """Feed lines one at a time; completed rules accumulate in ``rules``."""

    def __init__(self) -> None:
        self.rules: list[RawFtdRule] = []
        self._cur: RawFtdRule | None = None
        self._label: str | None = None
        self._pending_header: tuple[str, int] | None = None
        self.section: str | None = None

    @property
    def in_rule(self) -> bool:
        return self._cur is not None

    def _close(self) -> None:
        if self._cur is not None:
            self.rules.append(self._cur)
        self._cur = None
        self._label = None

    def feed(self, text: str, page: int) -> None:
        # A candidate header is confirmed only if the next line is 'Action ...'.
        if self._pending_header is not None:
            htext, hpage = self._pending_header
            self._pending_header = None
            lab = match_label(text)
            if lab and lab[0] == "Action":
                m = RULE_HEADER.match(htext)
                assert m is not None
                self._close()
                self._cur = RawFtdRule(int(m.group(1)), m.group(2).strip(), bool(m.group(3)), hpage)
                self._cur.lines.append(htext)
            elif self._cur is not None:
                self._cur.lines.append(htext)
                self._append_value(htext)
        if RULE_HEADER.match(text) and not match_label(text):
            self._pending_header = (text, page)
            return
        if text in SECTION_HEADINGS or _CATEGORY_RE.match(text):
            self._close()
            if text in SECTION_HEADINGS:
                self.section = text
            return
        if self._cur is None:
            return
        self._cur.lines.append(text)
        lab = match_label(text)
        if lab:
            label, val = lab
            self._label = label
            vals = self._cur.fields.setdefault(label, [])
            if val:
                vals.append(val)
            return
        self._append_value(text)

    def _append_value(self, text: str) -> None:
        if self._cur is None or self._label is None:
            return
        self._cur.fields.setdefault(self._label, []).append(text)

    def finish(self) -> list[RawFtdRule]:
        if self._pending_header is not None:
            if self._cur is not None:
                self._cur.lines.append(self._pending_header[0])
                self._append_value(self._pending_header[0])
            self._pending_header = None
        self._close()
        return self.rules
