"""M5 prescriptions + M6 safety + Bangla dosage + QR + signature."""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone

import qrcode
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import bad_request, forbidden, not_found
from ..deps import get_current_user, require_role
from ..core.security import sign_content, verify_signature
from ..schemas import PrescriptionIn, SafetyCheckIn
from ..services.dosage import format_dosage
from ..services.ids import public_token, rx_code
from ..services.safety import check_prescription

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


def _doctor_for_user(db: Session, user: M.User) -> M.Doctor | None:
    return db.scalar(select(M.Doctor).where(M.Doctor.user_id == user.id))


def _resolve_items(db: Session, items) -> list[dict]:
    out = []
    for it in items:
        brand = db.get(M.Brand, it.brand_id) if it.brand_id else None
        gid = it.generic_id or (brand.generic_id if brand else None)
        out.append({
            "brand_id": it.brand_id,
            "generic_id": gid,
            "form": it.form or (brand.form_name if brand else None),
            "strength": it.strength or (brand.strength_text if brand else None),
            "name": it.free_text_name or (brand.name if brand else None),
            "duration_days": (it.dose.duration.get("value") if it.dose and it.dose.duration else None),
        })
    return out


@router.post("/safety-check")
def safety_check(payload: SafetyCheckIn, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    patient = db.get(M.Patient, payload.patient_id)
    if not patient:
        raise not_found("Patient not found")
    items = _resolve_items(db, payload.items)
    warnings = check_prescription(db, patient, items)
    return {"warnings": warnings, "count": len(warnings)}


@router.post("")
def create_prescription(payload: PrescriptionIn, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    doctor = _doctor_for_user(db, user)
    if not doctor:
        raise bad_request("No doctor profile linked to this account")
    patient = db.get(M.Patient, payload.patient_id)
    if not patient:
        raise not_found("Patient not found")
    items = _resolve_items(db, payload.items)
    warnings = check_prescription(db, patient, items)
    critical = [w for w in warnings if w["severity"] == "critical"]
    ack_codes = {a.get("code") for a in payload.acknowledgements}
    unacked = [w for w in critical if w["code"] not in ack_codes]
    if unacked:
        raise bad_request("Critical safety warnings must be acknowledged", details=unacked)

    year = datetime.now(timezone.utc).year
    rx = M.Prescription(
        rx_code=rx_code(year), public_token=public_token(), doctor_id=doctor.id,
        hospital_id=payload.hospital_id, patient_id=patient.id, appointment_id=payload.appointment_id,
        diagnosis=payload.diagnosis, chief_complaints=payload.chief_complaints,
        notes=payload.notes, advice=payload.advice, status="draft",
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)
    for it in payload.items:
        brand = db.get(M.Brand, it.brand_id) if it.brand_id else None
        dose = it.dose.model_dump() if it.dose else {}
        bn = format_dosage(dose) if dose else None
        db.add(M.PrescriptionItem(
            rx_id=rx.id, brand_id=it.brand_id, generic_id=it.generic_id or (brand.generic_id if brand else None),
            free_text_name=it.free_text_name, form=it.form or (brand.form_name if brand else None),
            strength=it.strength or (brand.strength_text if brand else None),
            dose_json=json.dumps(dose, ensure_ascii=False), bn_dosage_text=bn, instructions=it.instructions,
        ))
    for t in payload.tests:
        db.add(M.PrescriptionTest(rx_id=rx.id, test_id=t.test_id, free_text_name=t.free_text_name, note=t.note))
    for a in payload.acknowledgements:
        db.add(M.SafetyAcknowledgement(rx_id=rx.id, code=a.get("code", ""), reason=a.get("reason"), doctor_id=doctor.id))
    db.commit()
    log_action(db, user.id, "prescription_create", "prescription", rx.rx_code, {"patient": patient.patient_code})
    return {"id": rx.id, "rx_code": rx.rx_code, "status": rx.status, "warnings": warnings}


def _signable_payload(db: Session, rx: M.Prescription) -> dict:
    """Canonical payload for the digital seal. Excludes volatile fields (status)."""
    payload = _rx_payload(db, rx)
    payload.pop("status", None)
    return payload


def _rx_payload(db: Session, rx: M.Prescription) -> dict:
    items = db.scalars(select(M.PrescriptionItem).where(M.PrescriptionItem.rx_id == rx.id)).all()
    tests = db.scalars(select(M.PrescriptionTest).where(M.PrescriptionTest.rx_id == rx.id)).all()
    doctor = db.get(M.Doctor, rx.doctor_id)
    patient = db.get(M.Patient, rx.patient_id)
    return {
        "rx_code": rx.rx_code,
        "issued_at": rx.issued_at.isoformat() if rx.issued_at else None,
        "status": rx.status,
        "doctor": {"id": doctor.id, "name": doctor.name, "bmdc_no": doctor.bmdc_no,
                   "speciality": doctor.speciality_name, "qualifications": doctor.qualifications} if doctor else None,
        "patient": {"id": patient.id, "patient_code": patient.patient_code, "full_name": patient.full_name,
                    "sex": patient.sex, "dob": patient.dob} if patient else None,
        "diagnosis": rx.diagnosis, "chief_complaints": rx.chief_complaints, "notes": rx.notes, "advice": rx.advice,
        "items": [{"brand_id": i.brand_id, "name": i.free_text_name or (db.get(M.Brand, i.brand_id).name if i.brand_id and db.get(M.Brand, i.brand_id) else None),
                   "form": i.form, "strength": i.strength, "dose": json.loads(i.dose_json or "{}"),
                   "bn_dosage_text": i.bn_dosage_text, "instructions": i.instructions} for i in items],
        "tests": [{"test_id": t.test_id, "name": t.free_text_name or (db.get(M.LabTest, t.test_id).name if t.test_id and db.get(M.LabTest, t.test_id) else None),
                   "note": t.note} for t in tests],
    }


@router.get("/{rx_id}")
def get_prescription(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    patient = db.get(M.Patient, rx.patient_id)
    doctor = _doctor_for_user(db, user)
    allowed = (
        user.role == "system_admin"
        or (patient and patient.account_id == user.id)
        or (doctor and doctor.id == rx.doctor_id)
    )
    if not allowed:
        raise forbidden("Not permitted to view this prescription")
    log_action(db, user.id, "prescription_view", "prescription", rx.rx_code)
    return _rx_payload(db, rx)


@router.post("/{rx_id}/finalize")
def finalize(rx_id: int, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    doctor = _doctor_for_user(db, user)
    if user.role != "system_admin" and (not doctor or doctor.id != rx.doctor_id):
        raise forbidden("Only the issuing doctor can finalize")
    payload = _signable_payload(db, rx)
    ch, sig = sign_content(payload)
    rx.content_hash = ch
    rx.signature = sig
    rx.status = "finalized"
    db.commit()
    log_action(db, user.id, "prescription_finalize", "prescription", rx.rx_code)
    return {"rx_code": rx.rx_code, "status": rx.status, "content_hash": ch, "signature": sig}


@router.post("/{rx_id}/void")
def void_rx(rx_id: int, body: dict, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    doctor = _doctor_for_user(db, user)
    if user.role != "system_admin" and (not doctor or doctor.id != rx.doctor_id):
        raise forbidden("Only the issuing doctor can void")
    rx.status = "void"
    rx.void_reason = body.get("reason", "")
    db.commit()
    log_action(db, user.id, "prescription_void", "prescription", rx.rx_code, {"reason": rx.void_reason})
    return {"rx_code": rx.rx_code, "status": rx.status}


@router.get("/{rx_id}/qr")
def rx_qr(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    patient = db.get(M.Patient, rx.patient_id)
    doctor = _doctor_for_user(db, user)
    if not (user.role == "system_admin" or (patient and patient.account_id == user.id) or (doctor and doctor.id == rx.doctor_id)):
        raise forbidden("Not permitted")
    url = f"/rx/{rx.public_token}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"qr_png_base64": b64, "payload": url, "rx_code": rx.rx_code}


@router.get("/{rx_id}/verify")
def verify_rx(rx_id: int, db: Session = Depends(get_db)):
    """Public integrity check: recompute the seal and compare."""
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if rx.status != "finalized" or not rx.content_hash:
        return {"verified": False, "reason": "not_finalized"}
    payload = _signable_payload(db, rx)
    ok = verify_signature(payload, rx.content_hash, rx.signature or "")
    return {"verified": ok, "rx_code": rx.rx_code, "content_hash": rx.content_hash}


@router.get("/public/{token}")
def public_rx(token: str, db: Session = Depends(get_db)):
    """Read-only public view reached by scanning the QR (no login)."""
    rx = db.scalar(select(M.Prescription).where(M.Prescription.public_token == token))
    if not rx:
        raise not_found("Prescription not found")
    payload = _rx_payload(db, rx)
    payload["verified"] = bool(rx.content_hash) and verify_signature(_signable_payload(db, rx), rx.content_hash, rx.signature or "")
    payload["disclaimer"] = "Informational only. Not medical advice."
    return payload
