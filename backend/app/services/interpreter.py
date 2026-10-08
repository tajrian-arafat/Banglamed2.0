"""M8 prescription interpreter — reading a photographed prescription.

This is the project's key differentiator, so the module is deliberately more than
a thin OCR wrapper. Three things had to be true for it to work on real photos:

1.  **Preprocessing.** A phone photo of a prescription is rarely OCR-ready: it is
    over-exposed (a white page under a lamp reads as brightness ~246, which the
    old quality check flagged as "too bright" and then refused to read), often
    slightly rotated, and low-contrast. ``preprocess_variants`` produces several
    normalised renderings — autocontrast grayscale, sharpened, and a locally
    binarised copy — and the OCR pass keeps whichever one actually yields the
    most medicine matches, instead of trusting a single fixed pipeline.

2.  **Provider chain.** Gemini (when a key is configured) is tried first because
    it reads handwriting and layout far better than a classical engine; Tesseract
    is the always-available fallback. Both are optional: when neither is present
    the endpoint degrades to the typed/manual path rather than failing, which is
    what the previous version did *unconditionally* (``OCR_PROVIDER=null`` meant
    "Automatic reading is not enabled" for every upload, however good the photo).

3.  **Extraction.** OCR text is split into lines, each line is stripped of dose
    noise ("Tab.", "1+0+1", "x 7 days", "after meal") and matched against the
    25k-brand catalog *and* the 108-test catalog. Matching is recall-oriented (an
    OCR token is frequently misspelt) but gated on a similarity floor so random
    words do not surface as medicines.
"""
from __future__ import annotations

import io
import re
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.config import get_settings
from .norm import norm as normalize

settings = get_settings()

# --------------------------------------------------------------------- patterns
DOSE_PATTERNS = [
    (r"1\s*[-+]\s*0\s*[-+]\s*1", {"morning": 1, "noon": 0, "evening": 0, "night": 1}),
    (r"1\s*[-+]\s*1\s*[-+]\s*1", {"morning": 1, "noon": 1, "evening": 1, "night": 0}),
    (r"0\s*[-+]\s*0\s*[-+]\s*1", {"morning": 0, "noon": 0, "evening": 0, "night": 1}),
    (r"1\s*[-+]\s*0\s*[-+]\s*0", {"morning": 1, "noon": 0, "evening": 0, "night": 0}),
    (r"1\s*[-+]\s*1\s*[-+]\s*0", {"morning": 1, "noon": 1, "evening": 0, "night": 0}),
    (r"1\s*[-+]\s*1\s*[-+]\s*1\s*[-+]\s*1", {"morning": 1, "noon": 1, "evening": 1, "night": 1}),
    (r"\b1\s*[-+]\s*1\b", {"morning": 1, "noon": 0, "evening": 1, "night": 0}),
    (r"\b1\s*[-+]\s*0\b", {"morning": 1, "noon": 0, "evening": 0, "night": 0}),
    (r"\b0\s*[-+]\s*1\b", {"morning": 0, "noon": 0, "evening": 0, "night": 1}),
]
DURATION_RE = re.compile(
    r"(\d+)\s*(day|days|week|weeks|month|months|দিন|সপ্তাহ|মাস)", re.IGNORECASE
)
# Frequency shorthand a doctor writes instead of a 1+0+1 grid.
FREQ_MAP = {
    "od": {"morning": 1, "noon": 0, "evening": 0, "night": 0},
    "bd": {"morning": 1, "noon": 0, "evening": 1, "night": 0},
    "bid": {"morning": 1, "noon": 0, "evening": 1, "night": 0},
    "tds": {"morning": 1, "noon": 1, "evening": 1, "night": 0},
    "tid": {"morning": 1, "noon": 1, "evening": 1, "night": 0},
    "qid": {"morning": 1, "noon": 1, "evening": 1, "night": 1},
    "qds": {"morning": 1, "noon": 1, "evening": 1, "night": 1},
    "hs": {"morning": 0, "noon": 0, "evening": 0, "night": 1},
    "nocte": {"morning": 0, "noon": 0, "evening": 0, "night": 1},
    "sos": {"morning": 0, "noon": 0, "evening": 0, "night": 0},
}
MEAL_MAP = {
    "after food": "after", "after meal": "after", "pc": "after", "p.c": "after",
    "before food": "before", "before meal": "before", "ac": "before", "a.c": "before",
    "empty stomach": "empty_stomach", "empty": "empty_stomach",
    "bedtime": "bedtime", "at night": "bedtime",
}

