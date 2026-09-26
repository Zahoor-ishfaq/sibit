"""CLI: python -m sibit.parsers.asa samples/before.cfg --summary"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import parse_asa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sibit.parsers.asa", description="Parse a Cisco ASA running config.")
    ap.add_argument("config", type=Path)
    ap.add_argument("--summary", action="store_true", help="print a summary (default)")
    ap.add_argument("--rules", action="store_true", help="print every parsed rule")
    ap.add_argument("--warnings", action="store_true", help="print every parse warning")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.perf_counter()
    res = parse_asa(args.config.read_text(encoding="utf-8", errors="replace"))
    elapsed = time.perf_counter() - t0
    summary = res.summary() | {"seconds": round(elapsed, 2)}

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Sibit ASA parser — {args.config.name}")
        print(f"  hostname          {summary['hostname']}")
        print(f"  version           {summary['version']}")
        print(f"  lines             {summary['lines']:,}")
        print(f"  rules (ACEs)      {summary['rules']:,}  ({summary['rules_inactive']} inactive)")
        print(f"  network objects   {summary['network_objects']:,}   groups {summary['network_groups']:,}")
        print(f"  service objects   {summary['service_objects']:,}   groups {summary['service_groups']:,}")
        print(f"  protocol groups   {summary['protocol_groups']:,}   icmp-type groups {summary['icmp_groups']:,}")
        print(f"  unresolved refs   {summary['unresolved']:,}")
        print(f"  warnings          {summary['warnings']:,}")
        print(f"  secret lines      {summary['secret_lines_removed']} removed")
        print(f"  parsed in         {elapsed:.2f}s")
        print("  ACLs:")
        for acl, n in summary["acls"].items():
            print(f"    {acl:<32} {n:>6,}  zone={res.zones.get(acl, '-')}")
    if args.rules:
        for r in res.rules:
            flag = "" if r.enabled else " (inactive)"
            print(f"{r.key:<28} {r.action:<6} {','.join(r.src_refs)} -> {','.join(r.dst_refs)} "
                  f"[{', '.join(r.services.labels()[:6])}]{flag}")
    if args.warnings:
        for w in res.warnings:
            print(f"line {w.line}: {w.message}: {w.text}")
        for u in res.unresolved:
            print(f"unresolved: {u.name} ({u.reason}) used by {len(u.used_by)} rule(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
