"""M15 hospital analytics (hospital_admin scoped)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..core.errors import forbidden
from ..deps import require_role

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _hospital_ids(db: Session, user: M.User) -> list[int]:
    if user.role == "system_admin":
        return [h.id for h in db.scalars(select(M.Hospital)).all()]
    rows = db.scalars(select(M.HospitalAdmin).where(M.HospitalAdmin.user_id == user.id)).all()
    return [r.hospital_id for r in rows]


@router.get("/hospital")
def hospital_analytics(user: M.User = Depends(require_role("hospital_admin", "system_admin")), db: Session = Depends(get_db)):
    hids = _hospital_ids(db, user)
    if not hids:
        raise forbidden("No hospital linked to this account")
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    rx_count = db.scalar(select(func.count()).select_from(M.Prescription).where(
        M.Prescription.hospital_id.in_(hids), M.Prescription.issued_at >= since)) or 0
    total_rx = db.scalar(select(func.count()).select_from(M.Prescription).where(M.Prescription.hospital_id.in_(hids))) or 0
    # top medicines
    top = db.execute(
        select(M.PrescriptionItem.brand_id, func.count().label("n"))
        .join(M.Prescription, M.Prescription.id == M.PrescriptionItem.rx_id)
        .where(M.Prescription.hospital_id.in_(hids))
        .group_by(M.PrescriptionItem.brand_id).order_by(func.count().desc()).limit(10)
    ).all()
    top_meds = []
    for brand_id, n in top:
        b = db.get(M.Brand, brand_id) if brand_id else None
        top_meds.append({"brand_id": brand_id, "name": b.name if b else "—", "count": n})
    # top tests
    top_tests = db.execute(
        select(M.PrescriptionTest.test_id, func.count().label("n"))
        .join(M.Prescription, M.Prescription.id == M.PrescriptionTest.rx_id)
        .where(M.Prescription.hospital_id.in_(hids))
        .group_by(M.PrescriptionTest.test_id).order_by(func.count().desc()).limit(10)
    ).all()
    top_test_rows = []
    for tid, n in top_tests:
        t = db.get(M.LabTest, tid) if tid else None
        top_test_rows.append({"test_id": tid, "name": t.name if t else "—", "count": n})
    # doctor activity
    doc_act = db.execute(
        select(M.Prescription.doctor_id, func.count().label("n"))
        .where(M.Prescription.hospital_id.in_(hids))
        .group_by(M.Prescription.doctor_id).order_by(func.count().desc()).limit(10)
    ).all()
    doctors = []
    for did, n in doc_act:
        d = db.get(M.Doctor, did) if did else None
        doctors.append({"doctor_id": did, "name": d.name if d else "—", "count": n})
    # daily trend (last 14 days)
    trend = []
    for i in range(13, -1, -1):
        day = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).date()
        n = db.scalar(select(func.count()).select_from(M.Prescription).where(
            M.Prescription.hospital_id.in_(hids),
            func.date(M.Prescription.issued_at) == day.isoformat())) or 0
        trend.append({"date": day.isoformat(), "count": n})
    return {"hospitals": hids, "rx_last_30d": rx_count, "rx_total": total_rx,
            "top_medicines": top_meds, "top_tests": top_test_rows, "doctor_activity": doctors, "trend": trend}


@router.get("/system")
def system_analytics(user: M.User = Depends(require_role("system_admin")), db: Session = Depends(get_db)):
    def c(model):
        return db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "counts": {
            "brands": c(M.Brand), "generics": c(M.Generic), "companies": c(M.Company),
            "indications": c(M.Indication), "dosage_forms": c(M.DosageForm), "drug_classes": c(M.DrugClass),
            "doctors": c(M.Doctor), "hospitals": c(M.Hospital), "tests": c(M.LabTest),
            "users": c(M.User), "prescriptions": c(M.Prescription), "appointments": c(M.Appointment),
        },
        "data_status": {
            "unverified": db.scalar(select(func.count()).select_from(M.Brand).where(M.Brand.data_status == "unverified")) or 0,
            "verified": db.scalar(select(func.count()).select_from(M.Brand).where(M.Brand.data_status == "verified")) or 0,
        },
    }