# Words that are never a drug name — stripped before matching so "Tab." and
# "1+0+1" cannot drag a fuzzy match toward the wrong brand.
NOISE = {
    "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules",
    "syr", "syrup", "susp", "suspension", "inj", "injection", "drop", "drops",
    "oint", "ointment", "cream", "gel", "lotion", "spray", "inhaler", "sachet",
    "powder", "sol", "solution", "iv", "im", "po", "oral", "rx", "sig", "dr",
    "doctor", "patient", "name", "age", "sex", "date", "diagnosis", "advice",
    "complaint", "complaints", "investigation", "investigations", "test", "tests",
    "mg", "ml", "gm", "g", "mcg", "iu", "kg", "cc", "puff", "puffs", "unit",
    "units", "day", "days", "week", "weeks", "month", "months", "morning",
    "noon", "evening", "night", "after", "before", "meal", "food", "stomach",
    "empty", "continue", "as", "needed", "sos", "prn", "stat", "bd", "tds",
    "qid", "od", "hs", "nocte", "pc", "ac", "x", "no", "sl", "total", "each",
    "and", "with", "for", "the", "of", "to", "in", "on", "at", "by", "or",
}

# A line must be at least this long to be worth matching, and no longer than
# this (a longer "line" is a paragraph of instructions, not a drug entry).
MIN_LINE = 3
MAX_LINE = 70

# Similarity floors. Medicines are matched more loosely than tests because a
# handwritten brand is far more likely to be misspelt than a printed test name.
MED_FLOOR = 72
TEST_FLOOR = 80


