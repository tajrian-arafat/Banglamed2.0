"""Cost calculator — worked example (SPEC M9)."""
from __future__ import annotations

from app.services.cost import compute_cost


def test_worked_example_tablet():
    # 1 tablet 3x/day for 30 days, unit price 2.00 -> 90 tablets -> 180.00
    brands = {1: {"name": "TestTab", "form_name": "Tablet", "unit_price": 2.0, "strip_price": 20.0, "pieces_per_strip": 10}}
    items = [{"brand_id": 1, "per_dose_qty": 1, "doses_per_day": 3, "duration_days": 30, "kind": "course"}]
    r = compute_cost(items, brands)
    assert r["totals"]["7d"] == 42.0
    assert r["totals"]["30d"] == 180.0
    assert r["totals"]["full_course"] == 180.0


def test_strip_price_derivation():
    # no unit price -> derive from strip 20.00 / 10 = 2.00
    brands = {1: {"name": "T", "form_name": "Tablet", "unit_price": None, "strip_price": 20.0, "pieces_per_strip": 10}}
    items = [{"brand_id": 1, "per_dose_qty": 1, "doses_per_day": 2, "duration_days": 10, "kind": "course"}]
    r = compute_cost(items, brands)
    assert r["totals"]["full_course"] == 40.0


def test_continue_excluded_from_full_course():
    brands = {1: {"name": "T", "form_name": "Tablet", "unit_price": 1.0, "pieces_per_strip": 10}}
    items = [{"brand_id": 1, "per_dose_qty": 1, "doses_per_day": 1, "duration_days": None, "kind": "continue"}]
    r = compute_cost(items, brands)
    assert r["totals"]["full_course"] == 0.0
    assert r["totals"]["7d"] == 7.0
    assert r["per_medicine"][0]["full_course"] is None


def test_container_form_rounds_up():
    brands = {1: {"name": "Syr", "form_name": "Syrup", "unit_price": 50.0}}
    items = [{"brand_id": 1, "per_dose_qty": 1, "doses_per_day": 1, "duration_days": 3, "kind": "course"}]
    r = compute_cost(items, brands)
    assert r["totals"]["full_course"] == 150.0


def test_mixed_course_and_continue():
    brands = {
        1: {"name": "A", "form_name": "Tablet", "unit_price": 1.0, "pieces_per_strip": 10},
        2: {"name": "B", "form_name": "Tablet", "unit_price": 2.0, "pieces_per_strip": 10},
    }
    items = [
        {"brand_id": 1, "per_dose_qty": 1, "doses_per_day": 1, "duration_days": 10, "kind": "course"},
        {"brand_id": 2, "per_dose_qty": 1, "doses_per_day": 1, "duration_days": None, "kind": "continue"},
    ]
    r = compute_cost(items, brands)
    assert r["totals"]["full_course"] == 10.0
    assert r["totals"]["30d"] == 10.0 + 60.0
