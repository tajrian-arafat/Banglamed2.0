"""Deterministic Bangla dosage formatter (SPEC 8.2). No LLM, fully unit-tested."""
from __future__ import annotations

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

SLOT_BN = {"morning": "সকাল", "noon": "দুপুর", "evening": "বিকাল", "night": "রাত"}
MEAL_BN = {
    "before": "খাবারের আগে",
    "after": "খাবারের পরে",
    "with": "খাবারের সাথে",
    "empty_stomach": "খালি পেটে",
    "bedtime": "শোয়ার আগে",
}
UNIT_BN = {
    "tablet": "টি",
    "capsule": "টি",
    "suppository": "টি",
    "injection": "টি",
    "syrup": "চামচ",
    "suspension": "চামচ",
    "solution": "চামচ",
    "oral solution": "চামচ",
    "drops": "ফোঁটা",
    "drop": "ফোঁটা",
    "eye drop": "ফোঁটা",
    "ear drop": "ফোঁটা",
    "nasal drop": "ফোঁটা",
    "inhaler": "পাফ",
    "puff": "পাফ",
    "cream": "আক্রান্ত স্থানে পাতলা করে লাগান",
    "gel": "আক্রান্ত স্থানে পাতলা করে লাগান",
    "ointment": "আক্রান্ত স্থানে পাতলা করে লাগান",
    "lotion": "আক্রান্ত স্থানে লাগান",
}
DURATION_UNIT_BN = {"day": "দিন", "days": "দিন", "week": "সপ্তাহ", "weeks": "সপ্তাহ", "month": "মাস", "months": "মাস"}


def to_bn_digits(value: str | int | float) -> str:
    return str(value).translate(BN_DIGITS)


def _fmt_qty(qty: float, unit: str) -> str:
    unit_bn = UNIT_BN.get((unit or "tablet").lower(), "টি")
    if unit_bn.startswith("আক্রান্ত"):
        return unit_bn
    if qty == 0.5:
        return f"আধা {unit_bn}"
    if qty == 1.5:
        return f"দেড় {unit_bn}"
    if float(qty).is_integer():
        return f"{to_bn_digits(int(qty))}{unit_bn}"
    return f"{to_bn_digits(qty)}{unit_bn}"


def format_dosage(dose: dict) -> str:
    """dose = {slots:{morning,noon,evening,night}, unit, meal, duration:{value,unit}|{kind}, every_hours}"""
    unit = dose.get("unit", "tablet")
    parts: list[str] = []
    every_hours = dose.get("every_hours")
    if every_hours:
        parts.append(f"প্রতি {to_bn_digits(every_hours)} ঘণ্টা পরপর {_fmt_qty(dose.get('per_dose_qty', 1), unit)}")
    else:
        slots = dose.get("slots") or {}
        for key in ("morning", "noon", "evening", "night"):
            qty = slots.get(key, 0)
            if qty:
                parts.append(f"{SLOT_BN[key]} {_fmt_qty(qty, unit)}")
    text = ", ".join(parts) if parts else "নির্দেশ অনুযায়ী"
    meal = dose.get("meal")
    if meal and meal in MEAL_BN:
        text += f" — {MEAL_BN[meal]}"
    duration = dose.get("duration") or {}
    if duration.get("kind") == "continue":
        text += " — চলবে"
    elif duration.get("kind") == "as_needed":
        text += " — প্রয়োজন"
    elif duration.get("value"):
        unit_bn = DURATION_UNIT_BN.get(str(duration.get("unit", "day")).lower(), "দিন")
        text += f" — {to_bn_digits(duration['value'])} {unit_bn}"
    return text
