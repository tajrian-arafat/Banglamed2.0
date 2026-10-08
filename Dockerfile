# syntax=docker/dockerfile:1
#
# BanglaMed 2.0 — single-container deploy.
#
# FastAPI/uvicorn serves BOTH the JSON API and the built React SPA from the same
# origin, so the frontend's relative `/api/*` calls work with no CORS setup.
#
# ── Why a multi-stage build ──────────────────────────────────────────────────
# The SPA is compiled in a Node stage and copied into the Python runtime, so the
# runtime image needs no Node toolchain and the build is fully reproducible.
#
# ── Database persistence (the honest answer) ─────────────────────────────────
# Render's free tier mounts NO persistent disk, so a database written at runtime
# is destroyed on every deploy AND every restart (including a wake from sleep).
# The catalog is therefore REBUILT from the original source data during the image
# build, and re-asserted on every container start by scripts/render_pipeline.sh:
#
#   fetch_source_data.py  pulls the upstream datasets (~10 MB) from the project's
#                         permanent object-store URLs
#   import_data.py        loads companies/generics/indications/tests/brands + FTS
#   (ALTER TABLE)         adds hospitals.listed_doctors, which the directory API reads
#   enrich_directory.py   derives doctor districts + hospital<->doctor links
#   dedupe_hospitals.py   flags the facilities the source published twice
#   fix_catalog_text.py   normalises scraped test names / dosage bodies
#   seed_demo.py          demo accounts, doctor profiles, patient, interactions
#   seed_demo_history.py  deterministic demo prescription history (analytics)
#
# The pipeline is idempotent: if the filesystem persisted it is a no-op, and if it
# did not, the container heals itself instead of serving an empty catalog. Net
# effect: every fresh container comes up fully populated, with no data committed
# to the repository.
#
# ── Secrets ──────────────────────────────────────────────────────────────────
# SECRET_KEY comes from the environment only (Render generates and stores it
# encrypted). Nothing is hardcoded here.

# ── Stage 1: build the React SPA ─────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the platform health check tooling; tesseract-ocr is the OCR
# engine behind the prescription-reading feature (pytesseract drives it).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
COPY --from=frontend /fe/dist ./frontend/dist

# Build the populated catalog into the image so the very first boot is instant.
RUN sh scripts/render_pipeline.sh

EXPOSE 8000

# Re-assert the catalog on every start (a no-op when it already exists), then serve.
CMD ["sh", "-c", "sh scripts/render_pipeline.sh && cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
