"""M14 doctor workspace: profile, patients, access codes, copy-from-previous."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.access import access_rules
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import bad_request, forbidden, not_found
from ..core.security import hash_password, verify_password
from ..deps import require_role
from ..services.ids import doc_code

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


def _doctor(db: Session, user: M.User) -> M.Doctor:
    d = db.scalar(select(M.Doctor).where(M.Doctor.user_id == user.id))
    if not d:
        raise bad_request("No doctor profile linked to this account")
    return d


@router.get("/profile")
def profile(user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    d = _doctor(db, user)
    return {"id": d.id, "doctor_code": d.doctor_code, "name": d.name, "speciality": d.speciality_name,
            "qualifications": d.qualifications, "bmdc_no": d.bmdc_no, "designation": d.designation,
            "district": d.district_name, "signature_image": d.signature_image}


@router.put("/profile")
def update_profile(body: dict, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    d = _doctor(db, user)
    for field in ("name", "qualifications", "bmdc_no", "designation", "signature_image"):
        if field in body:
            setattr(d, field, body[field])
    db.commit()
    return {"ok": True}


@router.get("/patients")
def patients(q: str = "", district: str = "", limit: int = 50, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    """Patients this doctor has seen (via prescriptions) + searchable directory."""
    d = _doctor(db, user)
    seen_ids = {p for p in db.scalars(select(M.Prescription.patient_id).where(M.Prescription.doctor_id == d.id)).all()}
    stmt = select(M.Patient)
    if q:
        stmt = stmt.where(M.Patient.full_name.ilike(f"%{q}%"))
    rows = db.scalars(stmt.limit(limit)).all()
    out = []
    for p in rows:
        out.append({"id": p.id, "patient_code": p.patient_code, "full_name": p.full_name, "sex": p.sex,
                    "dob": p.dob, "seen_by_me": p.id in seen_ids})
    return {"results": out}


@router.get("/patients/{patient_id}/history")
def patient_history(patient_id: int, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    d = _doctor(db, user)
    p = db.get(M.Patient, patient_id)
    if not p:
        raise not_found("Patient not found")
    rxs = db.scalars(select(M.Prescription).where(M.Prescription.patient_id == p.id).order_by(M.Prescription.issued_at.desc())).all()
    return {"patient": {"id": p.id, "patient_code": p.patient_code, "full_name": p.full_name, "sex": p.sex, "dob": p.dob},
            "prescriptions": [{"id": rx.id, "rx_code": rx.rx_code, "date": rx.issued_at.isoformat(),
                               "diagnosis": rx.diagnosis, "status": rx.status,
                               "by_me": rx.doctor_id == d.id} for rx in rxs]}


@router.get("/patients/{patient_id}/copy-from/{rx_id}")
def copy_from(patient_id: int, rx_id: int, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    """Return a prior prescription's items as a draft payload for the writer."""
    rx = db.get(M.Prescription, rx_id)
    if not rx or rx.patient_id != patient_id:
        raise not_found("Prescription not found for this patient")
    items = db.scalars(select(M.PrescriptionItem).where(M.PrescriptionItem.rx_id == rx.id)).all()
    tests = db.scalars(select(M.PrescriptionTest).where(M.PrescriptionTest.rx_id == rx.id)).all()
    return {"source_rx": rx.rx_code, "diagnosis": rx.diagnosis, "advice": rx.advice,
            "items": [{"brand_id": i.brand_id, "generic_id": i.generic_id, "free_text_name": i.free_text_name,
                       "form": i.form, "strength": i.strength, "dose": json.loads(i.dose_json or "{}"),
                       "instructions": i.instructions} for i in items],
            "tests": [{"test_id": t.test_id, "free_text_name": t.free_text_name, "note": t.note} for t in tests]}


@router.post("/access-codes")
def create_access_code(body: dict, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    """Doctor issues a short code; patient shares it to grant temporary record access."""
    d = _doctor(db, user)
    patient_id = int(body["patient_id"])
    p = db.get(M.Patient, patient_id)
    if not p:
        raise not_found("Patient not found")
    rules = access_rules()
    code = "".join(secrets.choice("0123456789") for _ in range(rules.get("code_length", 6)))
    ac = M.AccessCode(patient_id=p.id, code_hash=hash_password(code),
                      expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=rules.get("code_valid_minutes", 15)))
    db.add(ac)
    db.commit()
    log_action(db, user.id, "access_code_create", "patient", p.patient_code)
    return {"code": code, "expires_in_minutes": rules.get("code_valid_minutes", 15)}


@router.post("/access-codes/redeem")
def redeem_access_code(body: dict, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    d = _doctor(db, user)
    code = str(body.get("code", ""))
    patient_id = int(body.get("patient_id", 0))
    rows = db.scalars(select(M.AccessCode).where(M.AccessCode.patient_id == patient_id, M.AccessCode.used_at.is_(None))).all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for ac in rows:
        if ac.expires_at < now:
            continue
        if verify_password(code, ac.code_hash):
            ac.used_at = now
            ac.used_by_doctor_id = d.id
            db.commit()
            log_action(db, user.id, "access_code_redeem", "patient", patient_id)
            return {"ok": True, "patient_id": patient_id}
    raise bad_request("Invalid or expired access code")
