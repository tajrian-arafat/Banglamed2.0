#!/usr/bin/env python3
"""Ground-truth audit of the BanglaMed 2.0 SQLite database.

Purpose: express DB truth as numbers so any API/UI shortfall (silent LIMIT
truncation, wrong grouping, dropped rows, duplicates, orphan FKs, NULL keys)
can be *proven* rather than guessed.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path("/workspace/banglamed2.0/data/banglamed.db")
OUT = Path("/workspace/banglamed2.0/data/audit_db_report.json")


def table_cols(cur, table: str) -> list[str]:
    return [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')]


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    rep: dict = {}

    tables = [
        r[0]
        for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    rep["table_counts"] = {
        t: cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables
    }

    print("=== TABLE ROW COUNTS ===")
    for t, n in rep["table_counts"].items():
        print(f"  {t:<34s} {n:>9,d}")

    if "brands" in tables:
        bcols = table_cols(cur, "brands")
        print(f"\n=== brands columns ===\n  {bcols}")
        total = rep["table_counts"]["brands"]

        def cnt(where: str) -> int:
            return cur.execute(f"SELECT COUNT(*) FROM brands WHERE {where}").fetchone()[0]

        rep["brands_nulls"] = {
            "total": total,
            "null_generic_id": cnt("generic_id IS NULL"),
            "empty_strength": cnt("strength_text IS NULL OR TRIM(strength_text)=''"),
            "empty_form": cnt("form_name IS NULL OR TRIM(form_name)=''"),
            "null_company_id": cnt("company_id IS NULL"),
        }
        print("\n=== brands NULL / empty ==")
        for k, v in rep["brands_nulls"].items():
            print(f"  {k:<20s} {v:>9,d}")

        rep["orphans"] = {
            "generic_fk_missing": cur.execute(
                "SELECT COUNT(*) FROM brands b LEFT JOIN generics g ON g.id=b.generic_id "
                "WHERE b.generic_id IS NOT NULL AND g.id IS NULL"
            ).fetchone()[0],
            "company_fk_missing": cur.execute(
                "SELECT COUNT(*) FROM brands b LEFT JOIN companies c ON c.id=b.company_id "
                "WHERE b.company_id IS NOT NULL AND c.id IS NULL"
            ).fetchone()[0],
        }
        print("\n=== orphan foreign keys ===")
        for k, v in rep["orphans"].items():
            print(f"  {k:<20s} {v:>9,d}")

        dups = cur.execute(
            """SELECT name, strength_text, form_name, company_id, COUNT(*) c
               FROM brands GROUP BY name, strength_text, form_name, company_id
               HAVING c > 1 ORDER BY c DESC, name LIMIT 25"""
        ).fetchall()
        rep["duplicate_brand_groups"] = cur.execute(
            """SELECT COUNT(*) FROM (SELECT 1 FROM brands
               GROUP BY name, strength_text, form_name, company_id HAVING COUNT(*) > 1)"""
        ).fetchone()[0]
        print(f"\n=== duplicate brand groups (name+strength+form+company): {rep['duplicate_brand_groups']} (top 25) ===")
        for name, st, fm, cid, c in dups:
            print(f"  x{c:<4d} {name} | {st} | {fm} | company={cid}")

        big = cur.execute(
            """SELECT g.name, COUNT(*) c FROM brands b JOIN generics g ON g.id=b.generic_id
               GROUP BY b.generic_id ORDER BY c DESC LIMIT 15"""
        ).fetchall()
        rep["largest_generics"] = [{"generic": n, "brands": c} for n, c in big]
        print("\n=== generics with most brands ===")
        for n, c in big:
            print(f"  {c:>5,d}  {n}")

        forms = cur.execute(
            "SELECT COALESCE(form_name,'(null)'), COUNT(*) FROM brands GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        rep["form_distribution"] = {f: c for f, c in forms}
        print(f"\n=== dosage form distribution ({len(forms)} distinct) ===")
        for f, c in forms[:30]:
            print(f"  {f:<30s} {c:>8,d}")

        variants = cur.execute(
            """SELECT COUNT(*) FROM (
                 SELECT generic_id, REPLACE(REPLACE(LOWER(strength_text),' ',''),'\t','') k,
                        COUNT(DISTINCT strength_text) d
                 FROM brands WHERE generic_id IS NOT NULL
                 GROUP BY generic_id, k HAVING d > 1)"""
        ).fetchone()[0]
        rep["strength_format_variant_groups"] = variants
        print(f"\n=== strength groups differing only by formatting: {variants:,d}")

    OUT.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
