"""Medicine relationship grouping for the detail page.

Groups (mutually exclusive — each candidate brand lands in at most one):
  alternatives    same generic + same strength + same form   (direct substitutes)
  other_forms     same generic + same strength + other form  (same dose, other route)
  other_strengths same generic + same form + other strength  (titration options)
  brand_family    same generic + same brand root, neither same strength nor same form

Every group carries a true ``*_count`` next to the (capped) list so the API can
never silently truncate: the earlier implementation returned a hard
``limit(30)`` over *all* same-generic brands with no count and no way for the
UI to know rows had been dropped (azithromycin has 331 same-generic brands).

Strength text is compared whitespace/case-normalised because the source catalog
contains formatting variants that describe the *same* strength
(e.g. ``"0.2% + 0.5%"`` vs ``"0.2%+0.5%"``). Comparing raw text hid those
genuine alternatives.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M

_WS = re.compile(r"\s+")
# The largest generics in the catalog hold 389 brands (Cefixime Trihydrate),
# so a 1000 cap means NO group can ever be truncated - the *_count fields
# remain as a truthful safety net rather than something the UI has to rely on.
CAP = 1000


def norm_strength(s: str | None) -> str:
    """Whitespace- and case-insensitive strength key ('500 mg' == '500 MG')."""
    if not s:
        return ""
    return _WS.sub("", s).lower()


def brand_root(name: str | None) -> str:
    """First token of a brand name: 'Napa Rapid' -> 'napa'."""
    if not name or not name.strip():
        return ""
    return _WS.split(name.strip())[0].lower()


def _card(b: M.Brand, comp_name: str | None, gen_name: str | None) -> dict:
    return {
        "id": b.id,
        "med_code": b.med_code,
        "name": b.name,
        "form": b.form_name,
        "strength": b.strength_text,
        "generic": gen_name,
        "generic_id": b.generic_id,
        "company": comp_name,
        "unit_price": float(b.unit_price) if b.unit_price is not None else None,
        "strip_price": float(b.strip_price) if b.strip_price is not None else None,
        "pack_size": b.pack_size,
        "pack_price": float(b.pack_price) if b.pack_price is not None else None,
        "pieces_per_strip": b.pieces_per_strip,
        "data_status": b.data_status,
        "completeness": b.completeness,
    }


def brand_card(db: Session, b: M.Brand) -> dict:
    """Card for a single brand (2 lookups — used for the page's own brand)."""
    gen = db.get(M.Generic, b.generic_id) if b.generic_id else None
    comp = db.get(M.Company, b.company_id) if b.company_id else None
    return _card(b, comp.name if comp else None, gen.name if gen else None)


def brands_for_generic(db: Session, generic_id: int | None) -> list[M.Brand]:
    """Every brand sharing a generic, company names eager-loaded.

    Previously each card triggered its own ``db.get(Company, ...)``, so a
    generic with 389 brands issued hundreds of round-trips and the detail page
    could take seconds to render. One query + one IN(...) for the companies.
    """
    if not generic_id:
        return []
    return list(
        db.scalars(
            select(M.Brand)
            .where(M.Brand.generic_id == generic_id)
            .order_by(M.Brand.id)
        ).all()
    )


def _price_key(c: dict) -> tuple:
    return (c["unit_price"] is None, c["unit_price"] or 0.0, c["name"] or "")


_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def sort_strength(s: str | None) -> tuple:
    """Order strengths by magnitude, not by text.

    Plain string sort put "100 mg" before "50 mg" and "5 mg" before "50 mg"
    on the brand-family list; the numeric key fixes the running order.
    """
    if not s:
        return (1, 0.0, "")
    m = _NUM.search(s)
    return (0, float(m.group(1)) if m else 0.0, s)


def _sort_strength_name(c: dict) -> tuple:
    return (sort_strength(c["strength"]), c["name"] or "")


def compute_relations(db: Session, brand: M.Brand, cap: int = CAP) -> dict:
    """Group every other brand that shares this brand's generic."""
    out = {
        "same_generic_total": 0,
        "alternatives": [],
        "alternatives_count": 0,
        "other_forms": [],
        "other_forms_count": 0,
        "other_strengths": [],
        "other_strengths_count": 0,
        "brand_family": [],
        "brand_family_count": 0,
    }
    if not brand.generic_id:
        return out

    rows = [r for r in brands_for_generic(db, brand.generic_id) if r.id != brand.id]
    out["same_generic_total"] = len(rows)
    if not rows:
        return out

    gen = db.get(M.Generic, brand.generic_id)
    gen_name = gen.name if gen else None

    comp_ids = {r.company_id for r in rows if r.company_id}
    comps: dict[int, str] = {}
    if comp_ids:
        comps = {
            c.id: c.name
            for c in db.scalars(select(M.Company).where(M.Company.id.in_(comp_ids))).all()
        }

    my_s = norm_strength(brand.strength_text)
    my_f = (brand.form_name or "").strip().lower()
    my_root = brand_root(brand.name)

    alts: list[dict] = []
    forms: list[dict] = []
    strs: list[dict] = []
    fam: list[dict] = []

    for r in rows:
        same_s = norm_strength(r.strength_text) == my_s
        same_f = (r.form_name or "").strip().lower() == my_f
        card = _card(r, comps.get(r.company_id), gen_name)
        if same_s and same_f:
            alts.append(card)
        elif same_s:
            forms.append(card)
        elif same_f:
            strs.append(card)
        elif my_root and brand_root(r.name) == my_root:
            fam.append(card)

    alts.sort(key=_price_key)
    forms.sort(key=lambda c: (norm_strength(c["strength"]), c["name"] or "", *_price_key(c)))
    strs.sort(key=lambda c: (sort_strength(c["strength"]), c["name"] or "", *_price_key(c)))
    fam.sort(key=lambda c: (c["name"] or "", sort_strength(c["strength"])))

    out["alternatives"] = alts[:cap]
    out["alternatives_count"] = len(alts)
    out["other_forms"] = forms[:cap]
    out["other_forms_count"] = len(forms)
    out["other_strengths"] = strs[:cap]
    out["other_strengths_count"] = len(strs)
    out["brand_family"] = fam[:cap]
    out["brand_family_count"] = len(fam)
    return out
