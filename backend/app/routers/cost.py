"""M9 cost calculator."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..schemas import CostIn
from ..services.cost import compute_cost

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.post("/estimate")
def estimate(payload: CostIn, db: Session = Depends(get_db)):
    brands: dict[int, dict] = {}
    for it in payload.items:
        b = db.get(M.Brand, it.brand_id)
        if b:
            brands[b.id] = {
                "name": b.name, "form_name": b.form_name, "unit_price": float(b.unit_price) if b.unit_price is not None else None,
                "strip_price": float(b.strip_price) if b.strip_price is not None else None,
                "pack_price": float(b.pack_price) if b.pack_price is not None else None,
                "pieces_per_strip": b.pieces_per_strip,
            }
    result = compute_cost([it.model_dump() for it in payload.items], brands)
    # tests
    test_total = 0.0
    test_rows = []
    for tid in payload.test_ids:
        t = db.get(M.LabTest, tid)
        if t:
            price = float(t.price_min) if t.price_min is not None else 0.0
            test_total += price
            test_rows.append({"id": t.id, "name": t.name, "price": price})
    result["tests"] = test_rows
    result["tests_total"] = round(test_total, 2)
    result["grand_total"] = round(result["totals"]["full_course"] + test_total, 2)
    result["disclaimer"] = "Estimated from catalog prices. Actual prices vary by pharmacy. Not medical advice."
    return result