# ------------------------------------------------------------------- quality
def assess_quality(data: bytes) -> dict[str, Any]:
    """Blur / resolution / brightness heuristics.

    The thresholds are deliberately *informational*: a bright, high-resolution
    scan is perfectly readable after autocontrast, so brightness alone must not
    be reported as a blocker. Only genuinely unreadable input (tiny, or almost
    entirely black) is flagged as an issue.
    """
    try:
        from PIL import Image, ImageOps, ImageStat

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        w, h = img.size
        stat = ImageStat.Stat(img)
        brightness = round(stat.mean[0], 1)
        small = img.resize((min(w, 200), min(h, 200)))
        px = list(small.getdata())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        sharpness = round(var ** 0.5, 1)
        issues: list[str] = []
        notes: list[str] = []
        if max(w, h) < 500:
            issues.append("low_resolution")
        if brightness < 45:
            issues.append("too_dark")
        elif brightness > 252:
            notes.append("very_bright")
        if sharpness < 18:
            issues.append("possibly_blurry")
        return {
            "width": w, "height": h, "brightness": brightness, "sharpness": sharpness,
            "issues": issues, "notes": notes, "ok": not issues,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": True, "issues": [], "notes": [], "note": f"quality check skipped: {exc}"}


# --------------------------------------------------------------- preprocessing
def preprocess_variants(data: bytes) -> list[tuple[str, Any]]:
    """Return several OCR-ready renderings of the photo, best-effort.

    Each variant is a ``(label, PIL.Image)`` pair. The caller OCRs them and keeps
    whichever produces the most catalog matches, so a photo that defeats one
    normalisation still has a chance through another.
    """
    from PIL import Image, ImageFilter, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    g = img.convert("L")

    w, h = g.size
    # Upscale small photos: Tesseract wants roughly 30px of glyph height, and a
    # 600px-wide phone crop simply does not have it.
    if max(w, h) < 1800:
        scale = 1800 / max(w, h)
        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    variants: list[tuple[str, Any]] = []

    # 1. Autocontrast + unsharp: fixes the over-exposed white-page case.
    ac = ImageOps.autocontrast(g, cutoff=1)
    variants.append(("autocontrast", ac))
    variants.append(("sharpened", ac.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))))

    # 2. Locally binarised: helps faint pencil / low-contrast print.
    try:
        import numpy as np

        arr = np.asarray(ac, dtype=np.float32)
        # Box-blur the image to get a local mean, then threshold against it.
        k = max(15, (min(arr.shape) // 25) | 1)
        pad = k // 2
        padded = np.pad(arr, pad, mode="edge")
        csum = padded.cumsum(0).cumsum(1)
        csum = np.pad(csum, ((1, 0), (1, 0)))
        local = (
            csum[k:, k:] - csum[:-k, k:] - csum[k:, :-k] + csum[:-k, :-k]
        ) / float(k * k)
        binary = np.where(arr > local - 6, 255, 0).astype("uint8")
        variants.append(("binarised", Image.fromarray(binary)))
    except Exception:
        # numpy is optional; the two variants above are enough to be useful.
        pass

    return variants


# ------------------------------------------------------------------------ OCR
def _tesseract_text(img: Any) -> str | None:
    try:
        import pytesseract  # type: ignore

        # psm 6 = "assume a single uniform block of text", which is what a
        # prescription body is; psm 4 handles the multi-column pad layout.
        best = ""
        for psm in (6, 4):
            try:
                txt = pytesseract.image_to_string(img, lang="eng", config=f"--oem 3 --psm {psm}")
            except Exception:
                continue
            if len(txt.strip()) > len(best.strip()):
                best = txt
        return best or None
    except Exception:
        return None


def _gemini_text(data: bytes) -> str | None:
    """Gemini vision transcription — best for handwriting, when a key exists."""
    if not settings.gemini_api_key:
        return None
    try:
        import base64

        import httpx

        b64 = base64.b64encode(data).decode()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={settings.gemini_api_key}"
        )
        prompt = (
            "This is a photograph of a doctor's prescription. Transcribe ALL text "
            "verbatim, one entry per line. Preserve medicine names, strengths, "
            "dosage (e.g. 1+0+1), duration (e.g. 7 days) and any test names. "
            "Do not translate, summarise or explain — output only the text."
        )
        body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                ]
            }]
        }
        r = httpx.post(url, json=body, timeout=45)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def ocr_text(data: bytes) -> tuple[str | None, str]:
    """Return ``(text, provider)``. ``provider`` is ``"none"`` when nothing ran.

    ``null``/empty/``auto`` all mean "use whatever is available": Gemini when a
    key is configured, otherwise the bundled Tesseract engine. Only an explicit
    ``off``/``disabled`` turns reading off — the old behaviour, where the shipped
    ``OCR_PROVIDER=null`` silently disabled reading for every upload, is exactly
    the bug this feature exists to fix.
    """
    provider = (settings.ocr_provider or "auto").strip().lower()
    if provider in ("", "null", "none", "auto"):
        provider = "auto"
    if provider in ("off", "disabled", "false"):
        return None, "none"

    if provider in ("auto", "gemini") and settings.gemini_api_key:
        txt = _gemini_text(data)
        if txt and txt.strip():
            return txt, "gemini"

    if provider in ("auto", "tesseract", "gemini"):
        # Try every preprocessing variant and keep the richest transcription.
        best: str | None = None
        for _label, img in preprocess_variants(data):
            txt = _tesseract_text(img)
            if txt and len(txt.strip()) > len((best or "").strip()):
                best = txt
        if best and best.strip():
            return best, "tesseract"

    return None, "none"


# ------------------------------------------------------------------ extraction
def _clean_line(line: str) -> str:
    """Strip dose/frequency/meal noise, leaving the drug-name-ish remainder."""
    s = line.strip()
    s = re.sub(r"^\s*(?:\d+[\.\)]\s*|[-•*]\s*)", "", s)          # leading "1." / "-"
    s = re.sub(r"\b\d+\s*[-+]\s*\d+(?:\s*[-+]\s*\d+){0,2}\b", " ", s)  # 1+0+1
    s = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|ml|gm|g|mcg|iu|%)\b", " ", s, flags=re.I)
    s = re.sub(r"\b(?:x|for)\s*\d+\s*(?:day|days|week|weeks|month|months)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*(?:day|days|week|weeks|month|months)\b", " ", s, flags=re.I)
    s = re.sub(r"[^\w\s\u0980-\u09ff+%./-]", " ", s)
    words = [w for w in s.split() if w.lower().strip(".") not in NOISE]
    return " ".join(words).strip()


