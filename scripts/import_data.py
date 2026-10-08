#!/usr/bin/env python3
"""One-command data import: drop files in data/import/ and run this.

Usage: python scripts/import_data.py [--dir data/import]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.services import import_pipeline as P  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "data" / "import"))
    args = ap.parse_args()
    d = Path(args.dir)
    init_db()
    db = SessionLocal()
    report: dict = {}
    try:
        geo = P.load_geo(db)
        report["geo"] = {"divisions": len(geo["divisions"]), "districts": len(geo["districts"])}
        if (d / "companies.xlsx").exists():
            report["companies"] = P.load_companies(db, d / "companies.xlsx", "medex.com.bd")
        if (d / "drug_classes.xlsx").exists():
            report["drug_classes"] = P.load_drug_classes(db, d / "drug_classes.xlsx", "medex.com.bd")
        if (d / "dosage_forms.xlsx").exists():
            report["dosage_forms"] = P.load_dosage_forms(db, d / "dosage_forms.xlsx", "medex.com.bd")
        if (d / "generics.xlsx").exists():
            report["generics"] = P.load_generics(db, d / "generics.xlsx", "medex.com.bd")
        if (d / "indications.xlsx").exists():
            report["indications"] = P.load_indications(db, d / "indications.xlsx", "medex.com.bd")
        brand_files = sorted(d.glob("brands_part*.xlsx"))
        if brand_files:
            report["brands"] = P.load_brands(db, brand_files, "medex.com.bd")
        if (d / "doctors_662b.csv").exists():
            report["doctors"] = P.load_doctors(db, d / "doctors_662b.csv", "seradoctor.com")
        if (d / "hospitals_0911.csv").exists():
            report["hospitals"] = P.load_hospitals(db, d / "hospitals_0911.csv", "seradoctor.com", geo)
        if (d / "medtestbd_full_dataset.json").exists():
            report["tests"] = P.load_tests(db, d / "medtestbd_full_dataset.json", "medtestbd.com")
        report["fts"] = P.build_fts(db)
    finally:
        db.close()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
