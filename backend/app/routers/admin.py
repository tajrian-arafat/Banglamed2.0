"""M16 admin: users, data review, audit, modules."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import bad_request, not_found
from ..core.modules import module_manifest
from ..core.security import hash_password
from ..deps import require_role
from ..schemas import CreateStaffIn
from ..services.ids import doc_code

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.User).order_by(M.User.id)).all()
    return {"results": [{"id": u.id, "username": u.username, "role": u.role, "full_name": u.full_name,
                         "is_active": u.is_active, "account_type": u.account_type} for u in rows]}


@router.post("/users")
def create_staff(payload: CreateStaffIn, user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    if payload.role not in ("doctor", "hospital_admin", "system_admin"):
        raise bad_request("Invalid role")
    if db.scalar(select(M.User).where(M.User.username == payload.username)):
        raise bad_request("Username already taken")
    u = M.User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role,
               full_name=payload.full_name, account_type="personal")
    db.add(u)
    db.commit()
    db.refresh(u)
    if payload.role == "doctor":
        n = db.query(M.Doctor).count() + 1
        d = M.Doctor(doctor_code=doc_code(n), user_id=u.id, name=payload.full_name,
                     speciality_name=payload.speciality, bmdc_no=payload.bmdc_no, data_status="verified")
        db.add(d)
        db.commit()
    if payload.role == "hospital_admin" and payload.hospital_id:
        db.add(M.HospitalAdmin(user_id=u.id, hospital_id=payload.hospital_id))
        db.commit()
    log_action(db, user.id, "staff_create", "user", u.id, {"role": payload.role})
    return {"id": u.id, "role": u.role}


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    u = db.get(M.User, user_id)
    if not u:
        raise not_found("User not found")
    u.is_active = not u.is_active
    db.commit()
    log_action(db, user.id, "user_toggle", "user", u.id, {"active": u.is_active})
    return {"id": u.id, "is_active": u.is_active}


@router.get("/data/review")
def data_review(status: str = "unverified", limit: int = 50, user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.Brand).where(M.Brand.data_status == status).limit(limit)).all()
    return {"results": [{"id": b.id, "name": b.name, "form": b.form_name, "strength": b.strength_text,
                         "completeness": b.completeness, "data_status": b.data_status} for b in rows]}


@router.post("/data/brands/{brand_id}/verify")
def verify_brand(brand_id: int, user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    b = db.get(M.Brand, brand_id)
    if not b:
        raise not_found("Brand not found")
    b.data_status = "verified"
    db.commit()
    log_action(db, user.id, "brand_verify", "brand", b.id)
    return {"id": b.id, "data_status": b.data_status}


@router.get("/imports")
def imports(user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.ImportBatch).order_by(M.ImportBatch.id.desc()).limit(50)).all()
    return {"results": [{"id": b.id, "entity": b.entity, "source_name": b.source_name, "rows_in": b.rows_in,
                         "rows_loaded": b.rows_loaded, "rows_skipped": b.rows_skipped, "status": b.status,
                         "started_at": b.started_at.isoformat() if b.started_at else None} for b in rows]}


@router.get("/audit")
def audit(limit: int = 100, user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(M.AuditLog).order_by(M.AuditLog.id.desc()).limit(limit)).all()
    return {"results": [{"id": a.id, "ts": a.ts.isoformat(), "actor_id": a.actor_id, "action": a.action,
                         "entity": a.entity, "entity_id": a.entity_id, "meta": json.loads(a.meta_json or "{}")} for a in rows]}


@router.get("/modules")
def modules(user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    return module_manifest()
