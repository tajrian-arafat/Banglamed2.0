"""Search & matching (SPEC 8.1): tiered relevance with strict precision.

Design goal: a suggestion must *genuinely* match the query. Free-form fuzzy
scoring against the concatenated haystack used to surface unrelated brands
(e.g. "Unilor" for "tufnil") because short queries score high on partial
substring overlap. This module instead assigns each candidate to a graded tier
and rejects anything that is only a weak, non-prefix fuzzy coincidence.

Tiers (best first)
  1.00  brand starts with the query        ("tufnil" -> Tufnil)
  1.00  brand equals a query token
  0.97  query / brand is a substring of the other
  0.92  one field (generic / company / alias) starts with the query
  0.88  start of a word inside a field has the query as prefix
  0.86  brand fuzzy matches with a near-identical short name (typo tolerance)
  0.84  every query token is a prefix of some word in one field
  0.78  all query tokens appear across the combined fields
Rejected: an internal word that merely *contains* the query (e.g. the "-nil-"
inside "Unilor" for the query "tufnil") and fuzzy matches whose similarity is
not concentrated in a prefix of the brand name.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as M

BN_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# A typo-tolerant fuzzy brand match is only trusted when the brand is close
# enough in absolute terms AND the query is a large fraction of the brand —
# this is what lets "celofn" -> "Celofen" through while keeping "tufnil" away
# from "Unilor".
FUZZY_MIN_WHOLE = 80.0   # fuzz.ratio(nq, brand_norm)
FUZZY_MIN_RATIO = 0.75   # len(nq) / len(brand_norm)
FUZZY_MAX_RATIO = 1.40   # lengths must be comparable — no short-brand matches


def normalize(q: str) -> str:
    q = (q or "").translate(BN_MAP).lower().strip()
    q = re.sub(r"[^\w\s\u0980-\u09FF]", " ", q)
    q = re.sub(r"\s+", " ", q)
    return q


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-z\u0980-\u09FF]+", text.lower()) if w]


def _is_word_prefix(text_norm: str, q: str) -> bool:
    """True when the query is a prefix of one of the words in ``text_norm``."""
    return any(w.startswith(q) for w in _words(text_norm))


def _all_tokens_prefix(text_norm: str, tokens: list[str]) -> bool:
    ws = _words(text_norm)
    return bool(ws) and all(any(w.startswith(t) for w in ws) for t in tokens)


def _all_tokens_present(text_norm: str, tokens: list[str]) -> bool:
    return all(t in text_norm for t in tokens)


def _fuzzy_brand(nq: str, brand_norm: str) -> bool:
    """Conservative whole-string typo tolerance on the brand name only."""
    if not brand_norm or not nq:
        return False
    if fuzz.ratio(nq, brand_norm) < FUZZY_MIN_WHOLE:
        return False
    # Anchor on the first TWO characters, matching the SQL candidate pre-filter.
    # A single-character anchor missed every typo landing in position 2
    # ("celofn" vs "Celofen") while still admitting unrelated same-suffix
    # collisions; two characters is the smallest anchor that keeps recall.
    if len(nq) >= 2 and len(brand_norm) >= 2:
        if nq[:2] != brand_norm[:2]:
            return False
    elif nq[0] != brand_norm[0]:
        return False
    # Require comparable lengths: this is what keeps a short unrelated brand
    # such as "Elo"/"OR" away from a long query like "celofn".
    length_ratio = len(nq) / len(brand_norm)
    return FUZZY_MIN_RATIO <= length_ratio <= FUZZY_MAX_RATIO


def _score_row(r: M.MedicineFts, q: str, nq: str, tokens: list[str]) -> float | None:
    """Return a relevance score for one catalog row, or None when irrelevant."""
    brand = normalize(r.brand)
    generic = normalize(r.generic)
    company = normalize(r.company)
    strength = normalize(r.strength)
    form = normalize(r.form)
    alias = normalize(r.aliases)
    fields = [f for f in (brand, generic, company, alias, strength, form) if f]
    if not fields:
        return None

    # 1. brand-level matches (the strongest signal for a brand catalog)
    if brand.startswith(nq):
        return 1.0 if brand == nq else 0.99
    if brand and nq in brand:
        return 0.97
    # A brand contained in the query only counts at a word boundary and when
    # it is substantial ("napa" in "napa extra") — never a fragment buried
    # mid-word ("eclo" inside "seclogen", "azole" inside "omeprazole").
    if brand and len(brand) >= 4:
        if re.search(r"(?:^|[\s\-/])" + re.escape(brand) + r"(?=$|[\s\-/])", nq):
            return 0.97

    # 2. another field begins with the query (generic, company, alias)
    for f in (generic, company, alias):
        if f and f.startswith(nq):
            return 0.92

    # 3. the query is a prefix of a word inside a field
    for f in fields:
        if _is_word_prefix(f, nq):
            return 0.88

    # 4. conservative whole-brand typo tolerance ("celofn" -> "Celofen").
    #    Only for a single token: comparing a multi-word query against one
    #    brand string would let unrelated brands through on shared words.
    if len(tokens) == 1 and _fuzzy_brand(nq, brand):
        return 0.86

    # multi-token queries: every token must land somewhere
    if len(tokens) > 1:
        if any(_all_tokens_prefix(f, tokens) for f in fields):
            return 0.84
        if _all_tokens_present(" ".join(fields), tokens):
            return 0.78
        return None

    # 5. single token: accept a contiguous substring that begins at a word
    #    boundary of a descriptive field ("napa" inside "napa extra").
    for f in (generic, company, alias, strength, form):
        if f and re.search(r"(?:^|[\s\-/])" + re.escape(nq), f):
            return 0.83

    # Deliberately NOT matched: a query appearing in the *middle* of an
    # unrelated brand ("tufnil" inside "Un-i-lor"). That was the reported bug.
    return None


def search_medicines(db: Session, q: str, limit: int = 20) -> list[dict]:
    nq = normalize(q)
    if not nq:
        return []
    tokens = nq.split()
    # Narrow candidates in SQL first: scoring all 25k rows in Python costs
    # ~1.7s, which is far too slow for live suggestions. The clauses cover
    # every tier below, plus "same first letter" so typo tolerance still has
    # candidates. Scoring then applies the strict rules to this small set.
    brand = func.lower(M.MedicineFts.brand)
    generic = func.lower(M.MedicineFts.generic)
    company = func.lower(M.MedicineFts.company)
    alias = func.lower(M.MedicineFts.aliases)
    pattern = f"%{nq}%"
    # Typo recall cannot be expressed with a SQL prefix test: the whole point of
    # a typo is that the prefix differs ("celofn" vs "Celofen" - third letter).
    # Prefixing on the FIRST TWO characters keeps recall for the realistic case
    # (a slip in the middle/end of the word) while still bounding the candidate
    # set. Prefixing on one character pulled in the entire 'a' block, and the
    # old ``LIKE 'a%'``-only clause dropped every brand whose typo was in
    # character 2; both are wrong for different reasons.
    first2 = nq[:2] if nq else ""
    clauses = [
        brand.like(f"{nq}%"),
        brand.like(pattern),
        generic.like(f"{nq}%"),
        generic.like(pattern),
        company.like(f"{nq}%"),
        alias.like(pattern),
        M.MedicineFts.strength.like(pattern),
        M.MedicineFts.form.like(pattern),
    ]
    if first2:
        clauses.append(brand.like(f"{first2}%"))  # typo recall, still strictly scored
    candidates = db.scalars(
        select(M.MedicineFts).where(or_(*clauses)).limit(6000)
    ).all()
    rows = candidates

    scored: list[tuple[float, int, str, M.MedicineFts]] = []
    for r in rows:
        score = _score_row(r, q, nq, tokens)
        if score is not None:
            # tie-break: shorter brand first (closer to the query), then A→Z
            scored.append((score, len(normalize(r.brand)), (r.brand or ""), r))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    out: list[dict] = []
    for score, _blen, _b, r in scored[:limit]:
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
    """Used by the OCR interpreter: match a candidate token to brands.

    Kept deliberately *recall*-oriented (an OCR token may be misspelt) but is
    still gated on a minimum similarity so random names do not surface.
    """
    nq = normalize(name)
    if not nq:
        return []
    rows = db.scalars(select(M.MedicineFts)).all()
    choices = {r.brand_id: normalize(r.brand) for r in rows if r.brand}
    results = process.extract(nq, choices, scorer=fuzz.WRatio, limit=limit, score_cutoff=60)
    out: list[dict] = []
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
