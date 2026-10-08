"""Prescription analysis — the payload behind the patient upload page.

Given a set of medicines (matched from OCR, or typed by hand) and tests, this
builds everything the UI needs in one response:

*   **prices** — per medicine and per test, from the catalog.
*   **totals across timeframes** — full course, 1 month, 15 days, 1 week,
    5 days (and 30 days), so a patient can see what a shorter or longer supply
    costs. Computed with the same Decimal money rules as the cost calculator.
*   **safety** — every guard the engine knows about (duplicate ingredient,
    duplicate class, interactions, allergies, pregnancy, age, long duration,
    repeat), plus the **side effects** of each medicine and the
    **contraindications / interactions** between the prescribed medicines.

Nothing here is medical advice: it surfaces what the catalog says so a patient
can discuss it with a pharmacist or doctor.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from .cost import _is_countable, _unit_cost
from .safety import check_prescription

# The timeframes the patient sees. "full_course" is handled separately because
# it depends on each medicine's own duration.
WINDOWS = [5, 7, 15, 30]
WINDOW_LABELS = {5: "5 days", 7: "1 week", 15: "15 days", 30: "1 month"}


def _brand_dict(b: M.Brand) -> dict[str, Any]:
    return {
        "name": b.name, "form_name": b.form_name,
        "unit_price": float(b.unit_price) if b.unit_price is not None else None,
        "strip_price": float(b.strip_price) if b.strip_price is not None else None,
        "pack_price": float(b.pack_price) if b.pack_price is not None else None,
        "pieces_per_strip": b.pieces_per_strip,
    }


def _doses_per_day(dose: dict[str, Any] | None) -> Decimal:
    if not dose:
        return Decimal("1")
    slots = dose.get("slots") or {}
    total = sum(float(v or 0) for v in slots.values())
    return Decimal(str(total)) if total > 0 else Decimal("1")


def _per_dose(dose: dict[str, Any] | None) -> Decimal:
    """Quantity taken at each administration (default 1 tablet)."""
    if not dose:
        return Decimal("1")
    q = dose.get("per_dose") or dose.get("qty")
    try:
        return Decimal(str(q)) if q else Decimal("1")
    except Exception:
        return Decimal("1")


def _duration_days(dose: dict[str, Any] | None) -> int | None:
    if not dose:
        return None
    dur = dose.get("duration") or {}
    if isinstance(dur, dict) and dur.get("value"):
        try:
            return int(dur["value"])
        except Exception:
            return None
    return None


def _cost_for_days(brand: dict[str, Any], per_dose: Decimal, dpd: Decimal, days: int) -> float:
    unit = _unit_cost(brand)
    pieces = per_dose * dpd * Decimal(days)
    if _is_countable(brand.get("form_name")):
        return float((pieces * unit).quantize(Decimal("0.01")))
    containers = pieces.to_integral_value(rounding=ROUND_CEILING)
    return float((containers * unit).quantize(Decimal("0.01")))


def analyse(
    db: Session,
    *,
    patient: M.Patient | None,
    medicines: list[dict[str, Any]],
    tests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the full analysis payload.

    ``medicines`` items: ``{brand_id, dose?, name?}`` (a free-text name with no
    brand_id is priced as unknown but still listed).
    ``tests`` items: ``{test_id?, name?}``.
    """
    med_rows: list[dict[str, Any]] = []
    totals = {f"{w}d": Decimal("0") for w in WINDOWS}
    full_total = Decimal("0")
    full_known = True

    for m in medicines:
        bid = m.get("brand_id")
        b = db.get(M.Brand, bid) if bid else None
        dose = m.get("dose") or {}
        per_dose = _per_dose(dose)
        dpd = _doses_per_day(dose)
        duration = _duration_days(dose) or m.get("duration_days")

        row: dict[str, Any] = {
            "brand_id": bid,
            "name": (b.name if b else m.get("name")) or "Unknown medicine",
            "generic": None, "company": None, "strength": None, "form": None,
            "unit_price": None, "pack_size": None, "pack_price": None,
            "doses_per_day": float(dpd), "duration_days": duration,
            "windows": {}, "full_course": None, "priced": False,
        }
        if b:
            gen = db.get(M.Generic, b.generic_id) if b.generic_id else None
            comp = db.get(M.Company, b.company_id) if b.company_id else None
            row.update({
                "generic": gen.name if gen else None,
                "company": comp.name if comp else None,
                "strength": b.strength_text, "form": b.form_name,
                "unit_price": float(b.unit_price) if b.unit_price is not None else None,
                "pack_size": b.pack_size,
                "pack_price": float(b.pack_price) if b.pack_price is not None else None,
            })
            bd = _brand_dict(b)
            for w in WINDOWS:
                c = _cost_for_days(bd, per_dose, dpd, w)
                row["windows"][f"{w}d"] = c
                totals[f"{w}d"] += Decimal(str(c))
            if duration:
                fc = _cost_for_days(bd, per_dose, dpd, int(duration))
                row["full_course"] = fc
                full_total += Decimal(str(fc))
            else:
                full_known = False
            row["priced"] = True
        else:
            for w in WINDOWS:
                row["windows"][f"{w}d"] = None
            full_known = False
        med_rows.append(row)

    # ---- tests
    test_rows: list[dict[str, Any]] = []
    tests_total = Decimal("0")
    for t in tests:
        tid = t.get("test_id")
        row_t = db.get(M.LabTest, tid) if tid else None
        price = None
        if row_t and row_t.price_min is not None:
            price = float(row_t.price_min)
            tests_total += Decimal(str(price))
        test_rows.append({
            "test_id": tid,
            "name": (row_t.name if row_t else t.get("name")) or "Unknown test",
            "price_min": price,
            "price_max": float(row_t.price_max) if row_t and row_t.price_max is not None else None,
            "sample_type": row_t.sample_type if row_t else None,
            "fasting_required": bool(row_t.fasting_required) if row_t else False,
            "priced": price is not None,
        })

    # ---- safety: guards + side effects + interactions
    safety = _safety_payload(db, patient, med_rows)

    return {
        "medicines": med_rows,
        "tests": test_rows,
        "totals": {
            # ``totals`` is already keyed "5d"/"7d"/… — do not append another "d".
            "windows": {k: float(v) for k, v in totals.items()},
            "window_labels": {f"{w}d": WINDOW_LABELS[w] for w in WINDOWS},
            "full_course": float(full_total) if full_known else None,
            "full_course_complete": full_known,
            "tests_total": float(tests_total),
            "grand_total_full_course": float(full_total + tests_total) if full_known else None,
            "currency": "BDT",
        },
        "safety": safety,
        "disclaimer": (
            "Informational only — not medical advice. Prices are catalog estimates and "
            "vary by pharmacy. Always confirm with a registered doctor or pharmacist."
        ),
    }


