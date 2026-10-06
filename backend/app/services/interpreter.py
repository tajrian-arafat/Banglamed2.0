"""M8 prescription interpreter: quality check + OCR provider + typed fallback + fuzzy match."""
from __future__ import annotations

import io
import re
from typing import Any

from sqlalchemy.orm import Session

from ..core.config import get_settings
from .search import fuzzy_match_name

settings = get_settings()

DOSE_PATTERNS = [
    (r"1\s*[-+]\s*0\s*[-+]\s*1", {"morning": 1, "noon": 0, "evening": 0, "night": 1}),
    (r"1\s*[-+]\s*1\s*[-+]\s*1", {"morning": 1, "noon": 1, "evening": 1, "night": 0}),
    (r"0\s*[-+]\s*0\s*[-+]\s*1", {"morning": 0, "noon": 0, "evening": 0, "night": 1}),
    (r"1\s*[-+]\s*0\s*[-+]\s*0", {"morning": 1, "noon": 0, "evening": 0, "night": 0}),
    (r"1\s*[-+]\s*1\s*[-+]\s*0", {"morning": 1, "noon": 1, "evening": 0, "night": 0}),
    (r"1\s*[-+]\s*1\s*[-+]\s*1\s*[-+]\s*1", {"morning": 1, "noon": 1, "evening": 1, "night": 1}),
]
DURATION_RE = re.compile(r"(\d+)\s*(day|days|week|weeks|month|months|দিন|সপ্তাহ|মাস)", re.IGNORECASE)


def assess_quality(data: bytes) -> dict[str, Any]:
    """Blur / resolution / brightness heuristics. No external deps required."""
    try:
        from PIL import Image, ImageStat

        img = Image.open(io.BytesIO(data)).convert("L")
        w, h = img.size
        stat = ImageStat.Stat(img)
        brightness = round(stat.mean[0], 1)
        # crude sharpness: variance of a downscaled edge map
        small = img.resize((min(w, 200), min(h, 200)))
        px = list(small.getdata())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        sharpness = round(var ** 0.5, 1)
        issues = []
        if w < 600 or h < 600:
            issues.append("low_resolution")
        if brightness < 60:
            issues.append("too_dark")
        if brightness > 220:
            issues.append("too_bright")
        if sharpness < 25:
            issues.append("possibly_blurry")
        return {"width": w, "height": h, "brightness": brightness, "sharpness": sharpness,
                "issues": issues, "ok": not issues}
    except Exception as exc:
        return {"ok": True, "issues": [], "note": f"quality check skipped: {exc}"}


def _ocr_tesseract(data: bytes) -> str | None:
    try:
        import pytesseract  # type: ignore
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(data)))
    except Exception:
        return None


def _ocr_gemini(data: bytes) -> str | None:
    if not settings.gemini_api_key:
        return None
    try:
        import base64

        import httpx

        b64 = base64.b64encode(data).decode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
        body = {"contents": [{"parts": [{"text": "Transcribe all text from this prescription image verbatim."},
                                        {"inline_data": {"mime_type": "image/png", "data": b64}}]}]}
        r = httpx.post(url, json=body, timeout=30)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def run_ocr(data: bytes, db: Session) -> tuple[str | None, dict[str, Any]]:
    """Returns (ocr_text, parsed). Falls back to typed entry when no provider is configured."""
    text: str | None = None
    provider = settings.ocr_provider
    if provider == "tesseract":
        text = _ocr_tesseract(data)
    elif provider == "gemini":
        text = _ocr_gemini(data)
    if not text:
        return None, {"mode": "typed_fallback",
                      "message": "Automatic reading is not enabled. Please type the medicines from your prescription.",
                      "candidates": []}
    return text, parse_ocr_text(db, text)


def parse_ocr_text(db: Session, text: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates = []
    for ln in lines:
        if len(ln) < 3 or len(ln) > 60:
            continue
        if re.match(r"^[\d\W]+$", ln):
            continue
        matches = fuzzy_match_name(db, ln, limit=3)
        if matches and matches[0]["score"] >= 0.6:
            dose = None
            for pat, slots in DOSE_PATTERNS:
                if re.search(pat, ln):
                    dose = {"slots": slots, "unit": "tablet", "meal": "after"}
                    break
            dur = DURATION_RE.search(ln)
            duration = None
            if dur:
                duration = {"value": int(dur.group(1)), "unit": dur.group(2).lower()}
            candidates.append({"raw": ln, "matches": matches, "dose": dose, "duration": duration})
    return {"mode": "ocr", "candidates": candidates, "line_count": len(lines)}
