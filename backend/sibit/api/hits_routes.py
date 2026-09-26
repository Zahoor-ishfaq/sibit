"""Hit-count analysis API: start a job, page through results, export."""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..hits.export import write_hits_csv, write_hits_excel
from ..hits.service import meta, rule_row
from .state import AppState

router = APIRouter(prefix="/api/hits")


def _state(request: Request) -> AppState:
    return request.app.state.sibit


def _res(request: Request, hid: str):
    res = _state(request).hits.get(hid)
    if res is None:
        raise HTTPException(404, "This analysis is no longer in memory. Please upload the file again.")
    return res


class HitsJobRequest(BaseModel):
    upload: str


@router.post("/jobs")
def start(request: Request, body: HitsJobRequest) -> dict:
    st = _state(request)
    up = st.uploads.pop(body.upload, None)
    if up is None or up.kind != "hits":
        raise HTTPException(400, "Upload not found — please add the file again.")
    return st.hits.start(st.jobs.jobs, up.path, up.name).snapshot()


@router.get("/{hid}/meta")
def get_meta(request: Request, hid: str) -> dict:
    return meta(_res(request, hid), hid)


@router.get("/{hid}/rules")
def rules(request: Request, hid: str, verdict: str = "", q: str = "", sort: str = "",
          offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=2000)) -> dict:
    res = _res(request, hid)
    ids = _state(request).hits.view(hid, verdict, q, sort)
    return {"total": len(ids), "offset": offset, "rows": [rule_row(res, i) for i in ids[offset:offset + limit]]}


@router.get("/{hid}/rules/{rid}")
def rule(request: Request, hid: str, rid: int) -> dict:
    res = _res(request, hid)
    if not 0 <= rid < len(res.rules):
        raise HTTPException(404, "Rule not found")
    r = res.rules[rid]
    lines = [res.line(i) | {"sheet": res.sheets[res.lines.sheet[i]]} for i in r.lines[:5000]]
    return rule_row(res, rid) | {"line_items": lines, "truncated": len(r.lines) > 5000}


@router.get("/{hid}/warnings")
def warnings(request: Request, hid: str, limit: int = Query(1000, le=20000)) -> dict:
    res = _res(request, hid)
    return {"total": len(res.warnings), "items": [w.__dict__ for w in res.warnings[:limit]]}


@router.get("/{hid}/export")
def export(request: Request, background: BackgroundTasks, hid: str, format: str = "xlsx",
           verdict: str = "", q: str = "") -> FileResponse:
    res = _res(request, hid)
    if format not in ("xlsx", "csv"):
        raise HTTPException(400, "format must be xlsx or csv")
    ids = _state(request).hits.view(hid, verdict, q, "") if (verdict or q) else None
    base = re.sub(r"[^\w.-]+", "_", Path(res.file_name).stem)[:50] or "hits"
    tag = "-" + verdict.lower().replace(",", "-") if verdict else ""
    fname = f"{base}-hit-analysis{tag}-{datetime.now():%Y%m%d-%H%M}.{format}"
    tmp = Path(tempfile.mkdtemp(prefix="sibit-hits-")) / fname
    (write_hits_excel if format == "xlsx" else write_hits_csv)(res, tmp, ids)
    background.add_task(shutil.rmtree, tmp.parent, True)
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if format == "xlsx" else "text/csv"
    return FileResponse(tmp, media_type=media, filename=fname)
