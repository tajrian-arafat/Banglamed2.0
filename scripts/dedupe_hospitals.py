#!/usr/bin/env python3
"""Reconcile facility rows the upstream listing published more than once.

A row is marked a duplicate only when ALL three signals agree: same district,
same NAME STEM (punctuation flattened, trailing company/place words peeled),
and SIMILAR ADDRESS (same leading number, >=45% token overlap).

Rows are marked ``data_status='duplicate'`` rather than deleted, so every listing
hides them while the original data stays recoverable. Idempotent.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "banglamed.db"

TAIL_WORDS = {"ltd", "limited", "pvt", "private", "co", "the", "dhaka", "bd", "bangladesh"}
LEAD_NUM = re.compile(r"^(\d+)")


def words(s: str | None) -> list[str]:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip().split()


def name_stem(name: str | None, district: str | None) -> str:
    w = words(name)
    drop = set(TAIL_WORDS)
    if district:
        drop.add(district.lower())
    while w and w[-1] in drop:
        w.pop()
    return " ".join(w)


def addr_similar(a: str | None, b: str | None) -> bool:
    wa, wb = set(words(a)), set(words(b))
    if not wa or not wb:
        return False
    na, nb = LEAD_NUM.match(" ".join(words(a))), LEAD_NUM.match(" ".join(words(b)))
    if na and nb and na.group(1) != nb.group(1):
        return False
    inter = len(wa & wb)
    union = len(wa | wb)
    return union and (inter / union) >= 0.45


def main() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()

    rows = cur.execute(
        "SELECT id, name, district_name, address, phone FROM hospitals "
        "WHERE COALESCE(data_status,'') NOT IN ('rejected','duplicate') ORDER BY id"
    ).fetchall()

    seen: dict[tuple, tuple] = {}
    marked: list[tuple[int, int, str, str]] = []
    for hid, name, district, address, phone in rows:
        key = (district, name_stem(name, district))
        prev = seen.get(key)
        if prev is None:
            seen[key] = (hid, address)
            continue
        keep_id, keep_addr = prev
        if addr_similar(address, keep_addr):
            marked.append((hid, keep_id, name, address or ""))
        else:
            seen[key] = (hid, address)

    for dup_id, keep_id, name, address in marked:
        cur.execute("UPDATE hospitals SET data_status='duplicate' WHERE id=?", (dup_id,))
    con.commit()

    print(f"duplicate rows marked: {len(marked)}")
    for dup_id, keep_id, name, address in marked:
        print(f"   id={dup_id:<4} (kept id={keep_id})  {name!r}")
        print(f"        addr={address[:62]!r}")

    active = cur.execute(
        "SELECT COUNT(*) FROM hospitals WHERE COALESCE(data_status,'') NOT IN ('rejected','duplicate')"
    ).fetchone()[0]
    n_rej = cur.execute("SELECT COUNT(*) FROM hospitals WHERE data_status='rejected'").fetchone()[0]
    n_dup = cur.execute("SELECT COUNT(*) FROM hospitals WHERE data_status='duplicate'").fetchone()[0]
    print(f"\nactive facilities: {active}   rejected: {n_rej}   duplicate: {n_dup}")

    dups = cur.execute(
        "SELECT COUNT(*) FROM (SELECT district_name,address FROM hospitals "
        "WHERE COALESCE(data_status,'') NOT IN ('rejected','duplicate') "
        "GROUP BY district_name,address HAVING COUNT(*)>1)"
    ).fetchone()[0]
    print(f"identical-address groups remaining: {dups} (distinct businesses may share a building)")
    con.close()


if __name__ == "__main__":
    main()
