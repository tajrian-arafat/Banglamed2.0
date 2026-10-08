#!/usr/bin/env python3
"""Seed demo accounts, doctor profiles, schedules and curated interactions.

Idempotent. Demo credentials are printed at the end (development only).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app import models as M  # noqa: E402
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.security import demo_password_hash  # noqa: E402
from app.models import build_epoch  # noqa: E402
from app.services.ids import doc_code, patient_code  # noqa: E402

DEMO = [
    ("admin", "Admin@123", "system_admin", "System Administrator"),
    ("dr.rahman", "Doctor@123", "doctor", "Dr. A. Rahman"),
    ("dr.nusrat", "Doctor@123", "doctor", "Dr. Nusrat Jahan"),
    ("hospital.dhaka", "Hospital@123", "hospital_admin", "Dhaka Medical College Hospital"),
    ("patient.demo", "Patient@123", "patient", "Demo Patient"),
]

CURATED_INTERACTIONS = [
    ("Warfarin", "Aspirin", "critical", "Increased bleeding risk (placeholder rule)."),
    ("Warfarin", "Ibuprofen", "critical", "Increased bleeding risk (placeholder rule)."),
    ("Metformin", "Alcohol", "warn", "Lactic acidosis risk (placeholder rule)."),
    ("Simvastatin", "Clarithromycin", "warn", "Myopathy/rhabdomyolysis risk (placeholder rule)."),
    ("ACE inhibitor", "Potassium", "warn", "Hyperkalemia risk (placeholder rule)."),
]


def main() -> int:
    init_db()
    db = SessionLocal()
    created = {}
    for username, pw, role, full_name in DEMO:
        u = db.scalar(select(M.User).where(M.User.username == username))
        if not u:
            u = M.User(username=username, password_hash=demo_password_hash(username, pw), role=role, full_name=full_name,
                       account_type="personal")
            db.add(u)
            db.commit()
            db.refresh(u)
        created[username] = u.id
    # doctor profiles
    for username, spec, bmdc in [("dr.rahman", "Medicine", "A-12345"), ("dr.nusrat", "Cardiology", "A-67890")]:
        u = db.get(M.User, created[username])
        d = db.scalar(select(M.Doctor).where(M.Doctor.user_id == u.id))
        if not d:
            n = db.query(M.Doctor).count() + 1
            d = M.Doctor(doctor_code=doc_code(n), user_id=u.id, name=u.full_name, speciality_name=spec,
                         bmdc_no=bmdc, qualifications=f"MBBS, FCPS ({spec})", designation=f"Consultant, {spec}",
                         district_name="Dhaka", city="Dhaka", data_status="verified")
            db.add(d)
            db.commit()
            db.refresh(d)
        # a schedule for tomorrow (fixed date during a deterministic build)
        base = build_epoch() or datetime.now(timezone.utc)
        tomorrow = (base + timedelta(days=1)).date().isoformat()
        s = db.scalar(select(M.DoctorSchedule).where(M.DoctorSchedule.doctor_id == d.id, M.DoctorSchedule.date == tomorrow))
        if not s:
            db.add(M.DoctorSchedule(doctor_id=d.id, date=tomorrow, total_serials=30, session_start="17:00",
                                    session_end="21:00", fee=1000))
            db.commit()
    # hospital admin link
    hu = db.get(M.User, created["hospital.dhaka"])
    h = db.scalar(select(M.Hospital).where(M.Hospital.name.ilike("%Dhaka Medical%")))
    if not h:
        h = db.scalar(select(M.Hospital).order_by(M.Hospital.id))
    if h and not db.scalar(select(M.HospitalAdmin).where(M.HospitalAdmin.user_id == hu.id)):
        db.add(M.HospitalAdmin(user_id=hu.id, hospital_id=h.id))
        db.commit()
    # patient profile
    pu = db.get(M.User, created["patient.demo"])
    p = db.scalar(select(M.Patient).where(M.Patient.account_id == pu.id))
    if not p:
        n = db.query(M.Patient).count() + 1
        p = M.Patient(patient_code=patient_code(n), account_id=pu.id, full_name=pu.full_name, relation="self",
                      sex="male", dob="1990-05-12", blood_group="O+")
        db.add(p)
        db.commit()
        db.refresh(p)
    if not db.scalar(select(M.Allergy).where(M.Allergy.patient_id == p.id)):
        db.add(M.Allergy(patient_id=p.id, substance="Penicillin", note="Rash reported"))
        db.commit()
    # curated interactions
    for a, b, sev, note in CURATED_INTERACTIONS:
        if not db.scalar(select(M.InteractionCurated).where(M.InteractionCurated.generic_a == a, M.InteractionCurated.generic_b == b)):
            db.add(M.InteractionCurated(generic_a=a, generic_b=b, severity=sev, note=note))
    db.commit()
    db.close()
    print(json.dumps({"demo_accounts": [{"username": u, "password": p, "role": r} for u, p, r, _ in DEMO]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