def _dose_from_line(line: str) -> dict[str, Any] | None:
    for pat, slots in DOSE_PATTERNS:
        if re.search(pat, line):
            return {"slots": slots, "unit": "tablet", "meal": _meal_from_line(line)}
    low = line.lower()
    for key, slots in FREQ_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", low):
            return {"slots": slots, "unit": "tablet", "meal": _meal_from_line(line)}
    # OCR noise fallback: a "1+0+1" grid often comes back as "1404+0" or
    # "14+14+1" because the separators are misread as digits. Take the digit
    # groups joined by "+" and treat any group containing a non-zero digit as a
    # dose, which recovers the intended pattern instead of dropping the dose.
    groups = re.findall(r"\d+", line)
    if 2 <= len(groups) <= 4 and "+" in line:
        slots_list = [1 if any(c != "0" for c in g) else 0 for g in groups]
        keys = ["morning", "noon", "evening", "night"]
        slots = {k: 0 for k in keys}
        for k, v in zip(keys, slots_list):
            slots[k] = v
        if any(slots.values()):
            return {"slots": slots, "unit": "tablet", "meal": _meal_from_line(line)}
    return None


def _meal_from_line(line: str) -> str:
    low = line.lower()
    for phrase, meal in MEAL_MAP.items():
        if phrase in low:
            return meal
    return "after"


def _duration_from_line(line: str) -> dict[str, Any] | None:
    m = DURATION_RE.search(line)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("week") or unit == "সপ্তাহ":
        value, unit = value * 7, "day"
    elif unit.startswith("month") or unit == "মাস":
        value, unit = value * 30, "day"
    elif unit == "দিন":
        unit = "day"
    return {"value": value, "unit": unit}


def _brand_index(db: Session) -> dict[str, list[M.MedicineFts]]:
    """Normalised brand name -> the catalog rows carrying it.

    A brand name is not unique (the same name is sold by several companies), so
    the value is a list; the first row is used for display and the rest are
    available if a caller wants to disambiguate.
    """
    rows = db.scalars(select(M.MedicineFts)).all()
    by_name: dict[str, list[M.MedicineFts]] = {}
    for r in rows:
        n = r.brand_n or normalize(r.brand)
        if n:
            by_name.setdefault(n, []).append(r)
    return by_name


def _test_index(db: Session) -> dict[str, M.LabTest]:
    """Normalised test name (and each alias) -> the test row."""
    rows = db.scalars(select(M.LabTest)).all()
    by_name: dict[str, M.LabTest] = {}
    for t in rows:
        for cand in [t.name, *(t.aliases or "").split(",")]:
            n = normalize(cand)
            if n:
                by_name.setdefault(n, t)
    return by_name


# Lines that are section headers or patient/doctor metadata, never a drug entry.
_HEADER_RE = re.compile(
    r"\b(investigation|advice|diagnosis|complaint|signature|seal|rx\s*no|"
    r"patient|doctor|hospital|clinic|reg\.?\s*no|mbbs|fcps|md\b|date|age|sex)\b",
    re.IGNORECASE,
)


def _form_hint(line: str) -> str | None:
    """Which dosage form the line asks for, from the "Tab."/"Cap." prefix."""
    low = line.lower()
    if re.search(r"\b(tab|tablet|tabs)\b", low):
        return "tablet"
    if re.search(r"\b(cap|caps|capsule)\b", low):
        return "capsule"
    if re.search(r"\b(syr|syrup|susp|suspension)\b", low):
        return "suspension"
    if re.search(r"\b(inj|injection|iv|im)\b", low):
        return "injection"
    if re.search(r"\b(drop|drops)\b", low):
        return "drop"
    return None


def _pick_row(rows: list[M.MedicineFts], line: str) -> M.MedicineFts:
    """Choose among same-named products by the form the line asks for.

    "Cap. Seclo 20 mg" must resolve to the capsule, not the injection that
    happens to sort first; without this the strength and price shown are wrong.
    """
    hint = _form_hint(line)
    if hint:
        for r in rows:
            if hint in (r.form or "").lower():
                return r
    return rows[0]