def _safety_payload(db: Session, patient: M.Patient | None, med_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """All guards, plus per-medicine side effects and pairwise interactions."""
    items = [
        {
            "brand_id": r["brand_id"],
            "generic_id": (db.get(M.Brand, r["brand_id"]).generic_id if r["brand_id"] else None),
            "form": r["form"], "strength": r["strength"], "name": r["name"],
            "duration_days": r["duration_days"],
        }
        for r in med_rows
    ]

    warnings: list[dict[str, Any]] = []
    if patient is not None and items:
        warnings = check_prescription(db, patient, items)

    # Per-medicine side effects + contraindications, straight from the catalog.
    side_effects: list[dict[str, Any]] = []
    for r in med_rows:
        bid = r["brand_id"]
        if not bid:
            continue
        b = db.get(M.Brand, bid)
        if not b:
            continue
        gen = db.get(M.Generic, b.generic_id) if b.generic_id else None
        se = (b.side_effects or "").strip()
        ci = (b.contraindications or "").strip()
        if not se and gen:
            se = (_generic_section(db, gen.id, "side_effects") or "").strip()
        if not ci and gen:
            ci = (_generic_section(db, gen.id, "contraindications") or "").strip()
        side_effects.append({
            "brand_id": bid, "name": b.name, "generic": gen.name if gen else None,
            "side_effects": se or None,
            "contraindications": ci or None,
        })

    # Pairwise interactions between the prescribed medicines, from the catalog
    # interaction text (the same source the safety engine uses).
    interactions: list[dict[str, Any]] = []
    for i, a in enumerate(med_rows):
        ga = _generic_of(db, a["brand_id"])
        if not ga:
            continue
        a_text = f"{ga.name or ''} {ga.therapeutic_class or ''}"
        a_inter = (_generic_section(db, ga.id, "interaction") or "").strip()
        for b_row in med_rows[i + 1:]:
            gb = _generic_of(db, b_row["brand_id"])
            if not gb:
                continue
            b_text = f"{gb.name or ''} {gb.therapeutic_class or ''}"
            b_inter = (_generic_section(db, gb.id, "interaction") or "").strip()
            if _mentions(a_inter, b_text) or _mentions(b_inter, a_text):
                interactions.append({
                    "a": a["name"], "b": b_row["name"],
                    "a_generic": ga.name, "b_generic": gb.name,
                    "note": (
                        f"The catalog interaction text for {ga.name} or {gb.name} "
                        "mentions the other. Confirm with a pharmacist."
                    ),
                })

    return {
        "guards": warnings,
        "guard_count": len(warnings),
        "side_effects": side_effects,
        "interactions": interactions,
        "interaction_count": len(interactions),
        "checked": patient is not None and bool(items),
    }


def _generic_of(db: Session, brand_id: int | None) -> M.Generic | None:
    if not brand_id:
        return None
    b = db.get(M.Brand, brand_id)
    if not b or not b.generic_id:
        return None
    return db.get(M.Generic, b.generic_id)


def _generic_section(db: Session, generic_id: int, section: str) -> str | None:
    row = db.scalar(
        select(M.GenericContent).where(
            M.GenericContent.generic_id == generic_id,
            M.GenericContent.section == section,
            M.GenericContent.lang == "en",
        )
    )
    return row.text if row else None


def _mentions(text: str, needle: str) -> bool:
    if not text or not needle:
        return False
    import re

    for token in re.split(r"[,\s]+", needle.lower()):
        token = token.strip()
        if len(token) >= 5 and token in text.lower():
            return True
    return False
