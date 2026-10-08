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

# Process-lifetime caches for the read-only catalog indexes. Building them per
# request loaded 25k ORM rows and pushed the free-tier container into an OOM
# restart; the catalog never changes at runtime, so caching is safe.
_BRAND_INDEX_CACHE: dict[str, list[tuple]] | None = None
_TEST_INDEX_CACHE: dict[str, tuple] | None = None

# Hard ceiling on the long side of an image handed to Tesseract. Its memory use
# scales with the pixel count, and Render's free instance has 512 MB total.
#
# NOTE: pytesseract runs the `tesseract` BINARY as a subprocess, so its memory is
# NOT part of this process's RSS — a 1500px image could push the subprocess past
# the container limit even though Python itself looked small. 1200px keeps the
# subprocess comfortably inside the free tier while still giving ~30px of glyph
# height, which is what the engine needs.
MAX_OCR_PIXELS = 1200

# How many preprocessing variants may be OCR'd. Each one is a `tesseract`
# subprocess, and the subprocess footprint is what the 512 MB container limit
# constrains, so this is a hard cap rather than "try everything".
MAX_OCR_PASSES = 2

# Tesseract is multi-threaded by default and each worker thread allocates its own
# scratch buffers. One thread is plenty for a single page and roughly halves the
# subprocess footprint.
import os as _os
_os.environ.setdefault("OMP_THREAD_LIMIT", "1")

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
def preprocess_variants(data: bytes):
    """Yield OCR-ready renderings of the photo, one at a time.

    A **generator**, not a list: each variant is a full-size grayscale image, and
    holding all of them at once (plus Tesseract's own working set) is what pushed
    Render's 512 MB free instance into an OOM kill — the container died mid-upload
    and every request 502'd until it restarted. Yielding lets the caller drop each
    image before the next is built.

    Only TWO variants are produced, and the caller stops at the first that yields
    text. Each variant costs a `tesseract` subprocess spawn, and the subprocess —
    not this process — is what the container limit actually constrains, so the
    number of passes matters as much as the image size.
    """
    from PIL import Image, ImageFilter, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    g = img.convert("L")
    img.close()

    w, h = g.size
    # Upscale small photos (Tesseract wants ~30px of glyph height) but never
    # beyond the cap, and always downscale an oversized one.
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    elif max(w, h) > MAX_OCR_PIXELS:
        scale = MAX_OCR_PIXELS / max(w, h)
        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    # 1. Autocontrast: fixes the over-exposed white-page case, which is the
    #    common phone-photo failure. This alone reads most prescriptions.
    ac = ImageOps.autocontrast(g, cutoff=1)
    g.close()
    yield "autocontrast", ac

    # 2. Sharpened: the fallback for faint print. `filter` returns a NEW image,
    #    so `ac` is released as soon as this one exists.
    sharp = ac.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))
    yield "sharpened", sharp
    ac.close()
    sharp.close()


# ------------------------------------------------------------------------ OCR
def _tesseract_text(img: Any) -> str | None:
    try:
        import pytesseract  # type: ignore

        # A single pass. psm 6 = "assume a single uniform block of text", which is
        # what a prescription body is. Running psm 4 as well doubled the number of
        # `tesseract` subprocess spawns, and the subprocess is what the container
        # memory limit constrains — one pass is the difference between a 200 and a
        # 502 on the free tier.
        try:
            txt = pytesseract.image_to_string(img, lang="eng", config="--oem 3 --psm 6")
        except Exception:
            return None
        return txt or None
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