def _match_brand(by_name: dict[str, list[M.MedicineFts]], cleaned: str, line: str = "") -> tuple[M.MedicineFts, float] | None:
    """Strict, anchored brand match.

    Deliberately NOT a free-form fuzzy scan: ``fuzz.WRatio`` partial-matches, so
    "A. Rahman" scored 90 against the brand "AH" and "Demo" scored 90 against
    "Demovo". Every rule below is anchored to a whole token or a word boundary,
    and the only fuzzy step compares the line's FIRST TOKEN against a brand of
    comparable length — which is what lets "seclo" reach "Seclo" and "celofn"
    reach "Celofen" without dragging in unrelated names.
    """
    nq = normalize(cleaned)
    if not nq:
        return None

    # 1. the whole cleaned line is exactly a brand ("napa")
    if nq in by_name:
        return _pick_row(by_name[nq], line), 1.0

    # 2. the line's first token is exactly a brand ("napa extra" -> Napa)
    first = nq.split(" ", 1)[0]
    if len(first) >= 3 and first in by_name:
        return _pick_row(by_name[first], line), 0.99

    # 2b. a brand whose FIRST TOKEN is the query token ("seclo" -> "Seclo EC
    #     Capsule"). This must run BEFORE the fuzzy step: without it, "seclo"
    #     fuzzy-matched the unrelated one-character-longer brand "Steclo" at
    #     0.909 and the real Seclo was never reached. ALL products sharing the
    #     token are pooled and then narrowed by the requested form — picking the
    #     shortest *name* alone would have chosen "Seclo Injection" over the
    #     capsule the line actually asked for.
    if len(first) >= 3:
        pooled: list[M.MedicineFts] = []
        for name, rows in by_name.items():
            if name.startswith(first + " "):
                pooled.extend(rows)
        if pooled:
            return _pick_row(pooled, line), 0.98

    # 3. a brand is a prefix of the line at a word boundary ("napa 500" -> Napa)
    best: tuple[str, list[M.MedicineFts]] | None = None
    for name, rows in by_name.items():
        if len(name) < 4:
            continue
        if nq.startswith(name + " "):
            if best is None or len(name) > len(best[0]):
                best = (name, rows)
    if best:
        return _pick_row(best[1], line), 0.97

    # 4. typo tolerance on the first token only, whole-string ratio, tight floor.
    if len(first) >= 4:
        cand = process.extractOne(first, list(by_name.keys()), scorer=fuzz.ratio, score_cutoff=85)
        if cand:
            name, score, _ = cand
            return _pick_row(by_name[name], line), round(score / 100.0, 3)
    return None


def _match_test(by_name: dict[str, M.LabTest], line: str) -> tuple[M.LabTest, float] | None:
    """Strict, anchored test match (same reasoning as ``_match_brand``)."""
    nq = normalize(line)
    if not nq:
        return None
    if nq in by_name:
        return by_name[nq], 1.0

    best: tuple[str, M.LabTest] | None = None
    for name, t in by_name.items():
        if len(name) < 4:
            continue
        # the line starts with the test name ("cbc test fasting" -> CBC Test)
        if nq.startswith(name + " "):
            if best is None or len(name) > len(best[0]):
                best = (name, t)
        # the line IS a prefix of the test name ("cbc" -> CBC Test)
        elif len(nq) >= 3 and name.startswith(nq + " "):
            if best is None or len(name) < len(best[0]):
                best = (name, t)
    if best:
        return best[1], 0.97

    # every query token appears in the test name ("blood sugar fasting" ->
    # "Fasting Blood Sugar (FBS) / Fasting Plasma Glucose (FPG)"). Requires at
    # least two tokens so a single common word cannot claim a test.
    qtokens = nq.split()
    if len(qtokens) >= 2:
        subset = [
            (name, t) for name, t in by_name.items()
            if all(tok in name.split() for tok in qtokens)
        ]
        if subset:
            name, t = min(subset, key=lambda kv: len(kv[0]))
            return t, 0.95

    if len(nq) >= 4:
        cand = process.extractOne(nq, list(by_name.keys()), scorer=fuzz.ratio, score_cutoff=88)
        if cand:
            name, score, _ = cand
            # Reject a fuzzy hit whose length is wildly different: a short query
            # must not be absorbed by a long unrelated test name.
            if abs(len(name) - len(nq)) <= max(6, len(nq)):
                return by_name[name], round(score / 100.0, 3)
    return None


