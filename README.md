# BanglaMed 2.0

A Bangladesh-focused medicine knowledge base, prescription engine and medication-safety
platform. FastAPI + SQLite backend, React + TypeScript frontend, dark "cool futuristic"
medical UI.

> **Not medical advice.** BanglaMed is informational software. It does not diagnose or
> treat. Always consult a registered doctor or pharmacist.

## What it does

- **Medicine catalog** — 25,405 brands, 1,653 generics, 223 companies, 1,726 indications,
  21 drug classes, 124 dosage forms, with prices (BDT), pack sizes and full clinical text.
- **Search** — prefix + typo-tolerant (RapidFuzz) search across brand, generic and company.
- **Prescriptions** — doctor writes a prescription, runs medication-safety checks, then
  finalizes it with a tamper-evident HMAC digital seal and a scannable QR code.
- **Safety engine** — duplicate ingredient, duplicate therapeutic class, interaction text
  match, allergy, pregnancy/lactation, age-band, long-duration and repeat-prescription flags.
- **Bangla dosage** — deterministic Bangla dosage instructions (সকাল ১টি — খাবারের পরে — ৭ দিন).
- **Cost calculator** — per-course / 7-day / 30-day estimates in BDT, strip-price derivation.
- **Patient records** — timeline of prescriptions, appointments and tests; family profiles;
  allergies; prescription photo upload with quality check and OCR/typed fallback.
- **Appointments** — serial booking with database-enforced concurrency safety.
- **Directory** — 2,082 doctors and 125 hospitals, searchable by name and speciality.
- **Analytics** — hospital prescription trends, top medicines/tests, doctor activity.
- **Admin** — users, data verification, audit trail, module registry.

## Architecture

```
backend/app/
  core/        config, db, security (bcrypt+JWT+HMAC seal), audit, modules, ratelimit
  models.py    SQLAlchemy 2.x models (all modules)
  schemas.py   Pydantic v2 request/response schemas
  routers/     auth, catalog, patients, prescriptions, cost, records, interpreter,
               reminders, appointments, doctor_workspace, analytics, admin
  services/    import_pipeline, search, safety, dosage, cost, interpreter, ids
config/        modules.config.json, safety_rules.json, cost_rules.json, matching.json
scripts/       import_data.py, seed_demo.py
frontend/      React + TS + Vite SPA (design-system, core, components, pages)
```

Modules are registered in a config-driven registry (`config/modules.config.json`) with
dependency validation — modules can be attached/detached without code changes.

## Quick start

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then set a strong SECRET_KEY

# 2. Import data (drop source files in data/import/ first)
python scripts/import_data.py

# 3. Seed demo accounts, doctor profiles, schedules, curated interactions
python scripts/seed_demo.py

# 3b. Seed realistic, correctly-signed demo prescription history
#     (populates hospital analytics, doctor activity and the patient timeline)
python scripts/seed_demo_history.py

# 4. Run the API (serves the built SPA too, if frontend/dist exists)
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. Frontend (dev)
cd frontend && npm install && npm run dev     # http://localhost:5173
# or build for the API to serve:
npm run build
```

## Demo accounts (development only)

| Role           | Username         | Password      |
|----------------|------------------|---------------|
| Patient        | `patient.demo`   | `Patient@123` |
| Doctor         | `dr.rahman`      | `Doctor@123`  |
| Hospital admin | `hospital.dhaka` | `Hospital@123`|
| System admin   | `admin`          | `Admin@123`   |

## Tests

```bash
cd backend && python -m pytest -q
```

Covers the API + RBAC matrix, the full prescription workflow (create → safety → finalize →
verify → QR → public view), Bangla dosage formatting (16 cases), the cost calculator,
signature tamper detection, and booking concurrency.

## Security

- bcrypt password hashing; JWT access/refresh tokens; login lockout + rate limiting.
- Strict role-based authorization on every endpoint (patient / doctor / hospital_admin /
  system_admin); object-level ownership checks on records and prescriptions.
- Parameterized queries via SQLAlchemy ORM; Pydantic input validation; uniform error envelope.
- HMAC-SHA256 digital seal on finalized prescriptions; public QR view is read-only and
  recomputes the seal to detect tampering.
- Audit logging of every prescription/record access, with patient identifiers masked in logs.
- Secrets only via environment variables (`.env`, never committed).

## Data provenance

Catalog data is scraped from public Bangladesh medicine directories (medex.com.bd),
doctor/hospital data from seradoctor.com, and test data from medtestbd.com. Every row carries
`source_name`, `source_url`, `collected_at`, `batch_id` and `data_status` for provenance and
review. Import runs are recorded in `import_batches`.
