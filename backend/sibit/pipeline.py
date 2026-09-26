"""End-to-end run: parse ASA → parse FTD → compare. Used by the CLI and the API."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .compare import Comparison, CompareOptions, compare
from .parsers.asa import AsaResult, parse_asa
from .parsers.common import ParseWarning, ProgressFn
from .parsers.ftd import FtdResult, FtdSource, open_source, parse_ftd
from .ports import PortResolver


@dataclass
class RunResult:
    asa: AsaResult
    ftd: FtdResult
    comparison: Comparison
    asa_name: str
    ftd_name: str
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    seconds: dict[str, float] = field(default_factory=dict)


def asa_object_names(asa: AsaResult) -> frozenset[str]:
    d = asa.defs
    return frozenset(
        list(d.net_objects) + list(d.net_groups) + list(d.svc_objects) + list(d.svc_groups)
        + list(d.proto_groups) + list(d.icmp_groups)
    )


def run(
    asa_path: str | Path,
    ftd: str | Path | FtdSource,
    options: CompareOptions | None = None,
    *,
    port_overrides: dict[str, int] | None = None,
    progress: ProgressFn | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    asa_name: str | None = None,
    ftd_name: str | None = None,
) -> RunResult:
    options = options or CompareOptions()
    ports = PortResolver(port_overrides)
    timings: dict[str, float] = {}

    t = time.perf_counter()
    text = Path(asa_path).read_text(encoding="utf-8", errors="replace")
    asa = parse_asa(text, ports=ports, progress=progress, is_cancelled=is_cancelled)
    del text
    timings["asa"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    source = ftd if isinstance(ftd, FtdSource) else open_source(str(ftd))
    ftd_res = parse_ftd(source, progress=progress, is_cancelled=is_cancelled)
    timings["ftd"] = round(time.perf_counter() - t, 2)

    # ACLs not applied with access-group (e.g. 'sfr' for a class-map, VPN or NAT ACLs)
    # are not traffic-filtering policy: skip them unless FTD has rules for them.
    ftd_acls = {r.acl for r in ftd_res.rules}
    unbound = sorted({r.acl for r in asa.rules if r.acl not in asa.zones and r.acl not in ftd_acls})
    asa_rules = [r for r in asa.rules if r.acl not in unbound]
    for acl in unbound:
        n = sum(1 for r in asa.rules if r.acl == acl)
        asa.warnings.append(ParseWarning("ASA", None, f"access-list {acl} ({n} rule(s))",
                                         "ACL is not applied with access-group and has no FTD rules; not compared"))

    t = time.perf_counter()
    comp = compare(
        asa_rules,
        ftd_res.rules,
        options,
        warnings=asa.warnings + ftd_res.warnings,
        asa_object_names=asa_object_names(asa),
        unresolved=asa.unresolved + ftd_res.unresolved,
        progress=progress,
        is_cancelled=is_cancelled,
    )
    timings["compare"] = round(time.perf_counter() - t, 2)
    if progress:
        progress("done", {"pairs": len(comp.pairs)})
    return RunResult(
        asa=asa,
        ftd=ftd_res,
        comparison=comp,
        asa_name=asa_name or Path(asa_path).name,
        ftd_name=ftd_name or (Path(str(ftd)).name if not isinstance(ftd, FtdSource) else "FMC"),
        seconds=timings,
    )
