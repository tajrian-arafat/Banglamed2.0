"""Canonical state fingerprint, shared by the CLI and the live API.

Why this exists
---------------
Render's free tier has no persistent disk, so a redeploy recreates the SQLite
file. "The data is unchanged across redeploys" therefore has to be *provable*
from outside, not asserted — hence a digest that a caller can fetch over HTTP
and compare with the one taken before the deploy.

Two digests are produced:

``fingerprint``          every table, every column, including write timestamps.
``stable_fingerprint``   the catalog + seeded dataset only, excluding
                         runtime-written tables and created_at/updated_at/used_at.

The *stable* digest is the one the persistence guarantee is stated in terms of,
because a long-lived deployment legitimately rewrites timestamps and appends to
the audit log as it is used. Because the build pins a fixed clock
(BANGLAMED_BUILD_EPOCH — see models.build_epoch), even a full rebuild from the
source data reproduces the stable digest exactly.

Single implementation is deliberate: `scripts/state_fingerprint.py` and the
``/api/health/state`` endpoint both import this module, so the number shown in
the API can never drift from the number the CLI prints.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

#: Columns carrying a write timestamp. Excluded from the stable digest: a running
#: deployment rewrites these as rows are touched, which is legitimate and must not
#: read as "the data changed".
TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at", "used_at"})

#: Tables written by runtime activity rather than by the catalog build. The stable
#: digest covers the seeded catalog + demo dataset, which is exactly what a rebuild
#: is required to reproduce; these grow as the app is used.
RUNTIME_TABLES = frozenset({
    "access_codes", "appointments", "audit_log", "brand_aliases", "departments",
    "geo_thanas", "geo_upazilas", "push_subscriptions", "reminder_events",
    "reminder_items", "reminders", "rx_uploads", "safety_acknowledgements",
    "test_categories", "test_records",
})


def _tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _canonical(value) -> str:
    if value is None:
        return "\x00"
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    p = str(db_path)
    if not p.startswith("file:"):
        p = f"file:{p}?mode=ro"
    return sqlite3.connect(p, uri=True)


def fingerprint(db_path: str | Path) -> dict:
    con = _connect(db_path)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables: dict[str, dict] = {}
        for name in _tables(con):
            h = hashlib.sha256()
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")')]
            order = ", ".join(f'"{c}"' for c in cols)
            n = 0
            for row in con.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
                h.update("\x1f".join(_canonical(v) for v in row).encode("utf-8", "surrogatepass"))
                h.update(b"\x1e")
                n += 1
            tables[name] = {"rows": n, "sha256": h.hexdigest()}
        aggregate = hashlib.sha256()
        for name in sorted(tables):
            aggregate.update(f"{name}:{tables[name]['rows']}:{tables[name]['sha256']}\n".encode())
        return {
            "db": Path(str(db_path)).name,
            "integrity_check": integrity,
            "table_count": len(tables),
            "total_rows": sum(t["rows"] for t in tables.values()),
            "state_sha256": aggregate.hexdigest(),
            "tables": tables,
        }
    finally:
        con.close()


def stable_fingerprint(db_path: str | Path) -> dict:
    con = _connect(db_path)
    try:
        tables: dict[str, dict] = {}
        for name in _tables(con):
            if name in RUNTIME_TABLES:
                continue
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")')]
            if not cols:
                continue
            h = hashlib.sha256()
            order = ", ".join(f'"{c}"' for c in cols)
            n = 0
            for row in con.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
                keep = [v for c, v in zip(cols, row) if c not in TIMESTAMP_COLUMNS]
                h.update("\x1f".join(_canonical(v) for v in keep).encode("utf-8", "surrogatepass"))
                h.update(b"\x1e")
                n += 1
            tables[name] = {
                "rows": n,
                "sha256": h.hexdigest(),
                "columns": [c for c in cols if c not in TIMESTAMP_COLUMNS],
            }
        aggregate = hashlib.sha256()
        for name in sorted(tables):
            aggregate.update(f"{name}:{tables[name]['rows']}:{tables[name]['sha256']}\n".encode())
        return {
            "db": Path(str(db_path)).name,
            "scope": "catalog + seeded dataset (runtime tables and write timestamps excluded)",
            "table_count": len(tables),
            "total_rows": sum(t["rows"] for t in tables.values()),
            "persistence_sha256": aggregate.hexdigest(),
            "tables": tables,
        }
    finally:
        con.close()
