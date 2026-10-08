"""Bangla dosage formatter — >=15 cases (SPEC 8.2)."""
from __future__ import annotations

import pytest

from app.services.dosage import format_dosage, to_bn_digits


def test_bn_digits():
    assert to_bn_digits(123) == "১২৩"
    assert to_bn_digits("2026") == "২০২৬"


@pytest.mark.parametrize(
    "dose,expected_parts",
    [
        ({"slots": {"morning": 1, "night": 1}, "unit": "tablet", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["সকাল ১টি", "রাত ১টি", "খাবারের পরে", "৭ দিন"]),
        ({"slots": {"morning": 1, "noon": 1, "evening": 1}, "unit": "tablet", "meal": "before", "duration": {"value": 5, "unit": "day"}},
         ["সকাল ১টি", "দুপুর ১টি", "বিকাল ১টি", "খাবারের আগে", "৫ দিন"]),
        ({"slots": {"night": 1}, "unit": "tablet", "meal": "after", "duration": {"value": 10, "unit": "day"}},
         ["রাত ১টি", "১০ দিন"]),
        ({"slots": {"morning": 0.5, "night": 0.5}, "unit": "tablet", "meal": "after", "duration": {"value": 3, "unit": "day"}},
         ["সকাল আধা টি", "রাত আধা টি", "৩ দিন"]),
        ({"slots": {"morning": 1.5}, "unit": "tablet", "meal": "after", "duration": {"value": 2, "unit": "day"}},
         ["সকাল দেড় টি", "২ দিন"]),
        ({"slots": {"morning": 2, "night": 2}, "unit": "capsule", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["সকাল ২টি", "রাত ২টি", "৭ দিন"]),
        ({"slots": {"morning": 1}, "unit": "syrup", "meal": "after", "duration": {"value": 5, "unit": "day"}},
         ["সকাল ১চামচ", "৫ দিন"]),
        ({"slots": {"morning": 1, "night": 1}, "unit": "drops", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["সকাল ১ফোঁটা", "রাত ১ফোঁটা"]),
        ({"slots": {"morning": 1}, "unit": "inhaler", "meal": "after", "duration": {"value": 30, "unit": "day"}},
         ["সকাল ১পাফ", "৩০ দিন"]),
        ({"slots": {"morning": 1, "night": 1}, "unit": "tablet", "meal": "empty_stomach", "duration": {"value": 14, "unit": "day"}},
         ["খালি পেটে", "১৪ দিন"]),
        ({"slots": {"night": 1}, "unit": "tablet", "meal": "bedtime", "duration": {"value": 7, "unit": "day"}},
         ["শোয়ার আগে", "৭ দিন"]),
        ({"slots": {"morning": 1}, "unit": "tablet", "meal": "after", "duration": {"kind": "continue"}},
         ["চলবে"]),
        ({"slots": {"morning": 1}, "unit": "tablet", "meal": "after", "duration": {"kind": "as_needed"}},
         ["প্রয়োজন"]),
        ({"every_hours": 6, "per_dose_qty": 1, "unit": "tablet", "meal": "after", "duration": {"value": 3, "unit": "day"}},
         ["প্রতি ৬ ঘণ্টা পরপর ১টি", "৩ দিন"]),
        ({"slots": {"morning": 1, "noon": 1, "evening": 1, "night": 1}, "unit": "tablet", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["সকাল ১টি", "দুপুর ১টি", "বিকাল ১টি", "রাত ১টি", "৭ দিন"]),
        ({"slots": {"morning": 1}, "unit": "cream", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["আক্রান্ত স্থানে পাতলা করে লাগান", "৭ দিন"]),
        ({"slots": {}, "unit": "tablet", "meal": "after", "duration": {"value": 7, "unit": "day"}},
         ["নির্দেশ অনুযায়ী", "৭ দিন"]),
    ],
)
def test_format_dosage(dose, expected_parts):
    text = format_dosage(dose)
    for part in expected_parts:
        assert part in text, f"missing '{part}' in '{text}'"


def test_week_duration():
    text = format_dosage({"slots": {"morning": 1}, "unit": "tablet", "meal": "after", "duration": {"value": 2, "unit": "week"}})
    assert "২ সপ্তাহ" in text
