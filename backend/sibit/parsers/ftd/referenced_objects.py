"""'Referenced Objects' section parser (object groups, network and port objects).

The section is a table (Name | [Type] | Value | [Description]). Text extraction
alone cannot reliably tell a wrapped value from the next object's name, so the
parser uses each span's x position against the column header positions. If no
header row is found, the leftmost x in the subsection is taken as the Name
column and the first token on such a line is the name.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .pdf_reader import PdfLine
from .values import split_values

SUBSECTIONS: dict[str, str] = {
    "Object Groups": "group",
    "Network Object Groups": "network",
    "Port Object Groups": "port",
    "Network Objects": "network",
    "Networks": "network",
    "Network": "network",
    "Port Objects": "port",
    "Ports": "port",
    "Port": "port",
    "URL Objects": "other",
    "URLs": "other",
    "URL": "other",
    "VLAN Tags": "other",
    "VLAN Tag": "other",
    "Security Zones": "other",
    "Zones": "other",
    "Interface Objects": "other",
    "Applications": "other",
    "Geolocation": "other",
    "Variable Sets": "other",
    "Time Ranges": "other",
}
_VALUE_HEADERS = {"value", "values", "contents", "members", "objects", "entries", "network", "port"}
_TOL = 4.0


@dataclass
class FtdObject:
    name: str
    section: str  # network | port | group | other
    values: list[str] = field(default_factory=list)
    type: str | None = None
    page: int = 0


class ReferencedObjectsParser:
    def __init__(self) -> None:
        self.objects: dict[str, FtdObject] = {}
        self.section = "group"
        self._cols: list[tuple[str, float]] | None = None  # sorted (kind, x)
        self._name_x: float | None = None
        self._cur: FtdObject | None = None
        self._cur_has_value_row = False

    def _start_section(self, kind: str) -> None:
        self._flush()
        self.section = kind
        self._cols = None
        self._name_x = None

    def _flush(self) -> None:
        if self._cur is not None:
            existing = self.objects.get(self._cur.name)
            if existing is None or (not existing.values and self._cur.values):
                self.objects[self._cur.name] = self._cur
        self._cur = None
        self._cur_has_value_row = False

    def _column_of(self, x: float) -> str:
        assert self._cols is not None
        kind = "name"
        for k, cx in self._cols:
            if x + _TOL >= cx:
                kind = k
        return kind

    def feed(self, line: PdfLine) -> None:
        text = line.text
        if len(line.spans) == 1 and text in SUBSECTIONS:
            self._start_section(SUBSECTIONS[text])
            return
        first = line.spans[0].text.split()[0] if line.spans and line.spans[0].text else ""
        # Column header row: 'Name  Type  Value  Description'
        if first == "Name":
            cols: list[tuple[str, float]] = [("name", line.spans[0].x0)]
            words = [(s.x0, s.text) for s in line.spans]
            if len(words) == 1:
                # Header rendered as a single span: nothing positional to learn.
                parts = text.split()
                if len(parts) > 1 and all(p.lower() in _VALUE_HEADERS | {"name", "type", "description"} for p in parts):
                    self._flush()
                    self._cols = None
                    self._name_x = line.spans[0].x0
                    return
            else:
                for x, w in words[1:]:
                    lw = w.strip().lower()
                    if lw in _VALUE_HEADERS:
                        cols.append(("value", x))
                    elif lw == "type":
                        cols.append(("type", x))
                    elif lw == "description":
                        cols.append(("desc", x))
                    else:
                        cols.append(("other", x))
                if any(k == "value" for k, _ in cols):
                    self._flush()
                    self._cols = sorted(cols, key=lambda c: c[1])
                    return
        if self._cols is not None:
            self._feed_positional(line)
        else:
            self._feed_heuristic(line)

    def _feed_positional(self, line: PdfLine) -> None:
        name_parts, values, typ = [], [], None
        for s in line.spans:
            col = self._column_of(s.x0)
            if col == "name":
                name_parts.append(s.text)
            elif col == "value":
                values.extend(split_values(s.text))
            elif col == "type":
                typ = s.text
        if name_parts:
            name = " ".join(name_parts).strip()
            if self._cur is not None and not self._cur_has_value_row and not values and typ is None:
                # A long name wrapped onto a second line.
                self._cur.name += name
                return
            self._flush()
            self._cur = FtdObject(name, self.section, [], typ, line.page)
        if self._cur is None:
            return
        if typ and not self._cur.type:
            self._cur.type = typ
        if values:
            self._cur.values.extend(values)
            self._cur_has_value_row = True

    def _feed_heuristic(self, line: PdfLine) -> None:
        x = line.spans[0].x0
        if self._name_x is None or x < self._name_x - _TOL:
            self._name_x = x
        text = line.text
        if abs(x - self._name_x) <= _TOL:
            parts = text.split(None, 1)
            self._flush()
            self._cur = FtdObject(parts[0], self.section, [], None, line.page)
            if len(parts) > 1:
                self._cur.values.extend(split_values(parts[1]))
        elif self._cur is not None:
            self._cur.values.extend(split_values(text))

    def feed_cell(self, cell) -> None:
        """Cell-based input (see pdf_reader.page_cells): name + its full value list."""
        if cell.kind == "heading":
            kind = SUBSECTIONS.get(cell.label)
            if kind is not None:
                self._start_section(kind)
            return
        if cell.kind == "cont":
            if self._cur is not None:
                for v in cell.values:
                    self._cur.values.extend(split_values(v))
            return
        if cell.label in SUBSECTIONS and not cell.values:
            self._start_section(SUBSECTIONS[cell.label])
            return
        if cell.label == "Name" and any(v.split()[0] in ("Value", "Type") for v in cell.values if v):
            return  # optional column header row
        self._flush()
        self._cur = FtdObject(cell.label, self.section, [], None, cell.page)
        for v in cell.values:
            self._cur.values.extend(split_values(v))
        self._cur_has_value_row = bool(cell.values)

    def finish(self) -> dict[str, FtdObject]:
        self._flush()
        return self.objects
