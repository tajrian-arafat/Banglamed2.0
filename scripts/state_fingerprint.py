#!/usr/bin/env python3
"""Deterministic per-table state fingerprint (CLI).

The problem it solves
---------------------
Render's free tier has no persistent disk, so a redeploy recreates the SQLite
file. "Nothing changed" therefore has to be *proved*, not asserted: this prints a
canonical digest of every table's rows (ordered, normalised) plus the row counts.
Two builds that agree on this fingerprint hold identical data, whatever the
file's internal page layout happens to be.

The implementation lives in ``backend/app/services/statefp.py`` and is imported
here, NOT reimplemented, because the live API exposes the same digest at
``GET /api/health/state``. A single implementation means the number printed below
can never drift from the number the deployment serves over HTTP.

Usage
-----
    python3 scripts/state_fingerprint.py                # human summary
    python3 scripts/state_fingerprint.py --json         # machine-readable
    python3 scripts/state_fingerprint.py --out f.json   # also write to a file
    python3 scripts/state_fingerprint.py a.json b.json  # compare two fingerprints

The comparison reports two verdicts:
  * ``state_sha256``       — every table, every column. Strictest.
  * ``persistence_sha256`` — catalog + seeded dataset, excluding runtime-written
    tables and write timestamps. This is the digest the "database survives a
    redeploy" guarantee is stated in terms of, because a long-lived deployment
    legitimately rewrites timestamps and appends to the audit log as it is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.statefp import fingerprint, stable_fingerprint  # noqa: E402

DEFAULT_DB = ROOT / "data" / "banglamed.db"


def compare(a: dict, b: dict) -> int:
    print(f"  A state_sha256        {a['state_sha256']}  ({a['total_rows']} rows)")
    print(f"  B state_sha256        {b['state_sha256']}  ({b['total_rows']} rows)")
    full_same = a["state_sha256"] == b["state_sha256"]
    print(f"  FULL STATE: {'IDENTICAL' if full_same else 'DIFFERENT'}"
          + ("" if full_same else "  (expected if the app was used between readings)"))

    rc = 0
    sa, sb = a.get("stable", {}), b.get("stable", {})
    if sa and sb:
        same = sa["persistence_sha256"] == sb["persistence_sha256"]
        print(f"\n  A persistence_sha256  {sa['persistence_sha256']}")
        print(f"  B persistence_sha256  {sb['persistence_sha256']}")
        print(f"  PERSISTENCE: {'IDENTICAL' if same else 'DIFFERENT'} "
              f"(catalog + seeded data, runtime tables and timestamps excluded)")
        if not same:
            rc = 1
            for name in sorted(set(sa["tables"]) | set(sb["tables"])):
                ta, tb = sa["tables"].get(name), sb["tables"].get(name)
                if ta != tb:
                    print(f"    {name:<26} {(ta or {}).get('rows', '—')} -> {(tb or {}).get('rows', '—')}")

    print("\n  headline counts:")
    for key in ("brands", "generics", "companies", "doctors", "hospitals",
                "tests", "prescriptions", "users"):
        ta = a["tables"].get(key, {})
        tb = b["tables"].get(key, {})
        flag = "" if ta.get("rows") == tb.get("rows") else "  <-- CHANGED"
        print(f"    {key:<14} {ta.get('rows')} -> {tb.get('rows')}{flag}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="fingerprint JSON files to compare (0 or 2)")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args()

    if len(args.paths) == 2:
        a = json.loads(Path(args.paths[0]).read_text())
        b = json.loads(Path(args.paths[1]).read_text())
        return compare(a, b)

    fp = fingerprint(Path(args.db))
    fp["stable"] = stable_fingerprint(Path(args.db))
    if args.out:
        Path(args.out).write_text(json.dumps(fp, indent=2))
    if args.json:
        print(json.dumps(fp, indent=2))
        return 0

    print(f"database            {fp['db']}")
    print(f"integrity_check     {fp['integrity_check']}")
    print(f"tables              {fp['table_count']}")
    print(f"total rows          {fp['total_rows']}")
    print(f"state_sha256        {fp['state_sha256']}")
    print(f"persistence_sha256  {fp['stable']['persistence_sha256']}")
    print(f"                    ({fp['stable']['total_rows']} rows / "
          f"{fp['stable']['table_count']} tables — runtime tables + write timestamps excluded)")
    print()
    print(f"{'table':<28}{'rows':>9}  sha256")
    for name in sorted(fp["tables"], key=lambda n: -fp["tables"][n]["rows"]):
        t = fp["tables"][name]
        print(f"{name:<28}{t['rows']:>9}  {t['sha256'][:32]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
