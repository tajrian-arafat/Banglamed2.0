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
  0.83  single token: query begins at a word boundary of a descriptive field
Rejected: an internal word that merely *contains* the query (e.g. the "-nil-"
inside "Unilor" for the query "tufnil") and fuzzy matches whose similarity is
not concentrated in a prefix of the brand name.

Performance (why this file was rewritten)
-----------------------------------------
The scoring rules above are unchanged — they are what make the results *right*.
What changed is how candidates reach them:

*   ``medicine_fts`` now carries pre-normalised columns (``brand_n``,
    ``generic_n``, ``company_n``, ``form_n``, ``strength_n``, ``first_token``,
    ``brand_root``) written once at import time via ``services/norm.py``, so
    scoring never re-normalises 25k strings per keystroke.
*   Candidate narrowing is *index-driven*. ``col >= q AND col < q+\\uffff`` is
    exactly ``LIKE 'q%'`` but usable by a BINARY index, which ``LIKE`` is not in
    SQLite — the difference between a full scan and an index seek.
*   Substring ("contains") clauses are only added when the cheap prefix pass is
    thin, so the common typeahead path stays on the index.
*   ``suggest_medicines`` is a prefix-only, index-only path for
    keystroke-by-keystroke suggestions; ``search_medicines`` is the full ranked
    path and takes a 'contains' fallback when prefixes find little.
*   Prices are fetched with the rows (one query) rather than a db.get per hit.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import models as M
from .norm import norm as normalize
from .norm import prefix_high

# A typo-tolerant fuzzy brand match is only trusted when the brand is close
# enough in absolute terms AND the query is a large fraction of the brand —
# this is what lets "celofn" -> "Celofen" through while keeping "tufnil" away
# from "Unilor".
FUZZY_MIN_WHOLE = 80.0   # fuzz.ratio(nq, brand_norm)
FUZZY_MIN_RATIO = 0.75   # len(nq) / len(brand_norm)
FUZZY_MAX_RATIO = 1.40   # lengths must be comparable — no short-brand matches

# Prefix pass: how many index candidates are enough to skip the substring pass.
PREFIX_ENOUGH = 60
# Hard ceiling on rows pulled into Python for scoring, so one pathological query
# (a single vowel, say) can never stall a keystroke.
CANDIDATE_CAP = 4000


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-z\u0980-\u09ff]+", text) if w]


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
    # Require comparable lengths: this keeps a short unrelated brand such as
    # "Elo"/"OR" away from a long query like "celofn".
    length_ratio = len(nq) / len(brand_norm)
    return FUZZY_MIN_RATIO <= length_ratio <= FUZZY_MAX_RATIO


def _score_row(r: M.MedicineFts, nq: str, tokens: list[str]) -> float | None:
    """Return a relevance score for one catalog row, or None when irrelevant.

    ``r`` already carries normalised text, so no per-row normalisation happens
    here — that is the point of the indexed columns.
    """
    brand = r.brand_n or ""
    generic = r.generic_n or ""
    company = r.company_n or ""
    strength = r.strength_n or ""
    form = r.form_n or ""
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


def _prefix_clauses(nq: str, *, first2: str) -> list:
    """Index-usable prefix ranges across every searchable column."""
    lo, hi = nq, prefix_high(nq)
    clauses = [
        and_(M.MedicineFts.brand_n >= lo, M.MedicineFts.brand_n < hi),
        and_(M.MedicineFts.generic_n >= lo, M.MedicineFts.generic_n < hi),
        and_(M.MedicineFts.company_n >= lo, M.MedicineFts.company_n < hi),
        and_(M.MedicineFts.first_token >= lo, M.MedicineFts.first_token < hi),
        and_(M.MedicineFts.brand_root >= lo, M.MedicineFts.brand_root < hi),
        and_(M.MedicineFts.form_n >= lo, M.MedicineFts.form_n < hi),
    ]
    if first2 and first2 != nq:
        # Typo recall: the whole point of a typo is that the prefix differs, so
        # prefix on the first TWO characters of the brand only.
        clauses.append(
            and_(M.MedicineFts.brand_n >= first2, M.MedicineFts.brand_n < prefix_high(first2))
        )
    return clauses


def _substring_clauses(nq: str) -> list:
    """Full-scan 'contains' clauses — only used when the prefix pass is thin."""
    like = f"%{nq}%"
    return [
        M.MedicineFts.brand_n.like(like),
        M.MedicineFts.generic_n.like(like),
        M.MedicineFts.company_n.like(like),
        M.MedicineFts.strength_n.like(like),
        M.MedicineFts.form_n.like(like),
        M.MedicineFts.aliases.like(like),
    ]


