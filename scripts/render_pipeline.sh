#!/bin/sh
# BanglaMed 2.0 — deterministic catalog build pipeline.
#
# Runs at image build time AND on every container start. It is idempotent: if the
# populated database is already present it does nothing, so a start on a warm
# filesystem is a no-op and a start on a cold one heals itself.
#
# This is what makes a disk-less host harmless — the catalog is reconstructed
# from the original source data instead of being stored.
#
# DETERMINISM (M4)
# ----------------
# BANGLAMED_BUILD_EPOCH pins the build clock, so every row carries a fixed
# timestamp instead of the wall-clock time of the build. Together with the
# deterministic demo-account password hashes (core/security.demo_password_hash)
# and a final VACUUM in build_indexes.py, two independent builds of the same
# inputs produce the SAME fingerprint:
#
#     python scripts/state_fingerprint.py   # state_sha256 is stable across runs
#
# Prove it with scripts/verify_determinism.sh.
set -e
cd "$(dirname "$0")/.."

export BANGLAMED_BUILD_EPOCH="${BANGLAMED_BUILD_EPOCH:-1}"

# Honour a mounted persistent disk when one is configured (BANGLAMED_DATA_DIR,
# read by backend/app/core/config.py). The directory must exist before anything
# tries to open the database inside it.
DATADIR="${BANGLAMED_DATA_DIR:-data}"
DB="$DATADIR/banglamed.db"
mkdir -p "$DATADIR"

# Treat a present-but-corrupt file as absent, so a half-written database from a
# killed container is rebuilt instead of served.
if [ -s "$DB" ]; then
  if ! DB="$DB" python -c "import os,sqlite3,sys; sys.exit(0 if sqlite3.connect(os.environ['DB']).execute('PRAGMA integrity_check').fetchone()[0]=='ok' else 1)"; then
    echo "[build] existing database failed integrity_check — rebuilding"
    rm -f "$DB"
  fi
fi

python scripts/fetch_source_data.py

# NOTE: the build scripts below address data/banglamed.db through
# app.core.config.DATA_DIR, which reads the SAME BANGLAMED_DATA_DIR variable
# exported here, so DATADIR and their target can never disagree.
export BANGLAMED_DATA_DIR="$DATADIR"

if [ ! -s "$DB" ]; then
  echo "[build] epoch=$BANGLAMED_BUILD_EPOCH — building catalog from source data"
  python scripts/import_data.py

  # The directory API reads hospitals.listed_doctors; the importer does not create
  # it, so add it before the enrichment step that populates it.
  python - <<'PY'
import os, sqlite3
db = os.path.join(os.environ.get("BANGLAMED_DATA_DIR") or "data", "banglamed.db")
c = sqlite3.connect(db)
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
  # Indexes last (far cheaper than maintaining them across 25k inserts), then the
  # role demo accounts and the versioned demo prescription.
  python scripts/build_indexes.py
  python scripts/seed_demo_accounts.py
else
  echo "[build] catalog already present — skipping rebuild"
fi

python - <<'PY'
import os, sqlite3
db = os.path.join(os.environ.get("BANGLAMED_DATA_DIR") or "data", "banglamed.db")
c = sqlite3.connect(db)
print("[build] integrity:", c.execute("PRAGMA integrity_check").fetchone()[0])
for t in ("brands", "generics", "companies", "doctors", "hospitals",
          "tests", "prescriptions", "users", "prescription_versions",
          "medicine_fts"):
    print(f"[build]   {t:24s}", c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
print("[build]   hospitals(active)      ",
      c.execute("SELECT COUNT(*) FROM hospitals WHERE COALESCE(data_status,'') "
                "NOT IN ('rejected','duplicate')").fetchone()[0])
c.close()
PY
