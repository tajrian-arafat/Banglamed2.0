"""Course cost calculator (SPEC M9). Decimal money, exact per-piece for solids."""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Any

from ..core.config import cost_rules

COUNTABLE = {f.lower() for f in cost_rules().get("countable_forms", [])}
CONTAINER = {f.lower() for f in cost_rules().get("container_forms", [])}
WINDOWS = cost_rules().get("windows_days", [7, 30])


def _is_countable(form: str | None) -> bool:
    f = (form or "").lower()
    if f in COUNTABLE:
        return True
    if f in CONTAINER:
        return False
    return True  # default to countable solids


def _unit_cost(brand: dict[str, Any]) -> Decimal:
    if brand.get("unit_price") is not None:
        return Decimal(str(brand["unit_price"]))
    if brand.get("strip_price") is not None and brand.get("pieces_per_strip"):
        return (Decimal(str(brand["strip_price"])) / Decimal(str(brand["pieces_per_strip"]))).quantize(Decimal("0.01"))
    if brand.get("pack_price") is not None and brand.get("pieces_per_strip"):
        return (Decimal(str(brand["pack_price"])) / Decimal(str(brand["pieces_per_strip"]))).quantize(Decimal("0.01"))
    return Decimal("0")


def _pieces_for_window(per_dose: Decimal, doses_per_day: Decimal, window_days: int, duration_days: int | None) -> Decimal:
    days = window_days if duration_days is None else min(window_days, duration_days)
    return per_dose * doses_per_day * Decimal(days)


def compute_cost(items: list[dict[str, Any]], brands: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """items: [{brand_id, per_dose_qty, doses_per_day, duration_days, kind}]"""
    per_medicine: list[dict[str, Any]] = []
    totals = {f"{w}d": Decimal("0") for w in WINDOWS}
    full_total = Decimal("0")
    for it in items:
        brand = brands.get(it["brand_id"])
        if not brand:
            continue
        form = brand.get("form_name")
        countable = _is_countable(form)
        unit_cost = _unit_cost(brand)
        per_dose = Decimal(str(it.get("per_dose_qty", 1)))
        dpd = Decimal(str(it.get("doses_per_day", 1)))
        duration = it.get("duration_days")
        kind = it.get("kind", "course")
        row: dict[str, Any] = {
            "brand_id": it["brand_id"],
            "name": brand.get("name"),
            "form": form,
            "unit_price": float(unit_cost),
            "countable": countable,
            "kind": kind,
            "windows": {},
        }
        for w in WINDOWS:
            if kind in ("continue", "as_needed") and duration is None:
                pieces = per_dose * dpd * Decimal(w)
            else:
                pieces = _pieces_for_window(per_dose, dpd, w, duration)
            if countable:
                cost = (pieces * unit_cost).quantize(Decimal("0.01"))
            else:
                containers = (pieces / Decimal("1")).to_integral_value(rounding=ROUND_CEILING)
                cost = (containers * unit_cost).quantize(Decimal("0.01"))
            row["windows"][f"{w}d"] = float(cost)
            totals[f"{w}d"] += cost
        if kind in ("continue", "as_needed") and duration is None:
            row["full_course"] = None
            row["flagged"] = "excluded from full course (no fixed duration)"
        else:
            days = duration if duration is not None else 0
            pieces = per_dose * dpd * Decimal(days)
            if countable:
                cost = (pieces * unit_cost).quantize(Decimal("0.01"))
            else:
                containers = pieces.to_integral_value(rounding=ROUND_CEILING)
                cost = (containers * unit_cost).quantize(Decimal("0.01"))
            row["full_course"] = float(cost)
            full_total += cost
        per_medicine.append(row)
    return {
        "totals": {**{k: float(v) for k, v in totals.items()}, "full_course": float(full_total)},
        "per_medicine": per_medicine,
        "currency": "BDT",
    }
