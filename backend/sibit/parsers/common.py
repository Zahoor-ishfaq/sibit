"""Types shared by both parsers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# progress(step, detail_dict) — called from worker threads.
ProgressFn = Callable[[str, dict], None]


class Cancelled(Exception):
    """Raised inside a parser when the job was cancelled."""


@dataclass
class ParseWarning:
    source: str  # "ASA" | "FTD"
    line: int | None  # config line number (ASA) or page number (FTD)
    text: str  # offending text (never contains secrets — filtered before parsing)
    message: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class UnresolvedRef:
    side: str
    name: str
    reason: str
    used_by: list[str]

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def noop_progress(step: str, detail: dict) -> None:  # pragma: no cover
    pass
