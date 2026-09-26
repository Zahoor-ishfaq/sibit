"""Background comparison jobs with progress events (consumed via Server-Sent Events).

Parsing runs in a worker thread so the API (and the UI) never freeze. Uploaded
inputs are deleted as soon as the job finishes — only the comparison result
is kept in memory.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .compare import CompareOptions
from .parsers.common import Cancelled
from .parsers.ftd import NotAnFmcReport

STEPS = [
    ("asa", "Reading ASA config"),
    ("objects", "Expanding objects"),
    ("pdf", "Reading PDF"),
    ("match", "Matching rules"),
    ("compare", "Comparing"),
    ("done", "Done"),
]
_STEP_OF = {
    "asa_read": "asa", "asa_objects": "asa", "asa_rules": "objects", "asa_done": "objects",
    "ftd_pages": "pdf", "ftd_done": "pdf", "matching": "match", "comparing": "compare", "done": "done",
}


@dataclass
class Job:
    id: str
    asa_path: Path
    ftd_path: Path
    asa_name: str
    ftd_name: str
    options: CompareOptions
    port_overrides: dict[str, int]
    state: str = "queued"  # queued | running | done | error | cancelled
    step: str = "asa"
    counters: dict = field(default_factory=dict)
    error: str | None = None
    session_id: str | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    version: int = 0  # bumped on every change; SSE streams poll it
    _cancel: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "state": self.state, "step": self.step, "counters": dict(self.counters),
                "error": self.error, "session_id": self.session_id,
                "elapsed": round((self.finished or time.time()) - self.started, 1),
                "steps": [{"id": s, "label": label} for s, label in STEPS], "version": self.version,
            }

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _update(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)
            if self.state in ("done", "error", "cancelled") and self.finished is None:
                self.finished = time.time()
            self.version += 1

    def progress(self, step: str, detail: dict) -> None:
        with self._lock:
            self.step = _STEP_OF.get(step, self.step)
            c = self.counters
            if step == "asa_read":
                c["asa_lines"] = detail.get("lines", 0)
            elif step == "asa_rules":
                c["asa_rules"] = detail.get("rules", 0)
            elif step == "asa_done":
                c["asa_rules"] = detail.get("rules", 0)
                c["objects_resolved"] = detail.get("objects", 0) + detail.get("groups", 0)
            elif step == "ftd_pages":
                c["page"], c["pages"] = detail.get("page", 0), detail.get("pages", 0)
                c["ftd_rules"] = detail.get("rules", 0)
            elif step == "ftd_done":
                c["ftd_rules"] = detail.get("rules", 0)
                c["ftd_objects"] = detail.get("objects", 0)
            elif step == "comparing":
                c["pairs"] = detail.get("pairs", c.get("pairs", 0))
                c["compared"] = detail.get("done", 0)
            self.version += 1


class JobManager:
    def __init__(self, on_done: Callable[[Job, dict], str]) -> None:
        """``on_done(job, session) -> session_id`` stores a finished session."""
        self.jobs: dict[str, Job] = {}
        self._on_done = on_done
        # One comparison at a time keeps memory bounded on a 16 GB laptop.
        self._sem = threading.Semaphore(1)

    def start(self, asa_path: Path, ftd_path: Path, asa_name: str, ftd_name: str,
              options: CompareOptions, port_overrides: dict[str, int]) -> Job:
        job = Job(uuid.uuid4().hex[:12], asa_path, ftd_path, asa_name, ftd_name, options, port_overrides)
        self.jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), name=f"sibit-job-{job.id}", daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        from .pipeline import run
        from .serialize import build_session

        with self._sem:
            if job.cancelled:
                job._update(state="cancelled")
                self._cleanup(job)
                return
            job._update(state="running")
            try:
                rr = run(job.asa_path, job.ftd_path, job.options, port_overrides=job.port_overrides,
                         progress=job.progress, is_cancelled=lambda: job.cancelled,
                         asa_name=job.asa_name, ftd_name=job.ftd_name)
                session = build_session(rr)
                del rr
                sid = self._on_done(job, session)
                job._update(state="done", step="done", session_id=sid)
            except Cancelled:
                job._update(state="cancelled")
            except NotAnFmcReport as e:
                job._update(state="error", error=str(e))
            except UnicodeDecodeError:
                job._update(state="error", error="The ASA config could not be read as text.")
            except Exception as e:  # noqa: BLE001 - report, never crash the server
                traceback.print_exc()
                job._update(state="error", error=f"Comparison failed: {type(e).__name__}: {e}")
            finally:
                self._cleanup(job)

    @staticmethod
    def _cleanup(job: Job) -> None:
        for p in (job.asa_path, job.ftd_path):
            try:
                os.remove(p)
            except OSError:
                pass
