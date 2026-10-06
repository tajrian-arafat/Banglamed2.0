"""M2 catalog + M3 medicine info + M4 tests + M12 directory + M13 facilities."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..core.errors import not_found
from ..deps import get_current_user
from ..services.search import search_medicines

router = APIRouter(prefix="/api", tags=["catalog"])


def _brand_card(db: Session, b: M.Brand) -> dict:
    gen = db.get(M.Generic, b.generic_id) if b.generic_id else None
    comp = db.get(M.Company, b.company_id) if b.company_id else None
    return {
        "id": b.id,
        "med_code": b.med_code,
        "name": b.name,
        "form": b.form_name,
        "strength": b.strength_text,
        "generic": gen.name if gen else None,
        "generic_id": b.generic_id,
        "company": comp.name if comp else None,
        "unit_price": float(b.unit_price) if b.unit_price is not None else None,
        "strip_price": float(b.strip_price) if b.strip_price is not None else None,
        "pack_size": b.pack_size,
        "pack_price": float(b.pack_price) if b.pack_price is not None else None,
        "pieces_per_strip": b.pieces_per_strip,
        "data_status": b.data_status,
        "completeness": b.completeness,
    }


@router.get("/medicines/search")
def medicines_search(q: str = Query("", min_length=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    results = search_medicines(db, q, limit=limit)
    # enrich with price
    for r in results:
        b = db.get(M.Brand, r["brand_id"])
        if b:
            r["unit_price"] = float(b.unit_price) if b.unit_price is not None else None
            r["strip_price"] = float(b.strip_price) if b.strip_price is not None else None
            r["pieces_per_strip"] = b.pieces_per_strip
            r["pack_size"] = b.pack_size
    return {"query": q, "count": len(results), "results": results}


@router.get("/medicines/{brand_id}")
def medicine_detail(brand_id: int, db: Session = Depends(get_db)):
    b = db.get(M.Brand, brand_id)
    if not b:
        raise not_found("Medicine not found")
    gen = db.get(M.Generic, b.generic_id) if b.generic_id else None
    comp = db.get(M.Company, b.company_id) if b.company_id else None
    # other strengths/forms of same generic
    others = []
    if b.generic_id:
        rows = db.scalars(
            select(M.Brand).where(M.Brand.generic_id == b.generic_id, M.Brand.id != b.id).limit(30)
        ).all()
        others = [_brand_card(db, x) for x in rows]
    # alternatives: same generic + same strength + same form, cheapest first
    alts = []
    if b.generic_id:
        rows = db.scalars(
            select(M.Brand).where(
                M.Brand.generic_id == b.generic_id,
                M.Brand.strength_text == b.strength_text,
                M.Brand.form_name == b.form_name,
                M.Brand.id != b.id,
            )
        ).all()
        alts = sorted([_brand_card(db, x) for x in rows], key=lambda r: (r["unit_price"] is None, r["unit_price"] or 0))
    return {
        "brand": _brand_card(db, b),
        "generic": {
            "id": gen.id if gen else None,
            "name": gen.name if gen else None,
            "therapeutic_class": gen.therapeutic_class if gen else None,
            "pregnancy_category": gen.pregnancy_category if gen else None,
        },
        "company": {"id": comp.id if comp else None, "name": comp.name if comp else None,
                    "headquarter": comp.headquarter if comp else None},
        "sections": {
            "indications": b.indications,
            "dosage_administration": b.dosage_administration,
            "side_effects": b.side_effects,
            "precautions_warnings": b.precautions_warnings,
            "pregnancy_lactation": b.pregnancy_lactation,
            "overdose_effects": b.overdose_effects,
            "storage_conditions": b.storage_conditions,
            "pharmacology": b.pharmacology,
            "contraindications": b.contraindications,
            "interaction": b.interaction,
        },
        "other_strengths": others,
        "alternatives": alts,
        "disclaimer": "Informational only. Not medical advice. Consult a registered doctor or pharmacist.",
    }


@router.get("/medicines/{brand_id}/alternatives")
def medicine_alternatives(brand_id: int, db: Session = Depends(get_db)):
    b = db.get(M.Brand, brand_id)
    if not b:
        raise not_found("Medicine not found")
    rows = db.scalars(
        select(M.Brand).where(
            M.Brand.generic_id == b.generic_id,
            M.Brand.strength_text == b.strength_text,
            M.Brand.form_name == b.form_name,
            M.Brand.id != b.id,
        )
    ).all()
    alts = sorted([_brand_card(db, x) for x in rows], key=lambda r: (r["unit_price"] is None, r["unit_price"] or 0))
    return {"alternatives": alts, "note": "Other brands with the same active ingredient. Consult your doctor or pharmacist before switching."}


# ---- tests
@router.get("/tests/search")
def tests_search(q: str = "", limit: int = 20, db: Session = Depends(get_db)):
    stmt = select(M.LabTest)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(M.LabTest.name.ilike(like), M.LabTest.aliases.ilike(like)))
    rows = db.scalars(stmt.limit(limit)).all()
    return {"results": [{"id": t.id, "name": t.name, "slug": t.slug, "price_min": float(t.price_min) if t.price_min else None,
                         "price_max": float(t.price_max) if t.price_max else None} for t in rows]}


@router.get("/tests/{test_id}")
def test_detail(test_id: int, db: Session = Depends(get_db)):
    t = db.get(M.LabTest, test_id)
    if not t:
        raise not_found("Test not found")
    prices = db.scalars(select(M.TestPrice).where(M.TestPrice.test_id == t.id)).all()
    return {
        "id": t.id, "name": t.name, "slug": t.slug, "sample_type": t.sample_type,
        "price_min": float(t.price_min) if t.price_min else None,
        "price_max": float(t.price_max) if t.price_max else None,
        "fasting_required": t.fasting_required, "fasting_hours_min": t.fasting_hours_min,
        "fasting_hours_max": t.fasting_hours_max, "prep_text": t.prep_text, "report_time": t.report_time,
        "procedure_text": t.procedure_text, "procedure_source": t.procedure_source,
        "prices": [{"hospital_name": p.hospital_name, "location": p.location,
                    "price": float(p.price) if p.price is not None else None, "badge": p.badge} for p in prices],
        "disclaimer": "Informational only. Not medical advice.",
    }


# ---- directory
@router.get("/directory/specialities")
def specialities(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.Speciality).order_by(M.Speciality.name)).all()
    return {"results": [{"id": s.id, "name": s.name} for s in rows]}


@router.get("/directory/doctors")
def doctors(q: str = "", speciality: str = "", district: str = "", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(M.Doctor)
    if q:
        stmt = stmt.where(M.Doctor.name.ilike(f"%{q}%"))
    if speciality:
        stmt = stmt.where(M.Doctor.speciality_name.ilike(f"%{speciality}%"))
    if district:
        stmt = stmt.where(M.Doctor.district_name == district)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(M.Doctor.name).offset(offset).limit(limit)).all()
    return {"total": total, "results": [
        {"id": d.id, "doctor_code": d.doctor_code, "name": d.name, "speciality": d.speciality_name,
         "qualifications": d.qualifications, "district": d.district_name, "city": d.city} for d in rows]}


@router.get("/directory/doctors/{doctor_id}")
def doctor_detail(doctor_id: int, db: Session = Depends(get_db)):
    d = db.get(M.Doctor, doctor_id)
    if not d:
        raise not_found("Doctor not found")
    affs = db.scalars(select(M.DoctorAffiliation).where(M.DoctorAffiliation.doctor_id == d.id)).all()
    scheds = db.scalars(select(M.DoctorSchedule).where(M.DoctorSchedule.doctor_id == d.id)).all()
    return {
        "id": d.id, "doctor_code": d.doctor_code, "name": d.name, "speciality": d.speciality_name,
        "qualifications": d.qualifications, "designation": d.designation, "bmdc_no": d.bmdc_no,
        "district": d.district_name, "city": d.city,
        "affiliations": [{"hospital_id": a.hospital_id, "room": a.room, "fee": float(a.fee) if a.fee else None} for a in affs],
        "schedules": [{"id": s.id, "date": s.date, "total_serials": s.total_serials, "session_start": s.session_start,
                       "session_end": s.session_end, "fee": float(s.fee) if s.fee else None} for s in scheds],
    }


@router.get("/directory/hospitals")
def hospitals(q: str = "", district: str = "", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(M.Hospital)
    if q:
        stmt = stmt.where(M.Hospital.name.ilike(f"%{q}%"))
    if district:
        stmt = stmt.where(M.Hospital.district_name == district)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(M.Hospital.name).offset(offset).limit(limit)).all()
    return {"total": total, "results": [
        {"id": h.id, "name": h.name, "district": h.district_name, "address": h.address,
         "phone": h.phone, "hours": h.hours} for h in rows]}


@router.get("/directory/hospitals/{hospital_id}")
def hospital_detail(hospital_id: int, db: Session = Depends(get_db)):
    h = db.get(M.Hospital, hospital_id)
    if not h:
        raise not_found("Hospital not found")
    affs = db.scalars(select(M.DoctorAffiliation).where(M.DoctorAffiliation.hospital_id == h.id)).all()
    docs = []
    for a in affs:
        d = db.get(M.Doctor, a.doctor_id)
        if d:
            docs.append({"id": d.id, "name": d.name, "speciality": d.speciality_name, "room": a.room,
                         "fee": float(a.fee) if a.fee else None})
    return {"id": h.id, "name": h.name, "district": h.district_name, "address": h.address, "phone": h.phone,
            "hours": h.hours, "about": h.about, "doctors": docs}


@router.get("/geo/districts")
def geo_districts(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.GeoDistrict).order_by(M.GeoDistrict.name)).all()
    return {"results": [{"id": d.id, "name": d.name, "division_id": d.division_id} for d in rows]}


@router.get("/geo/divisions")
def geo_divisions(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.GeoDivision).order_by(M.GeoDivision.name)).all()
    return {"results": [{"id": d.id, "name": d.name} for d in rows]}


@router.get("/facilities/nearby")
def facilities_nearby(lat: float | None = None, lng: float | None = None, radius_km: float = 5, kind: str = "hospital", db: Session = Depends(get_db)):
    """Local-DB facility finder (hospitals). Overpass/OSM is the optional live provider."""
    rows = db.scalars(select(M.Hospital).limit(200)).all()
    out = []
    for h in rows:
        dist = None
        if lat is not None and lng is not None and h.lat is not None and h.lng is not None:
            dist = round(((h.lat - lat) ** 2 + (h.lng - lng) ** 2) ** 0.5 * 111, 2)
        out.append({"id": h.id, "name": h.name, "district": h.district_name, "address": h.address,
                    "phone": h.phone, "lat": h.lat, "lng": h.lng, "distance_km": dist})
    if lat is not None:
        out = [o for o in out if o["distance_km"] is None or o["distance_km"] <= radius_km]
        out.sort(key=lambda o: (o["distance_km"] is None, o["distance_km"] or 0))
    return {"provider": "local-db", "results": out[:60]}
