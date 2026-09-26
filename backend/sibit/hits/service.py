"""Hit-count analysis as a background job + in-memory results with server-side paging.

Results can hold millions of rules, so the UI never downloads them all: it asks
for pages of a filtered/sorted view, and filtered views are cached.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..parsers.common import Cancelled
from .analyzer import GARBAGE, IN_USE, NO_DATA, HitResult, analyze

VERDICTS = (GARBAGE, IN_USE, NO_DATA)


@dataclass
class HitsJob:
    """Same snapshot/cancel interface as comparison jobs, so /api/jobs/{id}/events serves both."""

    id: str
    path: Path
    file_name: str
    state: str = "queued"
    step: str = "read"
    counters: dict = field(default_factory=dict)
    error: str | None = None
    session_id: str | None = None  # the hits result id
    started: float = field(default_factory=time.time)
    finished: float | None = None
    version: int = 0
    kind: str = "hits"
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict:
        with self._lock:
            return {"id": self.id, "kind": self.kind, "state": self.state, "step": self.step,
                    "counters": dict(self.counters), "error": self.error, "session_id": self.session_id,
                    "elapsed": round((self.finished or time.time()) - self.started, 1),
                    "steps": [{"id": "read", "label": "Reading rows"}, {"id": "done", "label": "Done"}],
                    "version": self.version}

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def update(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)
            if self.state in ("done", "error", "cancelled") and self.finished is None:
                self.finished = time.time()
            self.version += 1

    def progress(self, step: str, d: dict) -> None:
        with self._lock:
            self.counters.update(rows=d.get("rows", 0), rules=d.get("rules", 0))
            if "sheet" in d:
                self.counters["sheet"] = d["sheet"]
            self.version += 1


class HitsStore:
    def __init__(self, max_results: int = 2) -> None:
        self.results: dict[str, HitResult] = {}
        self._views: dict[tuple, list[int]] = {}
        self._search: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._sem = threading.Semaphore(1)
        self.max_results = max_results

    # ---------------------------------------------------------------- jobs
    def start(self, jobs: dict, path: Path, file_name: str) -> HitsJob:
        job = HitsJob(uuid.uuid4().hex[:12], path, file_name)
        jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), name=f"sibit-hits-{job.id}", daemon=True).start()
        return job

    def _run(self, job: HitsJob) -> None:
        with self._sem:
            job.update(state="running")
            try:
                res = analyze(job.path, job.file_name, progress=job.progress, is_cancelled=lambda: job.cancelled)
                hid = uuid.uuid4().hex[:12]
                with self._lock:
                    self.results[hid] = res
                    while len(self.results) > self.max_results:
                        old = next(iter(self.results))
                        self.results.pop(old)
                        self._search.pop(old, None)
                        self._views = {k: v for k, v in self._views.items() if k[0] != old}
                job.update(state="done", step="done", session_id=hid)
            except Cancelled:
                job.update(state="cancelled")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                job.update(state="error", error=f"Could not read this file: {type(e).__name__}: {e}")
            finally:
                try:
                    os.remove(job.path)
                except OSError:
                    pass

    # --------------------------------------------------------------- views
    def get(self, hid: str) -> HitResult | None:
        return self.results.get(hid)

    def view(self, hid: str, verdict: str = "", q: str = "", sort: str = "") -> list[int]:
        res = self.results[hid]
        key = (hid, verdict, q.strip().lower(), sort)
        with self._lock:
            hit = self._views.get(key)
        if hit is not None:
            return hit
        wanted = set(v for v in verdict.split(",") if v in VERDICTS)
        ql = q.strip().lower()
        if ql and hid not in self._search:
            self._search[hid] = [
                f"{r.name} {r.rule_id or ''} {r.acl or ''} {res.sheets[r.first_sheet]}".lower() for r in res.rules
            ]
        blob = self._search.get(hid)
        ids = [i for i, r in enumerate(res.rules)
               if (not wanted or r.verdict in wanted) and (not ql or ql in blob[i])]
        if sort == "hits":
            ids.sort(key=lambda i: -res.rules[i].total_hits)
        elif sort == "hits_asc":
            ids.sort(key=lambda i: res.rules[i].total_hits)
        elif sort == "name":
            ids.sort(key=lambda i: res.rules[i].name.lower())
        elif sort == "lines":
            ids.sort(key=lambda i: -len(res.rules[i].lines))
        with self._lock:
            if len(self._views) > 24:
                self._views.clear()
            self._views[key] = ids
        return ids


def rule_row(res: HitResult, i: int) -> dict:
    r = res.rules[i]
    return {
        "id": i, "verdict": r.verdict, "name": r.name, "named": r.named, "rule_id": r.rule_id, "acl": r.acl, "acl_line": r.acl_line,
        "action": r.action, "lines": len(r.lines), "total_hits": r.total_hits, "hit_values": r.hit_values,
        "elements": r.elements, "zero_elements": r.zero_elements,
        "sheet": res.sheets[r.first_sheet] if res.sheets else "", "row": r.first_row,
    }


def meta(res: HitResult, hid: str) -> dict:
    c = res.counts()
    by_sheet: dict[str, dict] = {s: {GARBAGE: 0, IN_USE: 0, NO_DATA: 0} for s in res.sheets}
    for r in res.rules:
        by_sheet[res.sheets[r.first_sheet]][r.verdict] += 1
    return {
        "id": hid, "file_name": res.file_name, "sheets": res.sheets, "rows_read": res.rows_read,
        "rows_used": res.rows_used, "lines": len(res.lines), "rules": len(res.rules), "counts": c,
        "by_sheet": [{"sheet": s, **v} for s, v in by_sheet.items()], "seconds": res.seconds,
        "warning_count": len(res.warnings),
        "partial": sum(1 for r in res.rules if r.verdict == IN_USE and r.zero_elements),
        "unnamed": sum(1 for r in res.rules if not r.named),
    }
