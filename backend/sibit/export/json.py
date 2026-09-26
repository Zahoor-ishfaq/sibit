"""JSON export."""
from __future__ import annotations

import json
from pathlib import Path


def write_json(session: dict, path: str | Path, ids: list[int] | None = None) -> Path:
    keep = set(ids) if ids is not None else None
    doc = {
        "generator": "Sibit",
        "meta": session["meta"],
        "rules": [d for d in session["details"] if keep is None or d["id"] in keep],
        "order_changes": session["order_changes"],
        "unresolved": session["unresolved"],
        "warnings": session["warnings"],
    }
    out = Path(path)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return out
