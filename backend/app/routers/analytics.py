"""M15 analytics — hospital_admin scoped to its own facility; system_admin sees all.

Visibility rules (explicit, enforced server-side):
  * ``hospital_admin``  → ONLY the facility/facilities linked to its account
                          (``hospital_admins`` rows). ``/hospital``,
                          ``/hospital/doctors`` and ``/hospitals-overview``
                          resolve their scope from that link, never from a
                          request parameter, so a hospital admin cannot widen
                          its own scope by editing a query string.
  * ``system_admin``    → every facility, plus the system-wide counters.

A doctor with a facility but no prescriptions must still appear in the doctor
roster — "who works here" and "who has prescribed lately" are different
questions, and only returning doctors with activity made the roster look empty
for a newly linked clinician.
"""
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
    """The facilities this account may see. Never trusts client input."""
    if user.role == "system_admin":
        return [h.id for h in db.scalars(select(M.Hospital).order_by(M.Hospital.id)).all()]
    rows = db.scalars(select(M.HospitalAdmin).where(M.HospitalAdmin.user_id == user.id)).all()
    return sorted({r.hospital_id for r in rows})


def _scoped_hids(db: Session, user: M.User, hospital_id: int | None) -> list[int]:
    """Resolve the scope for a request, honouring the account's own limits."""
    hids = _hospital_ids(db, user)
    if hospital_id is None:
        return hids
    if user.role != "system_admin" and hospital_id not in hids:
        # Explicit refusal rather than an empty (and misleading) result set.
        raise forbidden("Not permitted to view analytics for this facility")
    return [hospital_id]


@router.get("/hospital")
def hospital_analytics(user: M.User = Depends(require_role("hospital_admin", "system_admin")), db: Session = Depends(get_db)):
    hids = _hospital_ids(db, user)
    if not hids:
        raise forbidden("No hospital linked to this account")
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    rx_count = db.scalar(select(func.count()).select_from(M.Prescription).where(
        M.Prescription.hospital_id.in_(hids), M.Prescription.issued_at >= since)) or 0
    total_rx = db.scalar(select(func.count()).select_from(M.Prescription).where(M.Prescription.hospital_id.in_(hids))) or 0
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
    # Doctor activity — every doctor linked to the facility, including those with
    # no prescriptions yet (count 0), so the roster is truthful.
    doc_act = dict(db.execute(
        select(M.Prescription.doctor_id, func.count().label("n"))
        .where(M.Prescription.hospital_id.in_(hids))
        .group_by(M.Prescription.doctor_id)
    ).all())
    linked_ids = {r.doctor_id for r in db.scalars(
        select(M.DoctorAffiliation).where(M.DoctorAffiliation.hospital_id.in_(hids))
    ).all() if r.doctor_id}
    all_ids = sorted(set(doc_act) | linked_ids)
    doctors = []
    for did in all_ids:
        d = db.get(M.Doctor, did) if did else None
        doctors.append({"doctor_id": did, "name": d.name if d else "—",
                        "speciality": d.speciality_name if d else None,
                        "count": int(doc_act.get(did, 0))})
    doctors.sort(key=lambda x: (-x["count"], x["name"] or ""))
    trend = []
    for i in range(13, -1, -1):
        day = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).date()
        n = db.scalar(select(func.count()).select_from(M.Prescription).where(
            M.Prescription.hospital_id.in_(hids),
            func.date(M.Prescription.issued_at) == day.isoformat())) or 0
        trend.append({"date": day.isoformat(), "count": n})
    return {"hospitals": hids, "rx_last_30d": rx_count, "rx_total": total_rx,
            "doctor_count": len(doctors),
            "top_medicines": top_meds, "top_tests": top_test_rows,
            "doctor_activity": doctors, "trend": trend}


