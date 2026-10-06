"""M10 reminders."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..core.errors import forbidden, not_found
from ..deps import get_current_user
from ..schemas import ReminderIn

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


def _own(db: Session, user: M.User, patient_id: int) -> M.Patient:
    p = db.get(M.Patient, patient_id)
    if not p:
        raise not_found("Patient not found")
    if p.account_id != user.id and user.role != "system_admin":
        raise forbidden("Not your patient profile")
    return p


@router.get("")
def list_reminders(patient_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, patient_id)
    rows = db.scalars(select(M.Reminder).where(M.Reminder.patient_id == p.id)).all()
    out = []
    for r in rows:
        items = db.scalars(select(M.ReminderItem).where(M.ReminderItem.reminder_id == r.id)).all()
        out.append({"id": r.id, "title": r.title, "source": r.source, "is_active": r.is_active,
                    "items": [{"id": i.id, "medicine_name": i.medicine_name, "times": json.loads(i.times_json or "[]"),
                               "start_date": i.start_date, "end_date": i.end_date} for i in items]})
    return {"results": out}


@router.post("")
def create_reminder(payload: ReminderIn, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _own(db, user, payload.patient_id)
    r = M.Reminder(patient_id=p.id, source=payload.source, rx_id=payload.rx_id, title=payload.title)
    db.add(r)
    db.commit()
    db.refresh(r)
    for it in payload.items:
        db.add(M.ReminderItem(reminder_id=r.id, brand_id=it.get("brand_id"), medicine_name=it.get("medicine_name", ""),
                              times_json=json.dumps(it.get("times", [])), start_date=it.get("start_date"),
                              end_date=it.get("end_date")))
    db.commit()
    return {"id": r.id}


@router.post("/items/{item_id}/event")
def log_event(item_id: int, body: dict, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(M.ReminderItem, item_id)
    if not item:
        raise not_found("Reminder item not found")
    ev = M.ReminderEvent(item_id=item.id, due_at=datetime.now(timezone.utc), action=body.get("action", "taken"),
                         acted_at=datetime.now(timezone.utc))
    db.add(ev)
    db.commit()
    return {"id": ev.id, "action": ev.action}


@router.delete("/{reminder_id}")
def delete_reminder(reminder_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(M.Reminder, reminder_id)
    if r:
        p = db.get(M.Patient, r.patient_id)
        if p and (p.account_id == user.id or user.role == "system_admin"):
            db.query(M.ReminderItem).filter(M.ReminderItem.reminder_id == r.id).delete()
            db.delete(r)
            db.commit()
    return {"ok": True}
