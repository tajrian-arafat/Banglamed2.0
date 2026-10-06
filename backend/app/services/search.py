"""Search & matching (SPEC 8.1): FTS prefix + RapidFuzz typo tolerance + ranking."""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M

BN_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize(q: str) -> str:
    q = (q or "").translate(BN_MAP).lower().strip()
    q = re.sub(r"[^\w\s\u0980-\u09FF]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q


def search_medicines(db: Session, q: str, limit: int = 20) -> list[dict]:
    nq = normalize(q)
    if not nq:
        return []
    rows = db.scalars(select(M.MedicineFts)).all()
    scored: list[tuple[float, M.MedicineFts]] = []
    for r in rows:
        hay = normalize(f"{r.brand} {r.generic} {r.company} {r.strength} {r.form}")
        if not hay:
            continue
        if hay.startswith(nq):
            score = 1.0
        elif nq in hay:
            score = 0.95
        else:
            score = fuzz.WRatio(nq, hay) / 100.0
        if score >= 0.6:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1].brand))
    out = []
    for score, r in scored[:limit]:
        out.append(
            {
                "brand_id": r.brand_id,
                "brand": r.brand,
                "generic": r.generic,
                "company": r.company,
                "strength": r.strength,
                "form": r.form,
                "score": round(score, 3),
            }
        )
    return out


def fuzzy_match_name(db: Session, name: str, limit: int = 8) -> list[dict]:
    """Used by the OCR interpreter: match a candidate token to brands."""
    nq = normalize(name)
    if not nq:
        return []
    rows = db.scalars(select(M.MedicineFts)).all()
    choices = {r.brand_id: normalize(r.brand) for r in rows if r.brand}
    results = process.extract(nq, choices, scorer=fuzz.WRatio, limit=limit)
    out = []
    by_id = {r.brand_id: r for r in rows}
    for _match, score, brand_id in results:
        r = by_id.get(brand_id)
        if not r:
            continue
        out.append(
            {
                "brand_id": r.brand_id,
                "brand": r.brand,
                "generic": r.generic,
                "company": r.company,
                "strength": r.strength,
                "form": r.form,
                "score": round(score / 100.0, 3),
            }
        )
    return out
