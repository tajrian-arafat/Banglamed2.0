"""M7 records: history timeline, uploads, test records."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import bad_request, forbidden, not_found
from ..deps import get_current_user
from ..services.analysis import analyse
from ..services.interpreter import assess_quality, run_ocr

router = APIRouter(prefix="/api/records", tags=["records"])
settings = get_settings()


def _own_patient(db: Session, user: M.User, patient_id: int) -> M.Patient:
    p = db.get(M.Patient, patient_id)
    if not p:
        raise not_found("Patient not found")
    if p.account_id != user.id and user.role != "system_admin":
        raise forbidden("Not your patient profile")
    return p


@router.get("/{patient_id}/timeline")
def timeline(patient_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own_patient(db, user, patient_id)
    events = []
    rxs = db.scalars(select(M.Prescription).where(M.Prescription.patient_id == p.id).order_by(M.Prescription.issued_at.desc())).all()
    for rx in rxs:
        doctor = db.get(M.Doctor, rx.doctor_id)
        events.append({"type": "prescription", "id": rx.id, "rx_code": rx.rx_code, "date": rx.issued_at.isoformat(),
                       "title": f"Prescription by {doctor.name if doctor else 'doctor'}", "status": rx.status,
                       "diagnosis": rx.diagnosis})
    apts = db.scalars(select(M.Appointment).where(M.Appointment.patient_id == p.id)).all()
    for a in apts:
        s = db.get(M.DoctorSchedule, a.schedule_id)
        d = db.get(M.Doctor, s.doctor_id) if s else None
        events.append({"type": "appointment", "id": a.id, "apt_code": a.apt_code, "date": a.created_at.isoformat(),
                       "title": f"Appointment with {d.name if d else 'doctor'}", "status": a.status,
                       "serial_no": a.serial_no, "date_of_visit": s.date if s else None})
    trs = db.scalars(select(M.TestRecord).where(M.TestRecord.patient_id == p.id)).all()
    for t in trs:
        test = db.get(M.LabTest, t.test_id)
        events.append({"type": "test", "id": t.id, "date": t.performed_on or "", "title": f"Test: {test.name if test else ''}"})
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return {"patient": {"id": p.id, "patient_code": p.patient_code, "full_name": p.full_name}, "events": events}


@router.post("/{patient_id}/upload")
async def upload_rx(patient_id: int, file: UploadFile = File(...), user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own_patient(db, user, patient_id)
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise bad_request(f"File exceeds {settings.max_upload_mb} MB")
    if not (file.content_type or "").startswith("image/"):
        raise bad_request("Only image uploads are supported")
    quality = assess_quality(data)
    ocr_text, parsed = run_ocr(data, db)
    # Price and safety-check whatever was read, so the patient sees medicines,
    # tests, totals and the safety panel immediately — and gets the same payload
    # shape the manual-entry fallback produces.
    analysis = analyse(
        db, patient=p,
        medicines=[{"brand_id": m.get("brand_id"), "name": m.get("brand"),
                    "dose": m.get("dose"), "duration_days": (m.get("duration") or {}).get("value")}
                   for m in parsed.get("medicines", [])],
        tests=[{"test_id": t.get("test_id"), "name": t.get("name")}
               for t in parsed.get("tests", [])],
    )
    up = M.RxUpload(patient_id=p.id, image_path=None, quality_json=json.dumps(quality),
                    ocr_text=ocr_text, parsed_json=json.dumps(parsed, ensure_ascii=False), status="parsed")
    db.add(up)
    db.commit()
    log_action(db, user.id, "rx_upload", "patient", p.patient_code)
    return {"upload_id": up.id, "quality": quality, "ocr_text": ocr_text,
            "parsed": parsed, "analysis": analysis}


@router.get("/{patient_id}/uploads")
def list_uploads(patient_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own_patient(db, user, patient_id)
    rows = db.scalars(select(M.RxUpload).where(M.RxUpload.patient_id == p.id).order_by(M.RxUpload.created_at.desc())).all()
    return {"results": [{"id": u.id, "status": u.status, "quality": json.loads(u.quality_json or "{}"),
                         "parsed": json.loads(u.parsed_json or "{}"), "created_at": u.created_at.isoformat()} for u in rows]}


@router.post("/{patient_id}/tests")
def add_test_record(patient_id: int, body: dict, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own_patient(db, user, patient_id)
    tr = M.TestRecord(patient_id=p.id, test_id=int(body["test_id"]), rx_id=body.get("rx_id"),
                      performed_on=body.get("performed_on") or datetime.now(timezone.utc).date().isoformat())
    db.add(tr)
    db.commit()
    return {"id": tr.id}
