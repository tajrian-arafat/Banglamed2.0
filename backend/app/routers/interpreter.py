"""M8 interpreter endpoints — OCR reading, matching, and full analysis.

*   ``GET  /api/interpreter/match``        fuzzy-match a typed name to brands
*   ``GET  /api/interpreter/capabilities`` what reading is available right now
*   ``POST /api/interpreter/analyze``      price + safety for a set of medicines
                                          and tests (used by the upload page and
                                          the manual-entry fallback)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models as M
from ..core.db import get_db
from ..deps import get_current_user
from ..services.analysis import analyse
from ..services.interpreter import ocr_text
from ..services.search import fuzzy_match_name

router = APIRouter(prefix="/api/interpreter", tags=["interpreter"])


class AnalyzeMedicine(BaseModel):
    brand_id: int | None = None
    name: str | None = None
    dose: dict | None = None
    duration_days: int | None = None


class AnalyzeTest(BaseModel):
    test_id: int | None = None
    name: str | None = None


class AnalyzeIn(BaseModel):
    patient_id: int | None = None
    medicines: list[AnalyzeMedicine] = Field(default_factory=list)
    tests: list[AnalyzeTest] = Field(default_factory=list)


@router.get("/match")
def match(name: str, limit: int = 8, db: Session = Depends(get_db)):
    return {"query": name, "candidates": fuzzy_match_name(db, name, limit=limit)}


@router.get("/capabilities")
def capabilities():
    from ..core.config import get_settings

    s = get_settings()
    provider = (s.ocr_provider or "auto").strip().lower()
    # "auto" (and the legacy "null"/empty values the shipped .env carried) mean:
    # Gemini if a key is present, otherwise Tesseract. Report what will actually
    # run rather than the raw setting, so the UI can tell the user the truth
    # about whether automatic reading is on.
    if provider in ("", "null", "none", "auto"):
        provider = "auto"
    if provider in ("off", "disabled", "false"):
        effective = "off"
    elif provider == "auto":
        effective = "gemini" if s.gemini_api_key else "tesseract"
    else:
        effective = provider
    available = effective in ("tesseract", "gemini")
    if effective == "tesseract":
        try:
            import pytesseract  # noqa: F401

            available = True
        except Exception:
            available = False
    return {
        "ocr_provider": effective,
        "configured": s.ocr_provider,
        "auto_read_enabled": available,
        "typed_fallback": True,
        "manual_entry": True,
    }


@router.post("/analyze")
def analyze(payload: AnalyzeIn, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Price and safety-check a set of medicines and tests.

    Works identically for OCR-extracted rows and hand-typed rows, which is what
    makes the manual-entry fallback a first-class path rather than a dead end.
    """
    patient = db.get(M.Patient, payload.patient_id) if payload.patient_id else None
    # Only the patient's own account (or an admin) may run a safety check against
    # their record; otherwise analyse without the patient context.
    if patient is not None and patient.account_id != user.id and user.role != "system_admin":
        patient = None
    return analyse(
        db,
        patient=patient,
        medicines=[m.model_dump() for m in payload.medicines],
        tests=[t.model_dump() for t in payload.tests],
    )
