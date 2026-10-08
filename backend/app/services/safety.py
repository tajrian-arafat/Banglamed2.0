"""Medication safety rules (SPEC M6). Data-driven from config/safety_rules.json."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.config import safety_rules


def _sev(rule: str) -> str:
    return safety_rules().get("severity", {}).get(rule, "warn")


def _age(dob: str | None) -> int | None:
    if not dob:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", dob)
    if not m:
        return None
    try:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        today = datetime.now(timezone.utc).date()
        return today.year - y - ((today.month, today.day) < (mo, d))
    except Exception:
        return None


def check_prescription(db: Session, patient: M.Patient, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """items: [{brand_id, generic_id, form, strength, duration_days, name}]"""
    warnings: list[dict[str, Any]] = []
    rules = safety_rules()

    # resolve generics/classes
    resolved = []
    for it in items:
        gid = it.get("generic_id")
        gen = db.get(M.Generic, gid) if gid else None
        resolved.append({**it, "generic": gen})

    # duplicate ingredient
    seen: dict[int, str] = {}
    for it in resolved:
        gen = it.get("generic")
        if not gen:
            continue
        if gen.id in seen:
            warnings.append(
                {
                    "code": "duplicate_ingredient",
                    "severity": _sev("duplicate_ingredient"),
                    "message": f"Duplicate active ingredient: {gen.name} appears more than once.",
                    "medicines_involved": [seen[gen.id], it.get("name") or gen.name],
                }
            )
        else:
            seen[gen.id] = it.get("name") or gen.name

    # duplicate therapeutic class
    class_seen: dict[str, str] = {}
    for it in resolved:
        gen = it.get("generic")
        if not gen or not gen.therapeutic_class:
            continue
        tc = gen.therapeutic_class.split(",")[0].strip()
        if tc in class_seen:
            warnings.append(
                {
                    "code": "duplicate_class",
                    "severity": _sev("duplicate_class"),
                    "message": f"Two medicines share the therapeutic class '{tc}'.",
                    "medicines_involved": [class_seen[tc], it.get("name") or gen.name],
                }
            )
        else:
            class_seen[tc] = it.get("name") or gen.name

    # text-match interactions
    for i, a in enumerate(resolved):
        ga = a.get("generic")
        if not ga:
            continue
        a_text = (ga.name or "") + " " + (ga.therapeutic_class or "")
        for b in resolved[i + 1 :]:
            gb = b.get("generic")
            if not gb:
                continue
            b_text = (gb.name or "") + " " + (gb.therapeutic_class or "")
            a_inter = _generic_section(db, ga.id, "interaction") or ""
            b_inter = _generic_section(db, gb.id, "interaction") or ""
            hit = _text_mentions(a_inter, b_text) or _text_mentions(b_inter, a_text)
            if hit:
                warnings.append(
                    {
                        "code": "interaction",
                        "severity": _sev("interaction"),
                        "message": f"Possible interaction between {ga.name} and {gb.name} (based on interaction text in the medicine database).",
                        "medicines_involved": [a.get("name") or ga.name, b.get("name") or gb.name],
                    }
                )

    # allergies
    allergies = db.scalars(select(M.Allergy).where(M.Allergy.patient_id == patient.id)).all()
    for al in allergies:
        sub = (al.substance or "").lower()
        if not sub:
            continue
        for it in resolved:
            gen = it.get("generic")
            if gen and (sub in (gen.name or "").lower() or sub in (gen.therapeutic_class or "").lower()):
                warnings.append(
                    {
                        "code": "allergy",
                        "severity": _sev("allergy"),
                        "message": f"Patient allergy '{al.substance}' may match {gen.name}.",
                        "medicines_involved": [it.get("name") or gen.name],
                    }
                )

    # pregnancy / lactation banner
    if patient.is_pregnant or patient.is_lactating:
        for it in resolved:
            gen = it.get("generic")
            if not gen:
                continue
            cat = gen.pregnancy_category
            sev = "critical" if cat in ("D", "X") else _sev("pregnancy")
            warnings.append(
                {
                    "code": "pregnancy",
                    "severity": sev,
                    "message": f"{gen.name}: pregnancy category {cat or 'unknown'}. Review pregnancy/lactation text.",
                    "medicines_involved": [it.get("name") or gen.name],
                }
            )

    # age banner
    age = _age(patient.dob)
    bands = rules.get("age_bands", {})
    if age is not None and (age < bands.get("pediatric_max", 12) or age >= bands.get("geriatric_min", 65)):
        for it in resolved:
            gen = it.get("generic")
            if gen:
                warnings.append(
                    {
                        "code": "age",
                        "severity": _sev("age"),
                        "message": f"Patient age {age}: check age-group dosage reference for {gen.name} (reference only, doctor decides).",
                        "medicines_involved": [it.get("name") or gen.name],
                    }
                )

    # long duration
    threshold = rules.get("long_duration_days", 90)
    for it in resolved:
        d = it.get("duration_days")
        if d and d > threshold:
            warnings.append(
                {
                    "code": "long_duration",
                    "severity": _sev("long_duration"),
                    "message": f"Unusually long duration ({d} days) for {it.get('name') or 'medicine'}.",
                    "medicines_involved": [it.get("name") or "medicine"],
                }
            )

    # repeated medicine
    window = rules.get("repeat_window_days", 30)
    since = datetime.now(timezone.utc) - timedelta(days=window)
    for it in resolved:
        gid = it.get("generic_id")
        if not gid:
            continue
        prior = db.scalars(
            select(M.Prescription)
            .join(M.PrescriptionItem, M.PrescriptionItem.rx_id == M.Prescription.id)
            .where(
                M.Prescription.patient_id == patient.id,
                M.PrescriptionItem.generic_id == gid,
                M.Prescription.issued_at >= since,
                M.Prescription.status == "finalized",
            )
        ).all()
        if prior:
            dates = ", ".join(sorted({p.issued_at.strftime("%d %b %Y") for p in prior}))
            warnings.append(
                {
                    "code": "repeat",
                    "severity": _sev("repeat"),
                    "message": f"{it.get('name') or 'Medicine'} was prescribed to this patient within the last {window} days ({dates}).",
                    "medicines_involved": [it.get("name") or "medicine"],
                }
            )
    return warnings


def _generic_section(db: Session, generic_id: int, section: str) -> str | None:
    row = db.scalar(
        select(M.GenericContent).where(
            M.GenericContent.generic_id == generic_id,
            M.GenericContent.section == section,
            M.GenericContent.lang == "en",
        )
    )
    return row.text if row else None


def _text_mentions(text: str, needle: str) -> bool:
    if not text or not needle:
        return False
    for token in re.split(r"[,\s]+", needle.lower()):
        token = token.strip()
        if len(token) >= 5 and token in text.lower():
            return True
    return False


# --------------------------------------------------------------- panel detail
# The guards above answer "is anything wrong?". The two helpers below answer the
# doctor's follow-up questions — "what are this medicine's side effects?" and
# "do these two interact?" — so the Safety panel can show the detail, not just a
# pass/fail. Both read the existing catalogue (brand + generic content); nothing
# is invented, and a medicine with no recorded text yields an empty string so the
# UI can say "none recorded" rather than showing a blank.
def _clean(text: str | None, limit: int = 420) -> str:
    """Strip markup/entities and collapse whitespace for display."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def side_effects_for(db: Session, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-medicine side effects, from the generic content then the brand row."""
    out: list[dict[str, Any]] = []
    for it in items:
        gid = it.get("generic_id")
        brand_id = it.get("brand_id")
        gen = db.get(M.Generic, gid) if gid else None
        text = _generic_section(db, gid, "side_effects") if gid else None
        if not text and brand_id:
            brand = db.get(M.Brand, brand_id)
            text = brand.side_effects if brand else None
        name = it.get("name") or (gen.name if gen else "Medicine")
        out.append({"name": name, "text": _clean(text)})
    return out


