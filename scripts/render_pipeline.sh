#!/bin/sh
# BanglaMed 2.0 — catalog build pipeline.
#
# Runs at image build time AND on every container start. It is idempotent: if the
# populated database is already present it does nothing, so a start on a warm
# filesystem is a no-op and a start on a cold one heals itself.
#
# This is what makes Render's free tier (no persistent disk) harmless — the
# catalog is reconstructed from the original source data instead of being stored.
set -e
cd "$(dirname "$0")/.."

python scripts/fetch_source_data.py

if [ ! -s data/banglamed.db ]; then
  echo "[render] building catalog from source data"
  python scripts/import_data.py

  # The directory API reads hospitals.listed_doctors; the importer does not create
  # it, so add it before the enrichment step that populates it.
  python - <<'PY'
import sqlite3
c = sqlite3.connect("data/banglamed.db")
cols = [r[1] for r in c.execute("PRAGMA table_info(hospitals)")]
if "listed_doctors" not in cols:
    c.execute("ALTER TABLE hospitals ADD COLUMN listed_doctors INTEGER")
c.commit()
c.close()
PY

  python scripts/enrich_directory.py
  python scripts/dedupe_hospitals.py
  python scripts/fix_catalog_text.py
  python scripts/seed_demo.py
  python scripts/seed_demo_history.py
else
  echo "[render] catalog already present"
fi

python - <<'PY'
import sqlite3
c = sqlite3.connect("data/banglamed.db")
print("[render] integrity:", c.execute("PRAGMA integrity_check").fetchone()[0])
for t in ("brands", "generics", "companies", "doctors", "hospitals",
          "tests", "prescriptions", "users"):
    print(f"[render]   {t:14s}", c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
c.close()
PY
