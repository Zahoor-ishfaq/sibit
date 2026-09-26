"""Fetch an access policy from an FMC over its REST API into a Sibit JSON bundle.

    python -m sibit.parsers.ftd.fmc_api --host fmc.corp.local --user api-ro \\
        --policy "FTD-Mig-ACP" -o after.json [--insecure]

The password is prompted (never stored). Only read-only GET calls are made
(plus the token request). The bundle is then compared offline like a PDF:
    python -m sibit compare before.cfg after.json -o report.xlsx
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime

OBJECT_TYPES = ["networks", "hosts", "ranges", "fqdns", "networkgroups", "protocolportobjects",
                "portobjectgroups", "icmpv4objects", "icmpv6objects"]


class Fmc:
    def __init__(self, host: str, user: str, password: str, verify: bool = True) -> None:
        self.base = f"https://{host}"
        self.ctx = ssl.create_default_context()
        if not verify:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        req = urllib.request.Request(f"{self.base}/api/fmc_platform/v1/auth/generatetoken", method="POST",
                                     headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
            self.token = r.headers["X-auth-access-token"]
            self.domain = r.headers.get("DOMAIN_UUID") or r.headers.get("global")

    def get(self, path: str, **params: str) -> dict:
        q = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{self.base}{path}{'?' + q if q else ''}",
                                     headers={"X-auth-access-token": self.token, "Accept": "application/json"})
        with urllib.request.urlopen(req, context=self.ctx, timeout=120) as r:
            return json.loads(r.read())

    def paged(self, path: str, **params: str) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            page = self.get(path, offset=str(offset), limit="1000", **params)
            items = page.get("items", [])
            out += items
            total = page.get("paging", {}).get("count", len(out))
            offset += len(items)
            if not items or offset >= total:
                return out


def fetch_bundle(fmc: Fmc, policy: str) -> dict:
    d = f"/api/fmc_config/v1/domain/{fmc.domain}"
    pols = fmc.paged(f"{d}/policy/accesspolicies")
    match = [p for p in pols if p.get("name") == policy or p.get("id") == policy]
    if not match:
        raise SystemExit(f"Access policy '{policy}' not found. Available: {', '.join(p['name'] for p in pols)}")
    pid = match[0]["id"]
    rules = fmc.paged(f"{d}/policy/accesspolicies/{pid}/accessrules", expanded="true")
    objects = {}
    for t in OBJECT_TYPES:
        try:
            objects[t] = fmc.paged(f"{d}/object/{t}", expanded="true")
        except Exception as e:  # noqa: BLE001 - some types may not exist on older FMCs
            print(f"  warning: could not read {t}: {e}", file=sys.stderr)
    return {"format": "sibit-fmc-bundle", "fetched": datetime.now().isoformat(timespec="seconds"),
            "policy": {"name": match[0]["name"], "id": pid}, "accessrules": rules, "objects": objects}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sibit.parsers.ftd.fmc_api", description=__doc__.split("\n")[0])
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--policy", required=True, help="access policy name or id")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    a = ap.parse_args(argv)
    fmc = Fmc(a.host, a.user, getpass.getpass(f"Password for {a.user}@{a.host}: "), verify=not a.insecure)
    bundle = fetch_bundle(fmc, a.policy)
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=1)
    print(f"Wrote {len(bundle['accessrules'])} rules and "
          f"{sum(len(v) for v in bundle['objects'].values())} objects to {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
