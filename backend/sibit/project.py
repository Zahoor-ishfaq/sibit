""".sibit project files: a zip containing JSON + parquet (spec 7).

    meta.json            summary, options, calibration, counts
    rows.parquet         one row per rule pair (table view)
    details.json         full per-pair detail (diff drawer)
    objects.json         object trees for both sides
    order_changes.json, warnings.json, unresolved.json, search.json
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import polars as pl

from .serialize import SCHEMA_VERSION

_JSON_PARTS = ("meta", "details", "objects", "order_changes", "warnings", "unresolved", "search")


def save_project(session: dict, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("sibit.json", json.dumps({"format": "sibit-project", "schema": SCHEMA_VERSION}))
        for part in _JSON_PARTS:
            z.writestr(f"{part}.json", json.dumps(session[part], ensure_ascii=False, separators=(",", ":")))
        buf = io.BytesIO()
        pl.DataFrame(session["rows"], infer_schema_length=None).write_parquet(buf)
        z.writestr("rows.parquet", buf.getvalue())
    tmp.replace(out)
    return out


def load_project(path_or_bytes: str | Path | bytes) -> dict:
    src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes
    try:
        z = zipfile.ZipFile(src)
    except zipfile.BadZipFile as e:
        raise ValueError("This file is not a Sibit project (.sibit).") from e
    with z:
        names = set(z.namelist())
        if "sibit.json" not in names:
            raise ValueError("This file is not a Sibit project (.sibit).")
        head = json.loads(z.read("sibit.json"))
        if head.get("schema", 0) > SCHEMA_VERSION:
            raise ValueError("This project was saved by a newer version of Sibit.")
        session = {part: json.loads(z.read(f"{part}.json")) for part in _JSON_PARTS}
        rows = pl.read_parquet(io.BytesIO(z.read("rows.parquet"))).to_dicts()
    session["rows"] = rows
    return session