def _fetch(db: Session, clauses: list, n: int) -> list[M.MedicineFts]:
    return list(db.scalars(select(M.MedicineFts).where(or_(*clauses)).limit(n)).all())


def _rank(rows: list[M.MedicineFts], nq: str, tokens: list[str], limit: int) -> list[M.MedicineFts]:
    scored: list[tuple[float, int, str, M.MedicineFts]] = []
    for r in rows:
        score = _score_row(r, nq, tokens)
        if score is not None:
            # tie-break: shorter brand first (closer to the query), then A→Z
            scored.append((score, len(r.brand_n or ""), (r.brand or ""), r))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [s[3] for s in scored[:limit]]


def _with_prices(db: Session, rows: list[M.MedicineFts]) -> list[dict]:
    """Attach price/pack fields in ONE query instead of a db.get per hit."""
    if not rows:
        return []
    ids = [r.brand_id for r in rows if r.brand_id]
    brands: dict[int, M.Brand] = {}
    if ids:
        brands = {b.id: b for b in db.scalars(select(M.Brand).where(M.Brand.id.in_(ids))).all()}
    out: list[dict] = []
    for r in rows:
        b = brands.get(r.brand_id)
        out.append({
            "brand_id": r.brand_id,
            "brand": r.brand,
            "generic": r.generic,
            "company": r.company,
            "strength": r.strength,
            "form": r.form,
            "unit_price": float(b.unit_price) if b is not None and b.unit_price is not None else None,
            "strip_price": float(b.strip_price) if b is not None and b.strip_price is not None else None,
            "pieces_per_strip": b.pieces_per_strip if b is not None else None,
            "pack_size": b.pack_size if b is not None else None,
        })
    return out


def search_medicines(db: Session, q: str, limit: int = 20) -> list[dict]:
    """Ranked search over the catalog. Index-first, with a 'contains' fallback."""
    nq = normalize(q)
    if not nq:
        return []
    tokens = nq.split()

    rows = _fetch(db, _prefix_clauses(nq, first2=nq[:2] if len(nq) >= 2 else ""), PREFIX_ENOUGH + 1)
    if len(rows) <= PREFIX_ENOUGH:
        # Thin prefix result: fall back to a full 'contains' scan so a query that
        # only ever appears mid-word ("mycin", "-pril") still finds its rows.
        seen = {r.id for r in rows}
        for r in _fetch(db, _substring_clauses(nq), CANDIDATE_CAP):
            if r.id not in seen:
                rows.append(r)
                seen.add(r.id)
    return _with_prices(db, _rank(rows, nq, tokens, limit))


def suggest_medicines(db: Session, q: str, limit: int = 8) -> list[dict]:
    """Keystroke typeahead: prefix-only and index-only, so it stays fast.

    Answers on the very first character. Falls back to the ranked path only when
    a prefix finds nothing at all, which keeps a genuine typo query usable while
    keeping the common path on the index.
    """
    nq = normalize(q)
    if not nq:
        return []
    rows = _fetch(db, _prefix_clauses(nq, first2=nq[:2] if len(nq) >= 2 else ""), 400)
    if not rows:
        return search_medicines(db, q, limit=limit)
    return _with_prices(db, _rank(rows, nq, nq.split(), limit))


def fuzzy_match_name(db: Session, name: str, limit: int = 8) -> list[dict]:
    """Used by the OCR interpreter: match a candidate token to brands.

    Kept deliberately *recall*-oriented (an OCR token may be misspelt) but is
    still gated on a minimum similarity so random names do not surface.
    """
    nq = normalize(name)
    if not nq:
        return []
    rows = db.scalars(select(M.MedicineFts)).all()
    choices = {r.brand_id: (r.brand_n or normalize(r.brand)) for r in rows if r.brand}
    results = process.extract(nq, choices, scorer=fuzz.WRatio, limit=limit, score_cutoff=60)
    out: list[dict] = []
    by_id = {r.brand_id: r for r in rows}
    for _match, score, brand_id in results:
        r = by_id.get(brand_id)
        if not r:
            continue
        out.append({
            "brand_id": r.brand_id,
            "brand": r.brand,
            "generic": r.generic,
            "company": r.company,
            "strength": r.strength,
            "form": r.form,
            "score": round(score / 100.0, 3),
        })
    return out
