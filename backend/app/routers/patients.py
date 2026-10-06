"""M7 patient profiles & records (owner-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import forbidden, not_found
from ..deps import get_current_user
from ..schemas import AllergyIn, PatientIn
from ..services.ids import patient_code

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _own(db: Session, user: M.User, patient_id: int) -> M.Patient:
    p = db.get(M.Patient, patient_id)
    if not p:
        raise not_found("Patient not found")
    if p.account_id != user.id and user.role not in ("system_admin",):
        raise forbidden("Not your patient profile")
    return p


@router.get("")
def list_patients(user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.Patient).where(M.Patient.account_id == user.id)).all()
    return {"results": [
        {"id": p.id, "patient_code": p.patient_code, "full_name": p.full_name, "relation": p.relation,
         "sex": p.sex, "dob": p.dob, "blood_group": p.blood_group, "is_pregnant": p.is_pregnant,
         "is_lactating": p.is_lactating} for p in rows]}


@router.post("")
def create_patient(payload: PatientIn, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(M.Patient).count() + 1
    p = M.Patient(patient_code=patient_code(n), account_id=user.id, **payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, user.id, "patient_create", "patient", p.id)
    return {"id": p.id, "patient_code": p.patient_code}


@router.get("/{patient_id}")
def get_patient(patient_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, patient_id)
    allergies = db.scalars(select(M.Allergy).where(M.Allergy.patient_id == p.id)).all()
    return {
        "id": p.id, "patient_code": p.patient_code, "full_name": p.full_name, "dob": p.dob, "sex": p.sex,
        "relation": p.relation, "blood_group": p.blood_group, "is_pregnant": p.is_pregnant,
        "is_lactating": p.is_lactating, "phone": p.phone,
        "allergies": [{"id": a.id, "substance": a.substance, "note": a.note} for a in allergies],
    }


@router.post("/{patient_id}/allergies")
def add_allergy(patient_id: int, payload: AllergyIn, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, patient_id)
    a = M.Allergy(patient_id=p.id, substance=payload.substance, note=payload.note)
    db.add(a)
    db.commit()
    log_action(db, user.id, "allergy_add", "patient", p.id)
    return {"id": a.id}


@router.delete("/{patient_id}/allergies/{allergy_id}")
def del_allergy(patient_id: int, allergy_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, patient_id)
    a = db.get(M.Allergy, allergy_id)
    if a and a.patient_id == p.id:
        db.delete(a)
        db.commit()
    return {"ok": True}
