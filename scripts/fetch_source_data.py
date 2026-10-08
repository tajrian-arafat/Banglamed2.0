#!/usr/bin/env python3
"""Download the upstream source data files into data/import/ at image-build time.

The catalog is rebuilt from these files (see scripts/build_db.py). They are the
original public source datasets for this project, served from the platform's
object store, so the image build is self-contained and reproducible without
committing ~22 MB of spreadsheets to the repository.

Idempotent: a file that is already present and non-empty is left alone.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "data" / "import"
BASE = "https://imserver.teamily.ai/im_api/object/2267791790744783/msg_file_1791293765504000000223_"

FILES = {
    0: "banglamed-architecture-and-requests.pdf",
    1: "medtestbd_full_dataset.json",
    2: "hospitals_0911.csv",
    3: "doctors_662b.csv",
    4: "brands_part2.xlsx",
    5: "brands_part1.xlsx",
    6: "indications.xlsx",
    7: "generics.xlsx",
    8: "dosage_forms.xlsx",
    9: "drug_classes.xlsx",
    10: "companies.xlsx",
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for idx, name in FILES.items():
        out = DEST / name
        if out.exists() and out.stat().st_size > 0:
            print(f"[fetch] have {name} ({out.stat().st_size} bytes)")
            continue
        url = f"{BASE}{idx}/{name}"
        print(f"[fetch] {name}", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as r, open(out, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if out.stat().st_size == 0:
            raise SystemExit(f"[fetch] FATAL: {name} downloaded empty")
        print(f"[fetch]   -> {out.stat().st_size} bytes")
    print("[fetch] source data ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
