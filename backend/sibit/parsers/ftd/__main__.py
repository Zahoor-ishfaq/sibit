"""CLI: python -m sibit.parsers.ftd samples/after.pdf --summary"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import PdfFtdSource, parse_ftd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sibit.parsers.ftd", description="Parse an FMC Access Control Policy report PDF.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--summary", action="store_true", help="print a summary (default)")
    ap.add_argument("--rules", action="store_true", help="print every parsed rule")
    ap.add_argument("--objects", action="store_true", help="print Referenced Objects")
    ap.add_argument("--warnings", action="store_true", help="print every parse warning")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    t0 = time.perf_counter()

    def progress(step: str, d: dict) -> None:
        if step == "ftd_pages" and not args.json:
            print(f"\r  reading page {d['page']:,} of {d['pages']:,}", end="", file=sys.stderr, flush=True)

    res = parse_ftd(PdfFtdSource(str(args.pdf)), progress=progress)
    print(file=sys.stderr)
    elapsed = time.perf_counter() - t0
    s = res.summary() | {"seconds": round(elapsed, 2)}
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        print(f"Sibit FTD parser — {args.pdf.name}")
        print(f"  policy            {s['policy']}")
        print(f"  source hostname   {s['hostname']}")
        print(f"  pages             {s['pages']:,}")
        print(f"  rules             {s['rules']:,}  ({s['rules_disabled']} disabled)")
        print(f"  referenced objs   {s['referenced_objects']:,}  {s['objects_by_section']}")
        print(f"  unresolved refs   {s['unresolved']:,}")
        print(f"  name convention   {s['resolved_by_name_convention']:,}")
        print(f"  warnings          {s['warnings']:,}")
        print(f"  parsed in         {elapsed:.2f}s")
        print("  ACLs:")
        for acl, n in s["acls"].items():
            print(f"    {acl:<32} {n:>6,}")
    if args.rules:
        for r in res.rules:
            flag = "" if r.enabled else " (disabled)"
            print(f"{r.position:>5}:{r.key:<28} {r.action_text:<10} {','.join(r.src_refs)[:40]} -> "
                  f"{','.join(r.dst_refs)[:40]} [{', '.join(r.services.labels()[:6])}]{flag}")
    if args.objects:
        for o in res.objects.values():
            print(f"[{o.section}] {o.name}: {', '.join(o.values)}")
    if args.warnings:
        for w in res.warnings:
            print(f"page {w.line}: {w.message}: {w.text}")
        for u in res.unresolved:
            print(f"unresolved: {u.name} ({u.reason}) used by {len(u.used_by)} rule(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
