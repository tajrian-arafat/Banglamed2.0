"""M8 interpreter endpoints (typed fallback + QR resolve)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..services.search import fuzzy_match_name

router = APIRouter(prefix="/api/interpreter", tags=["interpreter"])


@router.get("/match")
def match(name: str, limit: int = 8, db: Session = Depends(get_db)):
    return {"query": name, "candidates": fuzzy_match_name(db, name, limit=limit)}


@router.get("/capabilities")
def capabilities():
    from ..core.config import get_settings

    s = get_settings()
    return {"ocr_provider": s.ocr_provider, "auto_read_enabled": s.ocr_provider in ("tesseract", "gemini"),
            "typed_fallback": True}
