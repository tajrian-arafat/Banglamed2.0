"""M11 appointments: serial booking with concurrency safety."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import AppError, bad_request, forbidden, not_found
from ..deps import get_current_user, require_role
from ..schemas import BookIn, ScheduleIn
from ..services.ids import apt_code

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


@router.post("/schedules")
def create_schedule(payload: ScheduleIn, user: M.User = Depends(require_role("doctor", "hospital_admin", "system_admin")), db: Session = Depends(get_db)):
    s = M.DoctorSchedule(**payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id}


@router.get("/schedules")
def list_schedules(doctor_id: int | None = None, date: str | None = None, db: Session = Depends(get_db)):
    stmt = select(M.DoctorSchedule)
    if doctor_id:
        stmt = stmt.where(M.DoctorSchedule.doctor_id == doctor_id)
    if date:
        stmt = stmt.where(M.DoctorSchedule.date == date)
    rows = db.scalars(stmt.order_by(M.DoctorSchedule.date)).all()
    out = []
    for s in rows:
        booked = db.scalar(select(func.count()).select_from(M.Appointment).where(
            M.Appointment.schedule_id == s.id, M.Appointment.status != "cancelled"))
        d = db.get(M.Doctor, s.doctor_id)
        out.append({"id": s.id, "doctor_id": s.doctor_id, "doctor_name": d.name if d else None, "date": s.date,
                    "total_serials": s.total_serials, "booked": booked, "available": s.total_serials - booked,
                    "session_start": s.session_start, "session_end": s.session_end,
                    "fee": float(s.fee) if s.fee else None, "booking_opens_at": s.booking_opens_at,
                    "booking_closes_at": s.booking_closes_at})
    return {"results": out}


@router.get("/schedules/{schedule_id}/serials")
def serials(schedule_id: int, db: Session = Depends(get_db)):
    s = db.get(M.DoctorSchedule, schedule_id)
    if not s:
        raise not_found("Schedule not found")
    taken = {a.serial_no for a in db.scalars(select(M.Appointment).where(
        M.Appointment.schedule_id == s.id, M.Appointment.status != "cancelled")).all()}
    return {"schedule_id": s.id, "total_serials": s.total_serials,
            "taken": sorted(taken), "available": [n for n in range(1, s.total_serials + 1) if n not in taken]}


@router.post("/book")
def book(payload: BookIn, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(M.DoctorSchedule, payload.schedule_id)
    if not s:
        raise not_found("Schedule not found")
    patient = db.get(M.Patient, payload.patient_id)
    if not patient:
        raise not_found("Patient not found")
    if patient.account_id != user.id and user.role not in ("system_admin", "hospital_admin"):
        raise forbidden("Not your patient profile")
    # booking window
    now = datetime.now(timezone.utc)
    if s.booking_opens_at:
        try:
            if now < datetime.fromisoformat(s.booking_opens_at).replace(tzinfo=timezone.utc):
                raise bad_request("Booking has not opened yet")
        except ValueError:
            pass
    if s.booking_closes_at:
        try:
            if now > datetime.fromisoformat(s.booking_closes_at).replace(tzinfo=timezone.utc):
                raise bad_request("Booking has closed")
        except ValueError:
            pass
    # one appointment per patient per schedule
    existing = db.scalar(select(M.Appointment).where(
        M.Appointment.schedule_id == s.id, M.Appointment.patient_id == patient.id,
        M.Appointment.status != "cancelled"))
    if existing:
        raise bad_request("This patient already has a serial for this schedule", details={"serial_no": existing.serial_no})
    taken = {a.serial_no for a in db.scalars(select(M.Appointment).where(
        M.Appointment.schedule_id == s.id, M.Appointment.status != "cancelled")).all()}
    if payload.serial_no is not None:
        if payload.serial_no in taken:
            raise AppError("serial_taken", "That serial is already taken", 409)
        serial = payload.serial_no
    else:
        serial = next((n for n in range(1, s.total_serials + 1) if n not in taken), None)
        if serial is None:
            raise AppError("full", "No serials available for this schedule", 409)
    apt = M.Appointment(apt_code=apt_code(now.year), schedule_id=s.id, patient_id=patient.id, serial_no=serial)
    db.add(apt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("serial_taken", "That serial was just taken. Please pick another.", 409)
    db.refresh(apt)
    log_action(db, user.id, "appointment_book", "appointment", apt.apt_code, {"serial": serial})
    return {"id": apt.id, "apt_code": apt.apt_code, "serial_no": serial, "status": apt.status}


@router.get("/mine")
def my_appointments(user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    pts = db.scalars(select(M.Patient).where(M.Patient.account_id == user.id)).all()
    ids = [p.id for p in pts]
    if not ids:
        return {"results": []}
    rows = db.scalars(select(M.Appointment).where(M.Appointment.patient_id.in_(ids)).order_by(M.Appointment.created_at.desc())).all()
    out = []
    for a in rows:
        s = db.get(M.DoctorSchedule, a.schedule_id)
        d = db.get(M.Doctor, s.doctor_id) if s else None
        out.append({"id": a.id, "apt_code": a.apt_code, "serial_no": a.serial_no, "status": a.status,
                    "date": s.date if s else None, "doctor_name": d.name if d else None,
                    "session_start": s.session_start if s else None, "fee": float(s.fee) if s and s.fee else None})
    return {"results": out}


@router.post("/{apt_id}/cancel")
def cancel(apt_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(M.Appointment, apt_id)
    if not a:
        raise not_found("Appointment not found")
    p = db.get(M.Patient, a.patient_id)
    if not p or (p.account_id != user.id and user.role not in ("system_admin", "hospital_admin")):
        raise forbidden("Not permitted")
    a.status = "cancelled"
    db.commit()
    return {"ok": True, "status": a.status}
