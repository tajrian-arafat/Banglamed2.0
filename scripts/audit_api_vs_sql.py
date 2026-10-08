#!/usr/bin/env python3
"""API-vs-SQL ground-truth harness for the BanglaMed 2.0 medicine detail page.

For a sample of real medicines spanning every dosage form, this compares the
detail API's relationship groups against independent SQL over the same SQLite
file, using the *documented* grouping rules:

  alternatives     same generic + same strength + same form
  other_forms      same generic + same strength + different form
  other_strengths  same generic + same form + different strength
  brand_family     same generic + same first-token brand, neither of the above

Exit code is non-zero when any count disagrees, so this is usable as a gate.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import urllib.request

DB = "/workspace/banglamed2.0/data/banglamed.db"
API = "http://127.0.0.1:8000"
WS = re.compile(r"\s+")


def norm_strength(s: str | None) -> str:
    return WS.sub("", (s or "")).lower()


def root(name: str | None) -> str:
    return WS.split((name or "").strip())[0].lower() if (name or "").strip() else ""


def sql_truth(cur, brand: sqlite3.Row) -> dict[str, int]:
    gid = brand["generic_id"]
    if not gid:
        return {"alternatives": 0, "other_forms": 0, "other_strengths": 0, "brand_family": 0,
                "same_generic_total": 0}
    rows = cur.execute(
        "SELECT id,name,strength_text,form_name FROM brands WHERE generic_id=? AND id<>?",
        (gid, brand["id"]),
    ).fetchall()
    my_s, my_f, my_root = norm_strength(brand["strength_text"]), (brand["form_name"] or "").strip().lower(), root(brand["name"])
    c = {"alternatives": 0, "other_forms": 0, "other_strengths": 0, "brand_family": 0}
    for r in rows:
        ss = norm_strength(r["strength_text"]) == my_s
        sf = (r["form_name"] or "").strip().lower() == my_f
        if ss and sf:
            c["alternatives"] += 1
        elif ss:
            c["other_forms"] += 1
        elif sf:
            c["other_strengths"] += 1
        elif my_root and root(r["name"]) == my_root:
            c["brand_family"] += 1
    c["same_generic_total"] = len(rows)
    return dict(c)


def get_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=25) as fh:
            return json.loads(fh.read().decode())
    except Exception as exc:  # noqa: BLE001
        print(f"    !! API error for {url}: {exc}")
        return None


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    picked: list[int] = []
    forms = [r[0] for r in cur.execute(
        "SELECT form_name FROM brands WHERE generic_id IS NOT NULL AND TRIM(COALESCE(form_name,''))<>'' "
        "GROUP BY form_name ORDER BY COUNT(*) DESC LIMIT 20"
    ).fetchall()]
    for form in forms:
        row = cur.execute(
            "SELECT id FROM brands WHERE form_name=? AND generic_id IS NOT NULL ORDER BY id LIMIT 1",
            (form,),
        ).fetchone()
        if row:
            picked.append(row["id"])
    big_generics = [r[0] for r in cur.execute(
        "SELECT generic_id FROM brands WHERE generic_id IS NOT NULL GROUP BY generic_id "
        "ORDER BY COUNT(*) DESC LIMIT 3"
    ).fetchall()]
    for gid in big_generics:
        row = cur.execute(
            "SELECT id FROM brands WHERE generic_id=? ORDER BY id LIMIT 1", (gid,)
        ).fetchone()
        if row:
            picked.append(row["id"])

    picked = list(dict.fromkeys(picked))
    groups = ("alternatives", "other_forms", "other_strengths", "brand_family")
    total_checks = 0
    mismatches: list[str] = []

    print(f"{'id':>7} {'form':<18} {'strength':<12} {'generic':<24} "
          f"{'alt db/api':>12} {'forms db/api':>14} {'str db/api':>12} {'fam db/api':>12}  ok")
    print("-" * 118)

    for bid in picked:
        b = cur.execute(
            "SELECT id,name,generic_id,strength_text,form_name FROM brands WHERE id=?", (bid,)
        ).fetchone()
        if not b:
            continue
        truth = sql_truth(cur, b)
        gen = cur.execute("SELECT name FROM generics WHERE id=?", (b["generic_id"],)).fetchone()
        data = get_json(f"{API}/api/medicines/{bid}")
        if not data:
            mismatches.append(f"brand {bid}: API did not return JSON")
            continue

        row_ok = True
        cells = []
        for g in groups:
            api_v = int(data.get(f"{g}_count", -1))
            list_v = len(data.get(g) or [])
            db_v = truth[g]
            total_checks += 1
            if api_v != db_v or list_v != db_v:
                row_ok = False
                mismatches.append(
                    f"brand {bid} ({b['name']}): {g} db={db_v} api_count={api_v} api_list={list_v}"
                )
            cells.append(f"{db_v}/{api_v}")
        print(f"{bid:>7} {(b['form_name'] or '-')[:17]:<18} {(b['strength_text'] or '-')[:11]:<12} "
              f"{(gen['name'] if gen else '-')[:23]:<24} {cells[0]:>12} {cells[1]:>14} "
              f"{cells[2]:>12} {cells[3]:>12}  {'OK' if row_ok else 'MISMATCH'}")

    print("-" * 118)
    print(f"medicines sampled: {len(picked)}   group checks: {total_checks}   mismatches: {len(mismatches)}")
    for m in mismatches:
        print("  !", m)
    con.close()
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