def ocr_text(data: bytes, score=None) -> tuple[str | None, str]:
    """Return ``(text, provider)``. ``provider`` is ``"none"`` when nothing ran.

    ``null``/empty/``auto`` all mean "use whatever is available": Gemini when a
    key is configured, otherwise the bundled Tesseract engine. Only an explicit
    ``off``/``disabled`` turns reading off — the old behaviour, where the shipped
    ``OCR_PROVIDER=null`` silently disabled reading for every upload, is exactly
    the bug this feature exists to fix.

    ``score`` is an optional ``callable(text) -> int`` used to pick between
    preprocessing variants. Stopping at the first variant that returns *any* text
    is too eager — a sharpened pass can return a few stray characters and win over
    the autocontrast pass that actually read the drug names. The caller passes a
    scorer (how many catalog entries the text matches) so the best variant wins,
    while still capping the number of `tesseract` subprocess spawns.
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
        # At most MAX_OCR_PASSES variants, each one `tesseract` subprocess. The
        # generator owns each image and releases it before building the next, so
        # the caller must NOT close them.
        best: str | None = None
        best_score = -1
        for i, (_label, img) in enumerate(preprocess_variants(data)):
            if i >= MAX_OCR_PASSES:
                break
            txt = _tesseract_text(img)
            if not txt or not txt.strip():
                continue
            s = score(txt) if score else len(txt.strip())
            if s > best_score:
                best, best_score = txt, s
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


def _brand_index(db: Session) -> dict[str, list[tuple]]:
    """Normalised brand name -> the catalog rows carrying it.

    A brand name is not unique (the same name is sold by several companies), so
    the value is a list; the first row is used for display and the rest are
    available if a caller wants to disambiguate.
    """
    # Read only the columns the matcher needs, as plain tuples. Loading 25k
    # ORM instances per request is what pushed the free-tier container into an
    # OOM restart (the 502s); a tuple index is a fraction of the memory and is
    # cached for the process lifetime, since the catalog is read-only.
    global _BRAND_INDEX_CACHE
    if _BRAND_INDEX_CACHE is not None:
        return _BRAND_INDEX_CACHE
    rows = db.execute(
        select(M.MedicineFts.brand_id, M.MedicineFts.brand, M.MedicineFts.brand_n,
               M.MedicineFts.generic, M.MedicineFts.company, M.MedicineFts.strength,
               M.MedicineFts.form)
    ).all()
    by_name: dict[str, list[tuple]] = {}
    for r in rows:
        n = r[2] or normalize(r[1])
        if n:
            by_name.setdefault(n, []).append(r)
    _BRAND_INDEX_CACHE = by_name
    return by_name


def _test_index(db: Session) -> dict[str, tuple]:
    """Normalised test name (and each alias) -> the test row (as a tuple)."""
    global _TEST_INDEX_CACHE
    if _TEST_INDEX_CACHE is not None:
        return _TEST_INDEX_CACHE
    rows = db.execute(
        select(M.LabTest.id, M.LabTest.name, M.LabTest.aliases,
               M.LabTest.price_min, M.LabTest.price_max)
    ).all()
    by_name: dict[str, tuple] = {}
    for t in rows:
        for cand in [t[1], *(t[2] or "").split(",")]:
            n = normalize(cand)
            if n:
                by_name.setdefault(n, t)
    _TEST_INDEX_CACHE = by_name
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


def _pick_row(rows: list[tuple], line: str) -> tuple:
    """Choose among same-named products by the form the line asks for.

    "Cap. Seclo 20 mg" must resolve to the capsule, not the injection that
    happens to sort first; without this the strength and price shown are wrong.
    """
    hint = _form_hint(line)
    if hint:
        for r in rows:
            if hint in (r[6] or "").lower():
                return r
    return rows[0]


def _match_brand(by_name: dict[str, list[tuple]], cleaned: str, line: str = "") -> tuple[tuple, float] | None:
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
        pooled: list[tuple] = []
        for name, rows in by_name.items():
            if name.startswith(first + " "):
                pooled.extend(rows)
        if pooled:
            return _pick_row(pooled, line), 0.98

    # 3. a brand is a prefix of the line at a word boundary ("napa 500" -> Napa)
    best: tuple[str, list[tuple]] | None = None
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


def _match_test(by_name: dict[str, tuple], line: str) -> tuple[tuple, float] | None:
    """Strict, anchored test match (same reasoning as ``_match_brand``)."""
    nq = normalize(line)
    if not nq:
        return None
    if nq in by_name:
        return by_name[nq], 1.0

    best: tuple[str, tuple] | None = None
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
            if t[0] not in seen_tests:
                seen_tests.add(t[0])
                tests.append({
                    "raw": line, "test_id": t[0], "name": t[1],
                    "price_min": float(t[3]) if t[3] is not None else None,
                    "price_max": float(t[4]) if t[4] is not None else None,
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
        if r[0] in seen_brands:
            continue
        seen_brands.add(r[0])
        medicines.append({
            "raw": line,
            "brand_id": r[0],
            "brand": r[1],
            "generic": r[3],
            "company": r[4],
            "strength": r[5],
            "form": r[6],
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


def _match_count(db: Session, text: str) -> int:
    """How many catalog entries this OCR text matches — the variant scorer.

    Cheap enough to run per variant (it reuses the cached indexes) and a far
    better signal than raw text length: a pass that reads three drug names beats
    one that reads forty characters of page furniture.
    """
    try:
        ex = extract_from_text(db, text)
        return len(ex["medicines"]) * 2 + len(ex["tests"])
    except Exception:
        return 0


def run_ocr(data: bytes, db: Session) -> tuple[str | None, dict[str, Any]]:
    """Returns ``(ocr_text, parsed)``.

    When no provider is available the parsed payload is the typed/manual
    fallback, which the UI turns into the manual-entry form.
    """
    text, provider = ocr_text(data, score=lambda t: _match_count(db, t))
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
