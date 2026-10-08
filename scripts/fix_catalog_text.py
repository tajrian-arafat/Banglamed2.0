#!/usr/bin/env python3
"""Clean two scraped-text artefacts that reached the catalog.

1. Test names carry a duplicated "Test" token (40 of 108 affected).
2. Dosage & administration bodies store a label line followed by a line that
   OPENS WITH A COLON; the label and its value are joined into one line.

Both rewrites are pure text normalisation - no value is invented and nothing is
dropped. Idempotent.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "banglamed.db"

TRAILING_PAREN_TEST = re.compile(r"\)\s*Test\s*$")
DOUBLE_TEST = re.compile(r"Test\s+Test\s*$")


def clean_test_name(name: str) -> str:
    if not name:
        return name
    if TRAILING_PAREN_TEST.search(name):
        return TRAILING_PAREN_TEST.sub(")", name).strip()
    if DOUBLE_TEST.search(name):
        return DOUBLE_TEST.sub("Test", name).strip()
    return name


def clean_dosage(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if line.lstrip().startswith(":") and out:
            out[-1] = out[-1].rstrip() + ":" + line.lstrip()[1:]
        else:
            out.append(line)
    return "\n".join(out)


def main() -> None:
    con = sqlite3.connect(DB)
    cur = con.cursor()

    renamed = 0
    before = {}
    for tid, name in cur.execute("SELECT id, name FROM tests").fetchall():
        new = clean_test_name(name)
        if new != name and new:
            before[name] = new
            cur.execute("UPDATE tests SET name = ? WHERE id = ?", (new, tid))
            renamed += 1

    cleaned = 0
    for bid, txt in cur.execute(
        "SELECT id, dosage_administration FROM brands WHERE dosage_administration LIKE '%\n:%'"
    ).fetchall():
        new = clean_dosage(txt)
        if new != txt:
            cur.execute("UPDATE brands SET dosage_administration = ? WHERE id = ?", (new, bid))
            cleaned += 1

    con.commit()

    dup = cur.execute(
        "SELECT COUNT(*) FROM (SELECT name FROM tests GROUP BY name HAVING COUNT(*) > 1)"
    ).fetchone()[0]

    print(f"test names rewritten      : {renamed}")
    for old, new in list(before.items())[:6]:
        print(f"    {old!r}\n      -> {new!r}")
    print(f"dosage bodies normalised  : {cleaned}")
    print(f"duplicate test names after: {dup}")
    print("\nsample after:", [
        r[0] for r in cur.execute("SELECT name FROM tests ORDER BY name LIMIT 5")
    ])
    print("dosage sample after:", repr(
        cur.execute("SELECT dosage_administration FROM brands WHERE id=1083").fetchone()[0][:160]
    ))
    con.close()


if __name__ == "__main__":
    main()