@router.get("/hospital/doctors")
def hospital_doctors(hospital_id: int | None = None, user: M.User = Depends(require_role("hospital_admin", "system_admin")), db: Session = Depends(get_db)):
    """All doctors at one facility, with per-doctor prescription analytics.

    A hospital admin may pass ``hospital_id`` only for a facility it is linked
    to (see ``_scoped_hids``); a system admin may pass any id or omit it to get
    every facility. Each doctor carries its affiliation source and prescription
    counts so the roster is auditable.
    """
    hids = _scoped_hids(db, user, hospital_id)
    if not hids:
        raise forbidden("No hospital linked to this account")
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)

    # Affiliation may come from the doctor_affiliations table and/or from a
    # prescription written at the facility; union both so nothing is missed.
    aff_rows = db.execute(
        select(M.DoctorAffiliation.hospital_id, M.DoctorAffiliation.doctor_id)
        .where(M.DoctorAffiliation.hospital_id.in_(hids))
    ).all()
    rx_rows = db.execute(
        select(M.Prescription.hospital_id, M.Prescription.doctor_id,
               func.count().label("n"), func.max(M.Prescription.issued_at).label("last"))
        .where(M.Prescription.hospital_id.in_(hids))
        .group_by(M.Prescription.hospital_id, M.Prescription.doctor_id)
    ).all()

    # doctor_id -> {hospital_id, counts}
    per_doc: dict[int, dict] = {}
    for hid, did in aff_rows:
        if not did:
            continue
        entry = per_doc.setdefault(did, {"doctor_id": did, "hospital_ids": set(),
                                         "rx_total": 0, "rx_last_30d": 0, "last_rx": None,
                                         "via": set()})
        entry["hospital_ids"].add(hid)
        entry["via"].add("affiliation")
    for hid, did, n, last in rx_rows:
        if not did:
            continue
        entry = per_doc.setdefault(did, {"doctor_id": did, "hospital_ids": set(),
                                         "rx_total": 0, "rx_last_30d": 0, "last_rx": None,
                                         "via": set()})
        entry["hospital_ids"].add(hid)
        entry["rx_total"] += int(n)
        if last and (entry["last_rx"] is None or last > entry["last_rx"]):
            entry["last_rx"] = last
        entry["via"].add("prescription")
    # 30-day counts, per doctor (scoped to the visible facilities)
    recent = dict(db.execute(
        select(M.Prescription.doctor_id, func.count().label("n"))
        .where(M.Prescription.hospital_id.in_(hids), M.Prescription.issued_at >= since)
        .group_by(M.Prescription.doctor_id)
    ).all())

    results = []
    for did, e in per_doc.items():
        d = db.get(M.Doctor, did)
        if not d:
            continue
        hosp_names = []
        for hid in sorted(e["hospital_ids"]):
            h = db.get(M.Hospital, hid)
            if h:
                hosp_names.append({"id": h.id, "name": h.name, "district": h.district_name})
        results.append({
            "doctor_id": d.id, "name": d.name, "doctor_code": d.doctor_code,
            "speciality": d.speciality_name, "bmdc_no": d.bmdc_no,
            "district": d.district_name, "designation": d.designation,
            "hospitals": hosp_names,
            "rx_total": e["rx_total"],
            "rx_last_30d": int(recent.get(did, 0)),
            "last_rx": e["last_rx"].isoformat() if e["last_rx"] else None,
            "affiliation_source": sorted(e["via"]),
        })
    results.sort(key=lambda x: (-x["rx_total"], x["name"] or ""))
    return {"hospitals": hids, "count": len(results), "results": results}


@router.get("/hospitals-overview")
def hospitals_overview(user: M.User = Depends(require_role("hospital_admin", "system_admin")), db: Session = Depends(get_db)):
    """Per-facility analytics across every facility in scope.

    For a hospital admin this is its own facility only; for a system admin it is
    all of them — the "all hospital analytics across facilities" view.
    """
    hids = _hospital_ids(db, user)
    if not hids:
        raise forbidden("No hospital linked to this account")
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    rx_all = dict(db.execute(
        select(M.Prescription.hospital_id, func.count().label("n"))
        .where(M.Prescription.hospital_id.in_(hids)).group_by(M.Prescription.hospital_id)
    ).all())
    rx_30 = dict(db.execute(
        select(M.Prescription.hospital_id, func.count().label("n"))
        .where(M.Prescription.hospital_id.in_(hids), M.Prescription.issued_at >= since)
        .group_by(M.Prescription.hospital_id)
    ).all())
    doc_all = dict(db.execute(
        select(M.Prescription.hospital_id, func.count(func.distinct(M.Prescription.doctor_id)))
        .where(M.Prescription.hospital_id.in_(hids)).group_by(M.Prescription.hospital_id)
    ).all())
    aff_all = dict(db.execute(
        select(M.DoctorAffiliation.hospital_id, func.count())
        .where(M.DoctorAffiliation.hospital_id.in_(hids)).group_by(M.DoctorAffiliation.hospital_id)
    ).all())
    facilities = []
    # Hospital stores division_id, not a division name; resolve the labels once.
    division_names = dict(db.execute(select(M.GeoDivision.id, M.GeoDivision.name)).all())
    for hid in hids:
        h = db.get(M.Hospital, hid)
        if not h:
            continue
        facilities.append({
            "hospital_id": h.id, "name": h.name, "district": h.district_name,
            "division": division_names.get(h.division_id) if h.division_id else None,
            "type": h.type,
            "rx_total": int(rx_all.get(hid, 0)),
            "rx_last_30d": int(rx_30.get(hid, 0)),
            "doctors_with_rx": int(doc_all.get(hid, 0)),
            "linked_doctors": int(aff_all.get(hid, 0)),
            "listed_doctors": getattr(h, "listed_doctors", None),
        })
    facilities.sort(key=lambda x: (-x["rx_total"], x["name"] or ""))
    return {
        "scope": "all_facilities" if user.role == "system_admin" else "own_facility",
        "count": len(facilities),
        "totals": {
            "facilities": len(facilities),
            "rx_total": sum(f["rx_total"] for f in facilities),
            "rx_last_30d": sum(f["rx_last_30d"] for f in facilities),
        },
        "facilities": facilities,
    }


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
