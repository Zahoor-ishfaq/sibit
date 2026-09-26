"""Sibit entry point.

    python -m sibit                          start the local app and open the browser
    python -m sibit compare a.cfg b.pdf -o report.xlsx
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _compare(argv: list[str]) -> int:
    from .compare import CompareOptions
    from .export import write_csv, write_excel, write_json
    from .parsers.ftd import NotAnFmcReport
    from .pipeline import run
    from .serialize import build_session

    ap = argparse.ArgumentParser(prog="python -m sibit compare", description="Compare an ASA config with an FTD policy report.")
    ap.add_argument("asa", type=Path, help="ASA running config (.cfg/.txt)")
    ap.add_argument("ftd", type=Path, help="FMC Access Control Policy report (.pdf)")
    ap.add_argument("-o", "--output", type=Path, default=Path("sibit-report.xlsx"),
                    help="report file: .xlsx, .csv or .json (default sibit-report.xlsx)")
    ap.add_argument("--numbering", choices=["auto", "ace_only", "all_lines"], default="auto")
    ap.add_argument("--exclude-disabled", action="store_true", help="skip rules disabled on both sides")
    ap.add_argument("--compare-comments", action="store_true", help="flag comment differences (ignored by default)")
    args = ap.parse_args(argv)

    opts = CompareOptions(args.numbering, not args.exclude_disabled, not args.compare_comments)
    t0 = time.perf_counter()

    def progress(step: str, d: dict) -> None:
        if step == "ftd_pages":
            print(f"\r  Reading PDF (page {d['page']:,} of {d['pages']:,})", end="", file=sys.stderr, flush=True)
        elif step == "asa_done":
            print(f"  ASA config parsed: {d['rules']:,} rules", file=sys.stderr)
        elif step == "ftd_done":
            print(f"\n  FTD policy parsed: {d['rules']:,} rules", file=sys.stderr)
        elif step == "matching":
            print("  Matching rules…", file=sys.stderr)

    try:
        rr = run(args.asa, args.ftd, opts, progress=progress)
    except NotAnFmcReport as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    session = build_session(rr)
    out = args.output
    ext = out.suffix.lower()
    if ext == ".csv":
        write_csv(session, out)
    elif ext == ".json":
        write_json(session, out)
    else:
        write_excel(session, out)
    m = session["meta"]
    c, cal = m["counts"], m["calibration"]
    print(f"\nSibit — {m['asa_name']} → {m['ftd_name']}  ({time.perf_counter() - t0:.1f}s)")
    print(f"  Matched {cal['match_rate']}% of rules by name ({cal['strategy']} numbering); "
          f"{cal['matched_by_content']} matched by content")
    print(f"  Total {c['total']:,}  |  " + "  ".join(f"{k} {v:,}" for k, v in c["status"].items()))
    print(f"  Critical {c['severity']['critical']:,}  High {c['severity']['high']:,}  "
          f"Medium {c['severity']['medium']:,}  Low {c['severity']['low']:,}")
    print(f"  Order changes around deny rules: {m['order_change_count']:,}")
    print(f"  Report written to {out.resolve()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure") and sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if argv and argv[0] == "compare":
        return _compare(argv[1:])
    ap = argparse.ArgumentParser(prog="sibit", description="Sibit — Firewall Migration Rule Verifier")
    ap.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: first free from 8765)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)
    from .server import serve

    serve(port=args.port or None, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
