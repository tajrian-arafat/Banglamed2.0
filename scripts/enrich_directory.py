#!/usr/bin/env python3
"""Backfill the directory fields the upstream catalogs left empty.

Nothing here is invented. Every value is derived from text that already exists
in the source data or in the row itself. Idempotent.
Run:  python3 scripts/enrich_directory.py
"""
from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "banglamed.db"
CSV_HOSP = REPO / "data" / "import" / "hospitals_0911.csv"

JUNK_NAMES = {"sera doctor logo", "dactarachen"}

_GENERIC = re.compile(
    r"\b(ltd|limited|pvt|private|hospital|clinic|medical|college|centre|center|"
    r"diagnostic|diagnostics|services|health|healthcare|care|&|and|the|"
    r"general|specialized|specialised)\b",
    re.IGNORECASE,
)


def collide_free_pattern(names: list[str]) -> re.Pattern | None:
    if not names:
        return None
    ordered = sorted({n for n in names if n}, key=len, reverse=True)
    alts = "|".join(re.escape(n) for n in ordered)
    return re.compile(rf"(?<![A-Za-z])(?:{alts})(?![A-Za-z])", re.IGNORECASE)


def facility_core(name: str) -> str:
    core = _GENERIC.sub(" ", name)
    core = re.sub(r"[^0-9a-z\s]", " ", core.lower())
    return re.sub(r"\s+", " ", core).strip()


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    report: dict[str, int | str] = {}

    cols = {r[1] for r in cur.execute("PRAGMA table_info(hospitals)")}
    if "listed_doctors" not in cols:
        cur.execute("ALTER TABLE hospitals ADD COLUMN listed_doctors INTEGER")
        print("  + added hospitals.listed_doctors")

    districts = [r[0] for r in cur.execute("SELECT name FROM geo_districts WHERE name IS NOT NULL")]
    dpat = collide_free_pattern(districts)
    filled = 0
    rows = cur.execute(
        "SELECT id, qualifications, designation FROM doctors "
        "WHERE district_name IS NULL OR TRIM(district_name) = ''"
    ).fetchall()
    for r in rows:
        text = f"{r['qualifications'] or ''} {r['designation'] or ''}"
        if not text.strip() or not dpat:
            continue
        m = dpat.search(text)
        if m:
            canon = next((d for d in districts if d.lower() == m.group(0).lower()), m.group(0))
            cur.execute("UPDATE doctors SET district_name = ? WHERE id = ?", (canon, r["id"]))
            filled += 1
    report["doctor_districts_filled"] = filled

    facs = cur.execute(
        "SELECT id, name FROM hospitals WHERE name IS NOT NULL AND TRIM(name) <> ''"
    ).fetchall()
    cores = []
    for f in facs:
        core = facility_core(f["name"])
        if len(core) >= 5:
            cores.append((f["id"], core))
    aff_added = 0
    linked_doctors = set()
    if cores:
        docs = cur.execute(
            "SELECT id, qualifications, designation FROM doctors"
        ).fetchall()
        existing = {
            (r[0], r[1]) for r in cur.execute("SELECT doctor_id, hospital_id FROM doctor_affiliations")
        }
        for d in docs:
            hay = f" {d['qualifications'] or ''} {d['designation'] or ''} ".lower()
            hay = re.sub(r"\s+", " ", hay)
            for hid, core in cores:
                if core in hay and (d["id"], hid) not in existing:
                    cur.execute(
                        "INSERT INTO doctor_affiliations (doctor_id, hospital_id) VALUES (?, ?)",
                        (d["id"], hid),
                    )
                    aff_added += 1
                    linked_doctors.add(d["id"])
                    break
    report["affiliations_derived"] = aff_added
    report["doctors_with_affiliation"] = len(linked_doctors)

    if CSV_HOSP.exists():
        listed: dict[str, int] = {}
        with CSV_HOSP.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                url = (r.get("URL") or "").strip()
                raw = (r.get("Listed Doctors") or "").strip()
                if not url or not raw.isdigit():
                    continue
                listed[url] = max(listed.get(url, 0), int(raw))
        upd = 0
        for url, n in listed.items():
            cur.execute(
                "UPDATE hospitals SET listed_doctors = ? WHERE source_url = ? "
                "AND (listed_doctors IS NULL OR listed_doctors < ?)",
                (n, url, n),
            )
            upd += cur.rowcount
        report["hospitals_listed_doctors_set"] = upd
        report["csv_listed_rows"] = len(listed)

    junk_ids = [
        r[0]
        for r in cur.execute("SELECT id, name FROM hospitals")
        if (r[1] or "").strip().lower() in JUNK_NAMES
    ]
    for hid in junk_ids:
        cur.execute("UPDATE hospitals SET data_status = 'rejected' WHERE id = ?", (hid,))
    report["junk_hospitals_rejected"] = len(junk_ids)

    con.commit()

    print("\n=== ENRICHMENT RESULT ===")
    for k, v in report.items():
        print(f"  {k:<32s} {v}")

    print("\n=== POST-STATE ===")
    print("  doctors with district:", cur.execute(
        "SELECT COUNT(*) FROM doctors WHERE district_name IS NOT NULL AND TRIM(district_name)<>''"
    ).fetchone()[0], "/", cur.execute("SELECT COUNT(*) FROM doctors").fetchone()[0])
    print("  district spread (top 10):")
    for n, c in cur.execute(
        "SELECT district_name, COUNT(*) FROM doctors WHERE district_name IS NOT NULL "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
    ):
        print(f"    {c:>5}  {n}")
    print("  doctor_affiliations:", cur.execute("SELECT COUNT(*) FROM doctor_affiliations").fetchone()[0])
    print("  hospitals active:", cur.execute(
        "SELECT COUNT(*) FROM hospitals WHERE COALESCE(data_status,'') <> 'rejected'"
    ).fetchone()[0])
    print("  hospitals with listed_doctors:", cur.execute(
        "SELECT COUNT(*) FROM hospitals WHERE listed_doctors IS NOT NULL"
    ).fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