def extract_from_text(db: Session, text: str) -> dict[str, Any]:
    """Turn OCR text into matched medicines and tests.

    Returns ``{"medicines": [...], "tests": [...], "lines": [...]}``. Each
    medicine carries the catalog row it matched plus the dose/duration read off
    the same line, so the UI can pre-fill the manual-entry form.
    """
    brand_by_name = _brand_index(db)
    test_by_name = _test_index(db)

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    medicines: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    seen_brands: set[int] = set()
    seen_tests: set[int] = set()

    for line in raw_lines:
        if len(line) < MIN_LINE or len(line) > MAX_LINE:
            continue
        if re.match(r"^[\d\W]+$", line):
            continue
        # Section headers and patient/doctor metadata are never drug entries.
        if _HEADER_RE.search(line):
            continue

        # --- tests first: a printed test name is a stronger, less ambiguous hit
        tmatch = _match_test(test_by_name, line)
        if tmatch:
            t, score = tmatch
            if t.id not in seen_tests:
                seen_tests.add(t.id)
                tests.append({
                    "raw": line, "test_id": t.id, "name": t.name,
                    "price_min": float(t.price_min) if t.price_min is not None else None,
                    "price_max": float(t.price_max) if t.price_max is not None else None,
                    "score": score,
                })
            continue

        # --- medicines: clean the line, then match the remainder
        cleaned = _clean_line(line)
        if len(cleaned) < MIN_LINE:
            continue
        bmatch = _match_brand(brand_by_name, cleaned, line)
        if not bmatch:
            continue
        r, score = bmatch
        if r.brand_id in seen_brands:
            continue
        seen_brands.add(r.brand_id)
        medicines.append({
            "raw": line,
            "brand_id": r.brand_id,
            "brand": r.brand,
            "generic": r.generic,
            "company": r.company,
            "strength": r.strength,
            "form": r.form,
            "score": score,
            "dose": _dose_from_line(line),
            "duration": _duration_from_line(line),
        })

    return {"medicines": medicines, "tests": tests, "lines": raw_lines}


# ------------------------------------------------------------- compat wrappers
def parse_ocr_text(db: Session, text: str) -> dict[str, Any]:
    """Backwards-compatible shape used by older callers/tests."""
    ex = extract_from_text(db, text)
    candidates = [
        {
            "raw": m["raw"],
            "matches": [{
                "brand_id": m["brand_id"], "brand": m["brand"], "generic": m["generic"],
                "company": m["company"], "strength": m["strength"], "form": m["form"],
                "score": m["score"],
            }],
            "dose": m["dose"],
            "duration": m["duration"],
        }
        for m in ex["medicines"]
    ]
    return {
        "mode": "ocr",
        "candidates": candidates,
        "medicines": ex["medicines"],
        "tests": ex["tests"],
        "line_count": len(ex["lines"]),
    }


def run_ocr(data: bytes, db: Session) -> tuple[str | None, dict[str, Any]]:
    """Returns ``(ocr_text, parsed)``.

    When no provider is available the parsed payload is the typed/manual
    fallback, which the UI turns into the manual-entry form.
    """
    text, provider = ocr_text(data)
    if not text:
        return None, {
            "mode": "typed_fallback",
            "provider": "none",
            "message": (
                "We could not read this image automatically. Type the medicines and "
                "tests below and we will price them for you."
            ),
            "candidates": [], "medicines": [], "tests": [],
        }
    parsed = parse_ocr_text(db, text)
    parsed["provider"] = provider
    if not parsed["medicines"] and not parsed["tests"]:
        parsed["mode"] = "ocr_no_match"
        parsed["message"] = (
            "We read the image but could not match any medicine or test. "
            "Type them below and we will price them for you."
        )
    return text, parsed