def interactions_for(db: Session, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise interactions between the prescribed medicines.

    Curated rules (``interactions_curated``) win; otherwise the generic
    interaction text is scanned for a mention of the other medicine, which is the
    same signal the guard uses.
    """
    resolved: list[tuple[str, M.Generic | None]] = []
    for it in items:
        gid = it.get("generic_id")
        gen = db.get(M.Generic, gid) if gid else None
        resolved.append((it.get("name") or (gen.name if gen else "Medicine"), gen))

    out: list[dict[str, Any]] = []
    for i, (na, ga) in enumerate(resolved):
        for nb, gb in resolved[i + 1:]:
            if not ga or not gb:
                continue
            cur = db.scalar(
                select(M.InteractionCurated).where(
                    or_(
                        and_(func.lower(M.InteractionCurated.generic_a) == ga.name.lower(),
                             func.lower(M.InteractionCurated.generic_b) == gb.name.lower()),
                        and_(func.lower(M.InteractionCurated.generic_a) == gb.name.lower(),
                             func.lower(M.InteractionCurated.generic_b) == ga.name.lower()),
                    )
                )
            )
            if cur:
                out.append({"a": na, "b": nb, "severity": cur.severity or "warn",
                            "note": _clean(cur.note) or f"Recorded interaction between {ga.name} and {gb.name}."})
                continue
            a_inter = _generic_section(db, ga.id, "interaction") or ""
            b_inter = _generic_section(db, gb.id, "interaction") or ""
            a_text = (ga.name or "") + " " + (ga.therapeutic_class or "")
            b_text = (gb.name or "") + " " + (gb.therapeutic_class or "")
            if _text_mentions(a_inter, b_text) or _text_mentions(b_inter, a_text):
                out.append({"a": na, "b": nb, "severity": _sev("interaction"),
                            "note": f"Possible interaction between {ga.name} and {gb.name} (from the medicine database)."})
    return out
