"""In-memory app state: uploads, sessions, settings, recent projects.

No database server: results live in memory and can be saved as .sibit files.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..hits.service import HitsStore
from ..jobs import Job, JobManager


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / "Sibit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir() -> Path:
    docs = Path.home() / "Documents"
    d = (docs if docs.is_dir() else Path.home()) / "Sibit"
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_SETTINGS = {
    "theme": "dark",
    "density": "comfortable",
    "numbering_default": "auto",
    "include_disabled": True,
    "ignore_comments": True,
    "port_overrides": {},
}


@dataclass
class Upload:
    id: str
    kind: str  # asa | ftd
    name: str
    size: int
    path: Path
    detect: dict


class AppState:
    def __init__(self, data_dir: Path | None = None, proj_dir: Path | None = None) -> None:
        self.data_dir = data_dir or app_data_dir()
        self.proj_dir = proj_dir or projects_dir()
        self.tmp = Path(tempfile.mkdtemp(prefix="sibit-"))
        self.uploads: dict[str, Upload] = {}
        self.sessions: dict[str, dict] = {}
        self.session_paths: dict[str, str] = {}  # sid -> saved .sibit path
        self._lock = threading.Lock()
        self.jobs = JobManager(self._store_job_session)
        self.hits = HitsStore()

    # ---------------------------------------------------------------- sessions
    def _store_job_session(self, job: Job, session: dict) -> str:
        return self.add_session(session)

    def add_session(self, session: dict) -> str:
        sid = session["meta"]["id"]
        with self._lock:
            self.sessions[sid] = session
            # Keep memory bounded: at most 4 sessions in memory.
            while len(self.sessions) > 4:
                oldest = next(iter(self.sessions))
                self.sessions.pop(oldest, None)
                self.session_paths.pop(oldest, None)
        return sid

    def get(self, sid: str) -> dict | None:
        return self.sessions.get(sid)

    # ----------------------------------------------------------------- uploads
    def new_upload(self, kind: str, name: str) -> tuple[str, Path]:
        uid = uuid.uuid4().hex[:12]
        if kind == "hits":
            ext = Path(name).suffix.lower()
            suffix = ext if ext in (".xlsx", ".xlsm", ".xlsb", ".xls", ".ods", ".csv", ".txt", ".log") else ".txt"
        else:
            suffix = ".pdf" if kind == "ftd" else ".cfg"
        return uid, self.tmp / f"{uid}{suffix}"

    def drop_upload(self, uid: str) -> None:
        up = self.uploads.pop(uid, None)
        if up is not None:
            try:
                up.path.unlink(missing_ok=True)
            except OSError:
                pass

    # ---------------------------------------------------------------- settings
    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    def load_settings(self) -> dict:
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}

    def save_settings(self, patch: dict) -> dict:
        cur = self.load_settings()
        cur.update({k: v for k, v in patch.items() if k in DEFAULT_SETTINGS})
        self.settings_file.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        return cur

    # ----------------------------------------------------------------- recent
    @property
    def recent_file(self) -> Path:
        return self.data_dir / "recent.json"

    def recent(self) -> list[dict]:
        try:
            items = json.loads(self.recent_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        return [i for i in items if Path(i.get("path", "")).is_file()][:12]

    def add_recent(self, entry: dict) -> None:
        items = [i for i in self.recent() if i.get("path") != entry["path"]]
        items.insert(0, entry)
        self.recent_file.write_text(json.dumps(items[:12], indent=2), encoding="utf-8")

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
