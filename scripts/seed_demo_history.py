#!/usr/bin/env python3
"""Seed realistic, correctly-signed demo prescription history.

Idempotent: skips if demo history already exists. Creates finalized prescriptions
attributed to the demo hospital so hospital analytics, doctor activity and the
patient timeline all render with real data.

Development/demo only. Not medical advice.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app import models as M  # noqa: E402
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.models import build_epoch  # noqa: E402
from app.routers.prescriptions import _signable_payload  # noqa: E402
from app.core.security import sign_content  # noqa: E402
from app.services.dosage import format_dosage  # noqa: E402
from app.services.ids import public_token, rx_code  # noqa: E402

DIAGNOSES = [
    "Acute pharyngitis", "Type 2 diabetes mellitus", "Essential hypertension",
    "Gastritis", "Iron deficiency anaemia", "Upper respiratory tract infection",
    "Allergic rhinitis", "Osteoarthritis", "Migraine", "Vitamin D deficiency",
]
ADVICE = [
    "Rest, plenty of fluids, review in 7 days.",
    "Low-salt diet, walk 30 minutes daily, review in 1 month.",
    "Take medicines after food. Avoid spicy food.",
    "Complete the full course. Return if fever persists beyond 3 days.",
]
MEAL = ["after", "before", "empty_stomach", "bedtime"]


def _pick_brands(db, n: int) -> list[M.Brand]:
    # ORDER BY id: an unordered LIMIT would feed random.shuffle a list whose order
    # depends on the query planner, which would make the seeded demo non-reproducible.
    rows = db.scalars(
        select(M.Brand).where(M.Brand.generic_id.isnot(None), M.Brand.form_name.isnot(None))
        .order_by(M.Brand.id).limit(4000)
    ).all()
    random.shuffle(rows)
    return rows[:n]


def _pick_tests(db, n: int) -> list[M.LabTest]:
    rows = db.scalars(select(M.LabTest).order_by(M.LabTest.id).limit(200)).all()
    random.shuffle(rows)
    return rows[:n]


def main() -> int:
    init_db()
    db = SessionLocal()
    random.seed(20261006)

    if db.scalar(select(func.count()).select_from(M.Prescription)) >= 12:
        print(json.dumps({"skipped": True, "reason": "demo history already present"}))
        db.close()
        return 0

    hospital = db.scalar(select(M.Hospital).where(M.Hospital.name.ilike("%Dhaka Medical%"))) \
        or db.scalar(select(M.Hospital).order_by(M.Hospital.id))
    doctors = db.scalars(select(M.Doctor).where(M.Doctor.user_id.isnot(None)).order_by(M.Doctor.id)).all()
    patient = db.scalar(select(M.Patient).order_by(M.Patient.id))
    if not (hospital and doctors and patient):
        print(json.dumps({"error": "run seed_demo.py first"}))
        db.close()
        return 1

    brands = _pick_brands(db, 40)
    tests = _pick_tests(db, 12)
    if not brands:
        print(json.dumps({"error": "no brands in catalog"}))
        db.close()
        return 1

    # Fixed clock during a deterministic build, so issued_at (and therefore the
    # signature, which covers issued_at) is identical on every rebuild.
    now = (build_epoch() or datetime.now(timezone.utc)).replace(tzinfo=None)
    created = 0
    # A FIXED number per day, so the demo history is deterministic by construction
    # (14 days x 4 = 56 prescriptions) rather than depending on a random draw.
    # The RNG is still seeded for the per-prescription details below.
    PER_DAY = 4
    for day in range(13, -1, -1):
        for k in range(PER_DAY):
            # Row-unique, rebuild-stable keys for the code and the QR token.
            key = f"demo-hist-{day}-{k}"
            doctor = random.choice(doctors)
            issued = now - timedelta(days=day, hours=random.randint(0, 9), minutes=random.randint(0, 59))
            rx = M.Prescription(
                rx_code=rx_code(issued.year, key=key), public_token=public_token(key=key), doctor_id=doctor.id,
                hospital_id=hospital.id, patient_id=patient.id,
                diagnosis=random.choice(DIAGNOSES), advice=random.choice(ADVICE),
                issued_at=issued, status="draft",
            )
            db.add(rx)
            db.commit()
            db.refresh(rx)

            for b in random.sample(brands, random.randint(1, 3)):
                slots = {s: random.choice([0, 1, 1, 2]) for s in ("morning", "noon", "evening", "night")}
                if not any(slots.values()):
                    slots["morning"] = 1
                dose = {"slots": slots, "unit": "tablet", "meal": random.choice(MEAL),
                        "duration": {"value": random.choice([5, 7, 10, 14, 30]), "unit": "day"}}
                db.add(M.PrescriptionItem(
                    rx_id=rx.id, brand_id=b.id, generic_id=b.generic_id, form=b.form_name,
                    strength=b.strength_text, dose_json=json.dumps(dose, ensure_ascii=False),
                    bn_dosage_text=format_dosage(dose),
                ))
            for t in random.sample(tests, random.randint(0, 2)):
                db.add(M.PrescriptionTest(rx_id=rx.id, test_id=t.id))
            db.commit()

            ch, sig = sign_content(_signable_payload(db, rx))
            rx.content_hash, rx.signature, rx.status = ch, sig, "finalized"
            db.commit()
            created += 1

    hospital_name = hospital.name
    db.close()
    print(json.dumps({"created_prescriptions": created, "hospital": hospital_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
