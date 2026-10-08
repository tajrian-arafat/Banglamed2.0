"""Public price lookup reached by scanning the QR on a printed prescription.

No authentication: the QR is meant to be scannable by a patient at a pharmacy
counter. Access is gated by the prescription's own unguessable ``public_token``
(``secrets.token_urlsafe(24)``), exactly like ``/api/prescriptions/public/{token}``
already was — this endpoint adds the PRICES on top of the prescription payload,
plus a free-text search so a scanned prescription can also be used to price a
medicine or test that was not written on it.

Deliberately contains nothing that is not already on the printed sheet:
no patient contact details, no doctor's private notes beyond what was printed,
no other patient's data.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..core.errors import not_found
from ..services.search import search_medicines, suggest_medicines

router = APIRouter(prefix="/api/prices", tags=["prices"])


def _money(v) -> float | None:
    return float(v) if v is not None else None


def _brand_price_row(db: Session, brand_id: int | None, fallback_name: str | None) -> dict:
    b = db.get(M.Brand, brand_id) if brand_id else None
    if b is None and fallback_name:
        # Try to resolve a free-text name back to a catalog brand so the price is
        # still shown when the doctor typed the medicine by hand.
        hits = search_medicines(db, fallback_name, limit=1)
        if hits:
            b = db.get(M.Brand, hits[0]["brand_id"])
    if b is None:
        return {"brand_id": brand_id, "name": fallback_name, "found": False,
                "unit_price": None, "strip_price": None, "pack_size": None,
                "pieces_per_strip": None}
    return {
        "brand_id": b.id, "name": b.name, "found": True,
        "generic": None, "company": None, "strength": b.strength_text, "form": b.form_name,
        "unit_price": _money(b.unit_price), "strip_price": _money(b.strip_price),
        "pack_size": b.pack_size, "pieces_per_strip": b.pieces_per_strip,
    }


def _test_price_row(db: Session, test_id: int | None, fallback_name: str | None) -> dict:
    t = db.get(M.LabTest, test_id) if test_id else None
    if t is None and fallback_name:
        name = re.sub(r"\s+", " ", (fallback_name or "").strip())
        t = db.scalar(select(M.LabTest).where(M.LabTest.name.ilike(f"%{name}%")).limit(1))
    if t is None:
        return {"test_id": test_id, "name": fallback_name, "found": False,
                "price_min": None, "price_max": None, "offers": []}
    offers = db.scalars(
        select(M.TestPrice).where(M.TestPrice.test_id == t.id)
        .order_by(M.TestPrice.price.asc()).limit(8)
    ).all()
    return {
        "test_id": t.id, "name": t.name, "found": True,
        "category": (db.get(M.TestCategory, t.category_id).name if t.category_id and db.get(M.TestCategory, t.category_id) else None),
        "sample_type": t.sample_type, "fasting_required": bool(t.fasting_required),
        "price_min": _money(t.price_min), "price_max": _money(t.price_max),
        "offers": [{"hospital_name": o.hospital_name, "location": o.location,
                    "price": _money(o.price), "badge": o.badge} for o in offers],
    }


@router.get("/lookup/{token}")
def lookup(token: str, db: Session = Depends(get_db)):
    """Everything a patient needs after scanning the printed QR: the prescribed
    medicines and tests, each with its price, and the prescription's integrity
    status."""
    rx = db.scalar(select(M.Prescription).where(M.Prescription.public_token == token))
    if not rx:
        raise not_found("Prescription not found")

    items = db.scalars(select(M.PrescriptionItem).where(M.PrescriptionItem.rx_id == rx.id)).all()
    tests = db.scalars(select(M.PrescriptionTest).where(M.PrescriptionTest.rx_id == rx.id)).all()

    med_rows = [_brand_price_row(db, i.brand_id, i.free_text_name) for i in items]
    # Fall back to the free-text name when a brand row exists but the name was typed.
    for row, i in zip(med_rows, items):
        if row.get("name") is None and i.free_text_name:
            row["name"] = i.free_text_name
        if row.get("brand_id") is None and i.brand_id:
            row["brand_id"] = i.brand_id
    test_rows = [_test_price_row(db, t.test_id, t.free_text_name) for t in tests]

    def _line_total(row: dict) -> float | None:
        for key in ("strip_price", "unit_price"):
            if row.get(key) is not None:
                return row[key]
        return None

    prices = [_line_total(r) for r in med_rows if r.get("found")]
    doctor = db.get(M.Doctor, rx.doctor_id)
    patient = db.get(M.Patient, rx.patient_id)
    return {
        "rx_code": rx.rx_code,
        "issued_at": rx.issued_at.isoformat() if rx.issued_at else None,
        "prescriber": doctor.name if doctor else None,
        "patient_initials": "".join(p[0] for p in (patient.full_name or "").split()[:2]) if patient else None,
        "diagnosis": rx.diagnosis,
        "medicines": med_rows,
        "tests": test_rows,
        "estimated_medicine_cost": round(sum(prices), 2) if prices else None,
        "medicine_count": len(med_rows),
        "test_count": len(test_rows),
        "disclaimer": ("Prices are indicative and collected from public listings; they vary by "
                       "pharmacy and over time. Informational only — not medical advice."),
    }


@router.get("/search")
def price_search(q: str = Query("", min_length=1), limit: int = Query(10, ge=1, le=25), db: Session = Depends(get_db)):
    """Free-text price search for medicines and tests, usable from the scanned page."""
    meds = search_medicines(db, q, limit=limit)
    like = f"%{q.strip()}%"
    tests = db.scalars(
        select(M.LabTest).where(M.LabTest.name.ilike(like)).order_by(M.LabTest.name).limit(limit)
    ).all()
    return {
        "query": q,
        "medicines": meds,
        "tests": [{"test_id": t.id, "name": t.name, "price_min": _money(t.price_min),
                   "price_max": _money(t.price_max), "sample_type": t.sample_type,
                   "fasting_required": bool(t.fasting_required)} for t in tests],
    }


@router.get("/suggest")
def price_suggest(q: str = Query("", min_length=1), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    """Public keystroke suggestions (same index-only engine as the catalog)."""
    return {"query": q, "results": suggest_medicines(db, q, limit=limit)}
