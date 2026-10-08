#!/usr/bin/env python3
"""Seed the 30 role demo accounts and one versioned demo prescription.

Accounts created (idempotent):
  patient1 .. patient10     role=patient         (+ a Patient profile each)
  doctor1  .. doctor10      role=doctor          (+ a Doctor profile each)
  hospital1.. hospital10    role=hospital_admin  (+ a HospitalAdmin link each)

All 30 share ONE password (printed at the end of the run). The hash is
deterministic (``demo_password_hash``) so a rebuild reproduces it exactly.

It also writes one demonstration prescription with TWO saved versions, to
exercise the version-history path end to end.

Note on scope: this only ADDS accounts and the one demo prescription. It never
touches the catalog tables, so the seeded catalog stays byte-identical.

Development/demo only. Not medical advice.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app import models as M  # noqa: E402
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.security import demo_password_hash  # noqa: E402
from app.services.ids import doc_code, patient_code  # noqa: E402

SHARED_PASSWORD = "Medic@2026"
N = 10

SPECIALITIES = ["Medicine", "Cardiology", "Neurology", "Paediatrics", "Orthopaedics",
                "Dermatology", "Gynaecology", "ENT", "Ophthalmology", "Psychiatry"]


def _free_hospitals(db, count: int) -> list[M.Hospital]:
    """Active facilities, ordered for a stable assignment across rebuilds."""
    rows = db.scalars(
        select(M.Hospital)
        .where(func.coalesce(M.Hospital.data_status, "").notin_(("rejected", "duplicate")))
        .order_by(M.Hospital.id)
        .limit(count)
    ).all()
    return list(rows)


def main() -> int:
    init_db()
    db = SessionLocal()
    created = {"patient": [], "doctor": [], "hospital_admin": []}

    def _user(username: str, role: str, full_name: str) -> M.User:
        u = db.scalar(select(M.User).where(M.User.username == username))
        if not u:
            u = M.User(username=username, password_hash=demo_password_hash(username, SHARED_PASSWORD),
                       role=role, full_name=full_name, account_type="personal")
            db.add(u)
            db.commit()
            db.refresh(u)
        return u

    # ---- 10 patients
    for i in range(1, N + 1):
        uname = f"patient{i}"
        u = _user(uname, "patient", f"Patient {i}")
        if not db.scalar(select(M.Patient).where(M.Patient.account_id == u.id)):
            n = (db.scalar(select(func.count()).select_from(M.Patient)) or 0) + 1
            db.add(M.Patient(patient_code=patient_code(n), account_id=u.id, full_name=u.full_name,
                             relation="self", sex="male" if i % 2 else "female",
                             dob=f"{1975 + i}-0{(i % 9) + 1}-1{i % 9}",
                             blood_group=["O+", "A+", "B+", "AB+"][i % 4]))
            db.commit()
        created["patient"].append(uname)

    # ---- 10 doctors
    for i in range(1, N + 1):
        uname = f"doctor{i}"
        spec = SPECIALITIES[(i - 1) % len(SPECIALITIES)]
        u = _user(uname, "doctor", f"Dr. Demo {i}")
        d = db.scalar(select(M.Doctor).where(M.Doctor.user_id == u.id))
        if not d:
            n = (db.scalar(select(func.count()).select_from(M.Doctor)) or 0) + 1
            d = M.Doctor(doctor_code=doc_code(n), user_id=u.id, name=u.full_name,
                         speciality_name=spec, bmdc_no=f"BMDC-{100000 + i}",
                         qualifications=f"MBBS, FCPS ({spec})",
                         designation=f"Consultant, {spec}", district_name="Dhaka", city="Dhaka",
                         data_status="verified")
            db.add(d)
            db.commit()
        created["doctor"].append(uname)

    # ---- 10 hospital admins, each linked to its own facility
    hospitals = _free_hospitals(db, N)
    if len(hospitals) < N:
        print(json.dumps({"error": f"only {len(hospitals)} linkable hospitals"}))
        db.close()
        return 1
    for i in range(1, N + 1):
        uname = f"hospital{i}"
        h = hospitals[i - 1]
        u = _user(uname, "hospital_admin", h.name)
        if not db.scalar(select(M.HospitalAdmin).where(M.HospitalAdmin.user_id == u.id)):
            db.add(M.HospitalAdmin(user_id=u.id, hospital_id=h.id))
            db.commit()
        created["hospital_admin"].append(uname)

    # ---- one versioned demo prescription (doctor1 -> patient1)
    doc1 = db.scalar(select(M.Doctor).join(M.User, M.User.id == M.Doctor.user_id).where(M.User.username == "doctor1"))
    pat1 = db.scalar(select(M.Patient).join(M.User, M.User.id == M.Patient.account_id).where(M.User.username == "patient1"))
    h1 = hospitals[0]
    if doc1 and pat1:
        rx = db.scalar(select(M.Prescription).where(M.Prescription.doctor_id == doc1.id, M.Prescription.patient_id == pat1.id))
        if not rx:
            from app.routers.prescriptions import _signable_payload  # noqa: E402
            from app.core.security import sign_content  # noqa: E402
            from app.services.ids import public_token, rx_code  # noqa: E402
            from app.models import build_epoch  # noqa: E402

            # Fixed clock during a deterministic build, so issued_at (and hence the
            # signature) is identical on every rebuild.
            now = (build_epoch() or datetime.now(timezone.utc)).replace(tzinfo=None)
            # Stable keys: the token/code must be identical on every rebuild yet
            # unique across rows (see app/services/ids.py).
            rx = M.Prescription(rx_code=rx_code(now.year, key="demo-rx-1"), public_token=public_token(key="demo-rx-1"),
                                doctor_id=doc1.id, hospital_id=h1.id, patient_id=pat1.id,
                                diagnosis="Acute pharyngitis", chief_complaints="Sore throat, fever 2 days",
                                advice="Warm saline gargle, rest, review in 5 days.",
                                issued_at=now - timedelta(days=3), status="draft")
            db.add(rx)
            db.commit()
            db.refresh(rx)
            # v1
            from app.services.dosage import format_dosage  # noqa: E402
            dose1 = {"slots": {"morning": 1, "night": 1}, "unit": "tablet", "meal": "after",
                     "duration": {"value": 5, "unit": "day"}}
            db.add(M.PrescriptionItem(rx_id=rx.id, brand_id=None, generic_id=None,
                                      free_text_name="Tab. Paracetamol 500 mg", form="Tablet",
                                      strength="500 mg", dose_json=json.dumps(dose1),
                                      bn_dosage_text=format_dosage(dose1)))
            db.commit()
            snap1 = _signable_payload(db, rx)
            ch1, sg1 = sign_content(snap1)
            db.add(M.PrescriptionVersion(rx_id=rx.id, version_no=1,
                                         snapshot_json=json.dumps(snap1, ensure_ascii=False, sort_keys=True),
                                         content_hash=ch1, signature=sg1, reason="initial",
                                         created_by=doc1.user_id))
            rx.content_hash, rx.signature, rx.status = ch1, sg1, "finalized"
            db.commit()
            # v2 (an edit: adds an antibiotic; v1 is preserved untouched)
            dose2 = {"slots": {"morning": 1, "night": 1}, "unit": "tablet", "meal": "after",
                     "duration": {"value": 7, "unit": "day"}}
            db.add(M.PrescriptionItem(rx_id=rx.id, brand_id=None, generic_id=None,
                                      free_text_name="Cap. Amoxicillin 500 mg", form="Capsule",
                                      strength="500 mg", dose_json=json.dumps(dose2),
                                      bn_dosage_text=format_dosage(dose2)))
            db.commit()
            snap2 = _signable_payload(db, rx)
            ch2, sg2 = sign_content(snap2)
            db.add(M.PrescriptionVersion(rx_id=rx.id, version_no=2,
                                         snapshot_json=json.dumps(snap2, ensure_ascii=False, sort_keys=True),
                                         content_hash=ch2, signature=sg2, reason="added antibiotic",
                                         created_by=doc1.user_id))
            rx.content_hash, rx.signature = ch2, sg2
            db.commit()

    db.close()
    print(json.dumps({
        "shared_password": SHARED_PASSWORD,
        "accounts": created,
        "counts": {k: len(v) for k, v in created.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
