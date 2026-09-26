"""HTTP API. Bound to 127.0.0.1 only (see server.py)."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..compare import CompareOptions
from ..export import write_csv, write_excel, write_json
from ..filters import RowFilter, filter_ids
from ..parsers.asa import detect_asa
from ..parsers.ftd import looks_like_fmc_json, pdf_info
from ..project import load_project, save_project
from .state import AppState, Upload

router = APIRouter(prefix="/api")


def _state(request: Request) -> AppState:
    return request.app.state.sibit


def _session(request: Request, sid: str) -> dict:
    s = _state(request).get(sid)
    if s is None:
        raise HTTPException(404, "This comparison is no longer in memory. Open the saved project or run it again.")
    return s


def _csv(v: str | None) -> list[str]:
    return [x for x in (v or "").split(",") if x]


def _filter(status: str | None, severity: str | None, acl: str | None, flag: str | None,
            enabled: str | None, q: str | None) -> RowFilter:
    return RowFilter(_csv(status), _csv(severity), _csv(acl), _csv(flag), enabled or None, q or "")


# --------------------------------------------------------------------- basics
@router.get("/health")
def health() -> dict:
    from .. import __version__

    return {"ok": True, "app": "Sibit", "version": __version__}


@router.post("/shutdown")
def shutdown(request: Request) -> dict:
    server = getattr(request.app.state, "server", None)
    if server is not None:
        server.should_exit = True
    return {"ok": True}


# --------------------------------------------------------------------- uploads
def _detect_hits(path: Path) -> dict:
    from ..hits.reader import EXCEL_EXT, sheet_names

    try:
        if path.suffix.lower() in EXCEL_EXT:
            sheets = sheet_names(path)
            return {"ok": True, "sheets": sheets,
                    "label": f"Excel workbook, {len(sheets)} sheet{'s' if len(sheets) != 1 else ''}"}
        return {"ok": True, "sheets": [path.name], "label": "Text/CSV file"}
    except Exception:  # noqa: BLE001
        return {"ok": False, "label": None, "error": "This file could not be opened as Excel, CSV or text."}


def _detect_fmc_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "label": None, "error": "This JSON file could not be read."}
    if isinstance(data, dict):
        items = data.get("accessrules") or data.get("items") or []
        policy = (data.get("policy") or {}).get("name")
    else:
        items, policy = data, None
    n = len(items) if isinstance(items, list) else 0
    if not n:
        return {"ok": False, "label": None, "error": "This JSON export contains no access rules."}
    return {"ok": True, "pages": 0, "policy": policy, "hostname": None, "label": f"FMC REST API export, {n:,} rules"}


@router.post("/uploads")
def upload(request: Request, kind: str = Form(...), file: UploadFile = File(...)) -> dict:
    if kind not in ("asa", "ftd", "hits"):
        raise HTTPException(400, "kind must be 'asa', 'ftd' or 'hits'")
    st = _state(request)
    uid, path = st.new_upload(kind, file.filename or kind)
    with open(path, "wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    size = path.stat().st_size
    name = Path(file.filename or kind).name
    if kind == "hits":
        det = _detect_hits(path)
        st.uploads[uid] = Upload(uid, kind, name, size, path, det)
        return {"id": uid, "kind": kind, "name": name, "size": size, "detect": det}
    if kind == "asa":
        with open(path, "rb") as f:
            head = f.read(256 * 1024).decode("utf-8", errors="replace")
        det = detect_asa(head)
        if head.startswith("%PDF"):
            det = {"ok": False, "label": None, "error": "This is a PDF. Drop it in the FTD policy report zone."}
        elif not det["ok"]:
            det["error"] = "This file doesn't look like a Cisco ASA running config."
    else:
        with open(path, "rb") as f:
            head = f.read(4096)
        if not head.startswith(b"%PDF") and looks_like_fmc_json(head):
            det = _detect_fmc_json(path)
            st.uploads[uid] = Upload(uid, kind, name, size, path, det)
            return {"id": uid, "kind": kind, "name": name, "size": size, "detect": det}
        try:
            info = pdf_info(str(path))
            ok = info["ok"]
            det = {
                "ok": ok, "pages": info["pages"], "policy": info["policy"], "hostname": info["hostname"],
                "label": f"FMC Access Control Policy report, {info['pages']:,} pages" if ok else None,
            }
            if not ok:
                det["error"] = "This PDF doesn't look like an FMC Access Control Policy report."
        except Exception:  # noqa: BLE001
            det = {"ok": False, "label": None, "error": "This file is not a readable PDF."}
    st.uploads[uid] = Upload(uid, kind, name, size, path, det)
    return {"id": uid, "kind": kind, "name": name, "size": size, "detect": det}


@router.delete("/uploads/{uid}")
def delete_upload(request: Request, uid: str) -> dict:
    _state(request).drop_upload(uid)
    return {"ok": True}


# ------------------------------------------------------------------------ jobs
class JobRequest(BaseModel):
    asa_upload: str
    ftd_upload: str
    numbering: str = Field("auto", pattern="^(auto|ace_only|all_lines)$")
    include_disabled: bool = True
    ignore_comments: bool = True


@router.post("/jobs")
def start_job(request: Request, body: JobRequest) -> dict:
    st = _state(request)
    a, f = st.uploads.pop(body.asa_upload, None), st.uploads.pop(body.ftd_upload, None)
    if a is None or f is None:
        raise HTTPException(400, "Upload not found — please add the files again.")
    settings = st.load_settings()
    overrides = {str(k): int(v) for k, v in (settings.get("port_overrides") or {}).items()}
    job = st.jobs.start(a.path, f.path, a.name, f.name,
                        CompareOptions(body.numbering, body.include_disabled, body.ignore_comments), overrides)
    return job.snapshot()


@router.get("/jobs/{jid}")
def job_status(request: Request, jid: str) -> dict:
    job = _state(request).jobs.jobs.get(jid)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job.snapshot()


@router.get("/jobs/{jid}/events")
async def job_events(request: Request, jid: str) -> StreamingResponse:
    job = _state(request).jobs.jobs.get(jid)
    if job is None:
        raise HTTPException(404, "Job not found")

    async def gen():
        last = -1
        while True:
            if await request.is_disconnected():
                break
            snap = job.snapshot()
            if snap["version"] != last:
                last = snap["version"]
                yield f"data: {json.dumps(snap)}\n\n"
            if snap["state"] in ("done", "error", "cancelled"):
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/jobs/{jid}/cancel")
def cancel_job(request: Request, jid: str) -> dict:
    job = _state(request).jobs.jobs.get(jid)
    if job is None:
        raise HTTPException(404, "Job not found")
    job.cancel()
    return {"ok": True}


# -------------------------------------------------------------------- sessions
@router.get("/sessions")
def list_sessions(request: Request) -> list[dict]:
    st = _state(request)
    return [{"id": sid, "name": s["meta"]["name"], "created": s["meta"]["created"],
             "asa_name": s["meta"]["asa_name"], "ftd_name": s["meta"]["ftd_name"],
             "saved_path": st.session_paths.get(sid)} for sid, s in reversed(list(st.sessions.items()))]


@router.get("/sessions/{sid}/meta")
def session_meta(request: Request, sid: str) -> dict:
    s = _session(request, sid)
    acls = sorted({r["acl"] for r in s["rows"]})
    zones = sorted({r["zone"] for r in s["rows"] if r.get("zone")})
    flags = sorted({f for r in s["rows"] for f in r["flags"]})
    top = sorted((r for r in s["rows"] if r["severity"] in ("critical", "high")),
                 key=lambda r: ({"critical": 0, "high": 1}[r["severity"]], -len(r["flags"]), r["id"]))[:10]
    return s["meta"] | {"acls": acls, "zones": zones, "flag_types": flags, "top_risks": top,
                        "warning_count": len(s["warnings"]), "unresolved_count": len(s["unresolved"]),
                        "saved_path": _state(request).session_paths.get(sid)}


class RenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@router.patch("/sessions/{sid}")
def rename_session(request: Request, sid: str, body: RenameRequest) -> dict:
    s = _session(request, sid)
    s["meta"]["name"] = body.name.strip()
    return {"ok": True, "name": s["meta"]["name"]}


@router.get("/sessions/{sid}/rows")
def rows(request: Request, sid: str) -> list[dict]:
    return _session(request, sid)["rows"]


@router.get("/sessions/{sid}/rules/{pid}")
def rule_detail(request: Request, sid: str, pid: int) -> dict:
    s = _session(request, sid)
    if not 0 <= pid < len(s["details"]):
        raise HTTPException(404, "Rule not found")
    return s["details"][pid]


@router.get("/sessions/{sid}/search")
def search(request: Request, sid: str, status: str | None = None, severity: str | None = None,
           acl: str | None = None, flag: str | None = None, enabled: str | None = None,
           q: str | None = None) -> dict:
    s = _session(request, sid)
    ids = filter_ids(s, _filter(status, severity, acl, flag, enabled, q))
    return {"ids": ids, "total": len(s["rows"])}


@router.get("/sessions/{sid}/order")
def order(request: Request, sid: str) -> list[dict]:
    return _session(request, sid)["order_changes"]


@router.get("/sessions/{sid}/warnings")
def warnings(request: Request, sid: str) -> dict:
    s = _session(request, sid)
    return {"warnings": s["warnings"], "unresolved": s["unresolved"]}


# --------------------------------------------------------------------- objects
def _obj_index(s: dict) -> dict[tuple[str, str], dict]:
    idx = s.get("_obj_index")
    if idx is None:
        idx = s["_obj_index"] = {(o["side"], o["name"]): o for o in s["objects"]}
    return idx


def _obj_ranges(o: dict) -> list[tuple[int, int, int]]:
    from netaddr import IPNetwork, IPRange

    cached = o.get("_ranges")
    if cached is not None:
        return cached
    out = []
    for lab in o["expanded"]:
        try:
            if lab == "any":
                out.append((4, 0, 2**32 - 1))
            elif "-" in lab and lab.count(".") == 6:
                a, b = lab.split("-")
                r = IPRange(a, b)
                out.append((r.version, r.first, r.last))
            elif lab[:1].isdigit() or ":" in lab:
                n = IPNetwork(lab)
                out.append((n.version, n.first, n.last))
        except Exception:  # noqa: BLE001
            continue
    o["_ranges"] = out
    return out


@router.get("/sessions/{sid}/objects")
def objects(request: Request, sid: str, q: str | None = None, side: str | None = None,
            unresolved: bool = False, limit: int = Query(500, le=5000)) -> dict:
    s = _session(request, sid)
    items = s["objects"]
    if side in ("ASA", "FTD"):
        items = [o for o in items if o["side"] == side]
    if unresolved:
        items = [o for o in items if o["unresolved"]]
    if q:
        from netaddr import AddrFormatError, IPAddress

        ql = q.strip().lower()
        ip = None
        if re.fullmatch(r"[0-9a-fA-F:.]+", ql) and (ql.count(".") == 3 or ql.count(":") >= 2):
            try:
                ip = IPAddress(ql)
            except (AddrFormatError, ValueError):
                ip = None
        if ip is not None:
            v, n = ip.version, int(ip)
            items = [o for o in items if any(rv == v and a <= n <= b for rv, a, b in _obj_ranges(o))]
        else:
            items = [o for o in items if ql in o["name"].lower()
                     or any(ql in e.lower() for e in o["expanded"][:200])]
    total = len(items)
    items = sorted(items, key=lambda o: (o["side"], o["name"].lower()))[:limit]
    return {"total": total, "items": [
        {"side": o["side"], "name": o["name"], "kind": o["kind"], "expanded_count": len(o["expanded"]),
         "used_count": len(o["used_by"]), "unresolved": o["unresolved"]} for o in items]}


@router.get("/sessions/{sid}/object")
def object_detail(request: Request, sid: str, side: str, name: str) -> dict:
    s = _session(request, sid)
    o = _obj_index(s).get((side, name))
    if o is None:
        raise HTTPException(404, f"Object '{name}' not found on {side}")
    rows = s["rows"]
    used = [{"id": i, "key": rows[i]["key"], "status": rows[i]["status"], "severity": rows[i]["severity"]}
            for i in o["used_by"][:500]]
    idx = _obj_index(s)
    members = [m | {"exists": bool(m.get("ref")) and (side, m["ref"]) in idx} for m in o["members"]]
    return {k: v for k, v in o.items() if not k.startswith("_")} | {"used_by_rules": used, "members": members}


# ---------------------------------------------------------------------- export
@router.get("/sessions/{sid}/export")
def export(request: Request, background: BackgroundTasks, sid: str, format: str = "xlsx",
           filtered: bool = False, status: str | None = None, severity: str | None = None,
           acl: str | None = None, flag: str | None = None, enabled: str | None = None,
           q: str | None = None) -> FileResponse:
    s = _session(request, sid)
    ids = filter_ids(s, _filter(status, severity, acl, flag, enabled, q)) if filtered else None
    if format not in ("xlsx", "csv", "json"):
        raise HTTPException(400, "format must be xlsx, csv or json")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = re.sub(r"[^\w.-]+", "_", s["meta"]["name"]).strip("_")[:60] or "sibit"
    fname = f"{base}-{'filtered-' if filtered else ''}{stamp}.{format}"
    tmp = Path(tempfile.mkdtemp(prefix="sibit-export-")) / fname
    {"xlsx": write_excel, "csv": write_csv, "json": write_json}[format](s, tmp, ids)
    background.add_task(shutil.rmtree, tmp.parent, True)
    media = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "csv": "text/csv", "json": "application/json"}[format]
    return FileResponse(tmp, media_type=media, filename=fname)


# -------------------------------------------------------------------- projects
class SaveRequest(BaseModel):
    name: str | None = None


def _project_path(st: AppState, name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .") or "Sibit project"
    return st.proj_dir / f"{safe[:80]}.sibit"


@router.post("/sessions/{sid}/save")
def save(request: Request, sid: str, body: SaveRequest) -> dict:
    st = _state(request)
    s = _session(request, sid)
    if body.name:
        s["meta"]["name"] = body.name.strip()
    path = Path(st.session_paths.get(sid) or _project_path(st, s["meta"]["name"]))
    save_project(s, path)
    st.session_paths[sid] = str(path)
    m = s["meta"]
    st.add_recent({"path": str(path), "name": m["name"], "asa_name": m["asa_name"], "ftd_name": m["ftd_name"],
                   "saved": datetime.now().isoformat(timespec="seconds"), "total": m["counts"]["total"],
                   "critical": m["counts"]["severity"]["critical"]})
    return {"ok": True, "path": str(path)}


@router.get("/sessions/{sid}/project")
def download_project(request: Request, background: BackgroundTasks, sid: str) -> FileResponse:
    s = _session(request, sid)
    tmp = Path(tempfile.mkdtemp(prefix="sibit-proj-")) / (_project_path(_state(request), s["meta"]["name"]).name)
    save_project(s, tmp)
    background.add_task(shutil.rmtree, tmp.parent, True)
    return FileResponse(tmp, media_type="application/zip", filename=tmp.name)


@router.get("/projects/recent")
def recent(request: Request) -> list[dict]:
    return _state(request).recent()


class OpenRequest(BaseModel):
    path: str


def _open(st: AppState, session: dict, path: str | None) -> dict:
    session.pop("_obj_index", None)
    sid = st.add_session(session)
    if path:
        st.session_paths[sid] = path
        m = session["meta"]
        st.add_recent({"path": path, "name": m["name"], "asa_name": m["asa_name"], "ftd_name": m["ftd_name"],
                       "saved": datetime.now().isoformat(timespec="seconds"), "total": m["counts"]["total"],
                       "critical": m["counts"]["severity"]["critical"]})
    return {"session_id": sid, "name": session["meta"]["name"]}


@router.post("/projects/open")
def open_path(request: Request, body: OpenRequest) -> dict:
    st = _state(request)
    p = Path(body.path)
    if p.suffix.lower() != ".sibit" or not p.is_file():
        raise HTTPException(404, "Project file not found.")
    try:
        return _open(st, load_project(p), str(p))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/upload")
def open_upload(request: Request, file: UploadFile = File(...)) -> dict:
    try:
        return _open(_state(request), load_project(file.file.read()), None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# -------------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(request: Request) -> dict:
    return _state(request).load_settings()


class SettingsPatch(BaseModel):
    theme: str | None = Field(None, pattern="^(dark|light|system)$")
    density: str | None = Field(None, pattern="^(comfortable|compact)$")
    numbering_default: str | None = Field(None, pattern="^(auto|ace_only|all_lines)$")
    include_disabled: bool | None = None
    ignore_comments: bool | None = None
    port_overrides: dict[str, int] | None = None


@router.put("/settings")
def put_settings(request: Request, body: SettingsPatch) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "port_overrides" in patch:
        clean = {}
        for k, v in patch["port_overrides"].items():
            k = k.strip().lower()
            if not re.fullmatch(r"((tcp|udp)/)?[a-z0-9][a-z0-9-]*", k) or not 0 <= int(v) <= 65535:
                raise HTTPException(400, f"Invalid port override '{k}' = {v}")
            clean[k] = int(v)
        patch["port_overrides"] = clean
    return _state(request).save_settings(patch)
