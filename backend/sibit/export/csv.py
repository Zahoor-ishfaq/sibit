"""CSV export (polars)."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from .excel import diff_text


def rules_frame(session: dict, ids: list[int] | None = None) -> pl.DataFrame:
    details = session["details"]
    if ids is not None:
        keep = set(ids)
        details = [d for d in details if d["id"] in keep]
    recs = []
    for d in details:
        a, f, df = d.get("asa"), d.get("ftd"), d.get("diffs", {})

        def g(r, k, sep="; "):
            if r is None:
                return None
            v = r.get(k)
            return sep.join(v) if isinstance(v, list) else v

        recs.append({
            "id": d["id"], "status": d["status"], "severity": d["severity"], "key": d["key"], "acl": d["acl"],
            "matched_by": d.get("matched_by"), "flags": ", ".join(fl["code"] for fl in d["flags"]),
            "asa_key": g(a, "key"), "asa_line": g(a, "line_no"), "asa_action": g(a, "action"),
            "asa_enabled": g(a, "enabled"), "asa_source": g(a, "src_refs"), "asa_destination": g(a, "dst_refs"),
            "asa_services": g(a, "svc_refs"), "asa_source_expanded": g(a, "src"),
            "asa_destination_expanded": g(a, "dst"), "asa_services_expanded": g(a, "services"),
            "asa_log": g(a, "log"), "asa_comment": g(a, "comment"),
            "ftd_position": g(f, "position"), "ftd_name": g(f, "key"), "ftd_action": g(f, "action_text"),
            "ftd_enabled": g(f, "enabled"), "ftd_source": g(f, "src_refs"), "ftd_destination": g(f, "dst_refs"),
            "ftd_services": g(f, "svc_refs"), "ftd_source_expanded": g(f, "src"),
            "ftd_destination_expanded": g(f, "dst"), "ftd_services_expanded": g(f, "services"),
            "ftd_log": g(f, "log"), "ftd_comment": g(f, "comment"),
            "source_diff": diff_text(df.get("src"), a, f, "src") if a and f else "",
            "destination_diff": diff_text(df.get("dst"), a, f, "dst") if a and f else "",
            "services_diff": diff_text(df.get("services"), a, f, "services") if a and f else "",
            "explanation": d["explanation"],
        })
    schema_overrides = {"asa_line": pl.Int64, "ftd_position": pl.Int64, "asa_enabled": pl.Boolean,
                        "ftd_enabled": pl.Boolean, "asa_log": pl.Boolean, "ftd_log": pl.Boolean}
    return pl.DataFrame(recs, schema_overrides=schema_overrides, infer_schema_length=None)


def write_csv(session: dict, path: str | Path, ids: list[int] | None = None) -> Path:
    out = Path(path)
    # UTF-8 with BOM so Excel on Windows opens it with the right encoding.
    data = rules_frame(session, ids).write_csv()
    out.write_bytes(b"\xef\xbb\xbf" + data.encode("utf-8"))
    return out
