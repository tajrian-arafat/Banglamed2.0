#!/usr/bin/env python3
"""Create the search indexes after the catalog has been built.

Why a separate step (and not just SQLAlchemy's ``index=True``)
--------------------------------------------------------------
``SQLAlchemy.metadata.create_all`` issues each ``CREATE INDEX`` in the same
write transaction batch as table creation, which is unnecessary here and, more
importantly, cannot express the *covering* index ``(brand_n, id)`` that makes the
typeahead prefix scan index-only.

Indexing AFTER the bulk load is also markedly faster: maintaining five indexes
across 25,405 inserts is far more expensive than building them once at the end.

Idempotent (``IF NOT EXISTS``), so it is safe on every container start.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "banglamed.db"

# (name, table, columns) — the plain ones mirror models.py's index=True so an
# existing database keeps the same set; the covering one is the addition.
INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_fts_brand_n", "medicine_fts", ["brand_n"]),
    ("ix_fts_generic_n", "medicine_fts", ["generic_n"]),
    ("ix_fts_company_n", "medicine_fts", ["company_n"]),
    ("ix_fts_first_token", "medicine_fts", ["first_token"]),
    ("ix_fts_brand_root", "medicine_fts", ["brand_root"]),
    ("ix_fts_brand_n_id", "medicine_fts", ["brand_n", "id"]),          # covering
    ("ix_fts_first_token_id", "medicine_fts", ["first_token", "id"]),  # covering
]


def main() -> int:
    if not DB.exists():
        raise SystemExit("[indexes] FATAL: database not built yet")
    con = sqlite3.connect(DB)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(medicine_fts)")}
        missing = {c for _, _, cs in INDEXES for c in cs if c not in cols}
        if missing:
            raise SystemExit(f"[indexes] FATAL: medicine_fts missing columns: {sorted(missing)}")
        for name, table, columns in INDEXES:
            t0 = time.time()
            con.execute(
                f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({", ".join(columns)})'
            )
            print(f"[indexes] {name} ({time.time() - t0:.1f}s)", flush=True)
        con.commit()
        con.execute("ANALYZE")
        con.commit()
        print("[indexes] analyze done")
        # VACUUM rebuilds the file from scratch, which makes the on-disk layout
        # depend only on logical content — part of keeping a rebuild byte-stable.
        con.execute("VACUUM")
        con.commit()
        print("[indexes] vacuum done")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
