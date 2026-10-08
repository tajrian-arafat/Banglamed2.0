"""Data ingestion pipeline: raw files -> validate -> clean -> normalize -> dedupe -> load -> report.

Idempotent (upsert by natural key). Every run creates an import_batch and stamps
provenance (source_name, source_url, collected_at, batch_id, data_status) on rows.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M

# ------------------------------------------------------------------ helpers
SECTION_MAP = {
    "indications": "indications",
    "pharmacology": "pharmacology",
    "dosage_administration": "dosage",
    "interaction": "interaction",
    "contraindications": "contraindications",
    "side_effects": "side_effects",
    "pregnancy_lactation": "pregnancy_lactation",
    "precautions_warnings": "precautions",
    "overdose_effects": "overdose",
    "storage_conditions": "storage",
}

DIVISIONS = ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Barishal", "Sylhet", "Rangpur", "Mymensingh"]

DISTRICTS = [
    "Bagerhat", "Bandarban", "Barguna", "Barishal", "Bhola", "Bogura", "Brahmanbaria", "Chandpur",
    "Chapainawabganj", "Chattogram", "Chuadanga", "Cox's Bazar", "Cumilla", "Dhaka", "Dinajpur",
    "Faridpur", "Feni", "Gaibandha", "Gazipur", "Gopalganj", "Habiganj", "Jamalpur", "Jashore",
    "Jhalokati", "Jhenaidah", "Joypurhat", "Khagrachhari", "Khulna", "Kishoreganj", "Kurigram",
    "Kushtia", "Lakshmipur", "Lalmonirhat", "Madaripur", "Magura", "Manikganj", "Meherpur",
    "Moulvibazar", "Munshiganj", "Mymensingh", "Naogaon", "Narail", "Narayanganj", "Narsingdi",
    "Natore", "Nawabganj", "Netrokona", "Nilphamari", "Noakhali", "Pabna", "Panchagarh",
    "Patuakhali", "Pirojpur", "Rajbari", "Rajshahi", "Rangamati", "Rangpur", "Satkhira",
    "Shariatpur", "Sherpur", "Sirajganj", "Sunamganj", "Sylhet", "Tangail", "Thakurgaon",
]

DISTRICT_TO_DIVISION = {
    "Bagerhat": "Khulna", "Bandarban": "Chattogram", "Barguna": "Barishal", "Barishal": "Barishal",
    "Bhola": "Barishal", "Bogura": "Rajshahi", "Brahmanbaria": "Chattogram", "Chandpur": "Chattogram",
    "Chapainawabganj": "Rajshahi", "Chattogram": "Chattogram", "Chuadanga": "Khulna",
    "Cox's Bazar": "Chattogram", "Cumilla": "Chattogram", "Dhaka": "Dhaka", "Dinajpur": "Rangpur",
    "Faridpur": "Dhaka", "Feni": "Chattogram", "Gaibandha": "Rangpur", "Gazipur": "Dhaka",
    "Gopalganj": "Dhaka", "Habiganj": "Sylhet", "Jamalpur": "Mymensingh", "Jashore": "Khulna",
    "Jhalokati": "Barishal", "Jhenaidah": "Khulna", "Joypurhat": "Rajshahi", "Khagrachhari": "Chattogram",
    "Khulna": "Khulna", "Kishoreganj": "Dhaka", "Kurigram": "Rangpur", "Kushtia": "Khulna",
    "Lakshmipur": "Chattogram", "Lalmonirhat": "Rangpur", "Madaripur": "Dhaka", "Magura": "Khulna",
    "Manikganj": "Dhaka", "Meherpur": "Khulna", "Moulvibazar": "Sylhet", "Munshiganj": "Dhaka",
    "Mymensingh": "Mymensingh", "Naogaon": "Rajshahi", "Narail": "Khulna", "Narayanganj": "Dhaka",
    "Narsingdi": "Dhaka", "Natore": "Rajshahi", "Nawabganj": "Rajshahi", "Netrokona": "Mymensingh",
    "Nilphamari": "Rangpur", "Noakhali": "Chattogram", "Pabna": "Rajshahi", "Panchagarh": "Rangpur",
    "Patuakhali": "Barishal", "Pirojpur": "Barishal", "Rajbari": "Dhaka", "Rajshahi": "Rajshahi",
    "Rangamati": "Chattogram", "Rangpur": "Rangpur", "Satkhira": "Khulna", "Shariatpur": "Dhaka",
    "Sherpur": "Mymensingh", "Sirajganj": "Rajshahi", "Sunamganj": "Sylhet", "Sylhet": "Sylhet",
    "Tangail": "Dhaka", "Thakurgaon": "Rangpur",
}

CITY_ALIASES = {
    "dhaka": "Dhaka", "dhanmondi": "Dhaka", "mirpur": "Dhaka", "uttara": "Dhaka", "mohammadpur": "Dhaka",
    "chittagong": "Chattogram", "chattogram": "Chattogram", "cumilla": "Cumilla", "comilla": "Cumilla",
    "sylhet": "Sylhet", "khulna": "Khulna", "rajshahi": "Rajshahi", "rangpur": "Rangpur",
    "barishal": "Barishal", "mymensingh": "Mymensingh", "bogura": "Bogura", "bogra": "Bogura",
    "coxs bazar": "Cox's Bazar", "cox's bazar": "Cox's Bazar", "narayanganj": "Narayanganj",
    "gazipur": "Gazipur", "jashore": "Jashore", "jessore": "Jashore", "noakhali": "Noakhali",
    "pabna": "Pabna", "dinajpur": "Dinajpur", "faridpur": "Faridpur", "tangail": "Tangail",
    "kishoreganj": "Kishoreganj", "feni": "Feni", "jamalpur": "Jamalpur", "kushtia": "Kushtia",
    "satkhira": "Satkhira", "bagerhat": "Bagerhat", "narsingdi": "Narsingdi", "manikganj": "Manikganj",
    "munshiganj": "Munshiganj", "madaripur": "Madaripur", "gopalganj": "Gopalganj", "shariatpur": "Shariatpur",
    "rajbari": "Rajbari", "pirojpur": "Pirojpur", "bhola": "Bhola", "patuakhali": "Patuakhali",
    "barguna": "Barguna", "jhalokati": "Jhalokati", "chuadanga": "Chuadanga", "jhenaidah": "Jhenaidah",
    "magura": "Magura", "narail": "Narail", "meherpur": "Meherpur", "habiganj": "Habiganj",
    "moulvibazar": "Moulvibazar", "sunamganj": "Sunamganj", "netrokona": "Netrokona", "sherpur": "Sherpur",
    "naogaon": "Naogaon", "natore": "Natore", "chapainawabganj": "Chapainawabganj", "joypurhat": "Joypurhat",
    "sirajganj": "Sirajganj", "kurigram": "Kurigram", "lalmonirhat": "Lalmonirhat", "nilphamari": "Nilphamari",
    "panchagarh": "Panchagarh", "thakurgaon": "Thakurgaon", "gaibandha": "Gaibandha", "rangamati": "Rangamati",
    "bandarban": "Bandarban", "khagrachhari": "Khagrachhari", "brahmanbaria": "Brahmanbaria",
    "chandpur": "Chandpur", "lakshmipur": "Lakshmipur",
}


def _now() -> datetime:
    """Timestamp for imported rows.

    Honours the deterministic build clock (models.stamp): on hosts without a
    persistent disk the catalog is rebuilt on every deploy, and if ``collected_at``
    / ``finished_at`` carried the wall clock the rebuilt state would differ on
    every boot. With BANGLAMED_BUILD_EPOCH set they resolve to one fixed instant,
    so two independent rebuilds produce identical rows and the state fingerprint
    is stable.
    """
    from ..models import stamp

    return stamp()


def clean_text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return None
    s = html.unescape(s)  # decode &amp; &lt; &#39; etc. from scraped HTML
    s = re.sub(r"\s+", " ", s)
    return s


def clean_multiline(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    return html.unescape(s)


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("৳", "").replace("BDT", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def to_int(v: Any) -> int | None:
    f = to_float(v)
    return int(f) if f is not None else None


def parse_pack(pack_size: str | None, form: str | None) -> tuple[int | None, dict[str, Any]]:
    """Parse '5 x 10' -> pieces_per_strip=10, {'strips':5,'pieces_per_strip':10}."""
    info: dict[str, Any] = {}
    if not pack_size:
        return None, info
    s = str(pack_size).strip().lower()
    m = re.match(r"^(\d+)\s*[x×]\s*(\d+)$", s)
    if m:
        strips, pcs = int(m.group(1)), int(m.group(2))
        info = {"strips": strips, "pieces_per_strip": pcs, "kind": "strip"}
        return pcs, info
    m2 = re.search(r"(\d+(\.\d+)?)\s*(ml|gm|g|mg|mcg|iu|%)", s)
    if m2:
        info = {"container_size": m2.group(1), "unit": m2.group(3), "kind": "container"}
        return None, info
    return None, info


def parse_pregnancy_category(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"category\s*([A-DX])", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def completeness_score(brand: M.Brand) -> float:
    fields = [
        brand.name, brand.generic_id, brand.company_id, brand.form_name, brand.strength_text,
        brand.unit_price, brand.strip_price, brand.indications, brand.dosage_administration,
        brand.side_effects, brand.precautions_warnings, brand.storage_conditions,
    ]
    present = sum(1 for f in fields if f not in (None, "", 0))
    return round(present / len(fields), 3)


def _batch(db: Session, entity: str, source_name: str, source_url: str | None = None) -> M.ImportBatch:
    b = M.ImportBatch(entity=entity, source_name=source_name, source_url=source_url, status="running")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _finish(db: Session, b: M.ImportBatch, rows_in: int, loaded: int, skipped: int, report: dict) -> None:
    b.rows_in = rows_in
    b.rows_loaded = loaded
    b.rows_skipped = skipped
    b.finished_at = _now()
    b.status = "completed"
    b.report_json = json.dumps(report, ensure_ascii=False)
    db.commit()


# ------------------------------------------------------------------ loaders
def load_geo(db: Session) -> dict:
    div_ids: dict[str, int] = {}
    for name in DIVISIONS:
        row = db.scalar(select(M.GeoDivision).where(M.GeoDivision.name == name))
        if not row:
            row = M.GeoDivision(name=name)
            db.add(row)
            db.commit()
            db.refresh(row)
        div_ids[name] = row.id
    dist_ids: dict[str, int] = {}
    for name in DISTRICTS:
        row = db.scalar(select(M.GeoDistrict).where(M.GeoDistrict.name == name))
        if not row:
            row = M.GeoDistrict(name=name, division_id=div_ids[DISTRICT_TO_DIVISION[name]])
            db.add(row)
            db.commit()
            db.refresh(row)
        dist_ids[name] = row.id
    return {"divisions": div_ids, "districts": dist_ids}


def load_companies(db: Session, path: Path, source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "companies", source_name)
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    loaded = skipped = 0
    for r in rows[1:]:
        name = clean_text(r[idx.get("company_name", 1)])
        if not name:
            skipped += 1
            continue
        row = db.scalar(select(M.Company).where(M.Company.name == name))
        if not row:
            row = M.Company(name=name)
            db.add(row)
        row.med_code = clean_text(r[idx.get("company_id", 0)])
        row.established = clean_text(r[idx.get("established", 2)])
        row.market_share = clean_text(r[idx.get("market_share", 3)])
        row.growth = clean_text(r[idx.get("growth", 4)])
        row.total_generics = to_int(r[idx.get("total_generics", 5)])
        row.headquarter = clean_text(r[idx.get("headquarter", 6)])
        row.contact_details = clean_text(r[idx.get("contact_details", 7)])
        row.source_name = source_name
        row.source_url = clean_text(r[idx.get("url", 10)])
        row.collected_at = _now()
        row.batch_id = b.id
        row.data_status = "unverified"
        loaded += 1
    db.commit()
    _finish(db, b, len(rows) - 1, loaded, skipped, {"entity": "companies"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_drug_classes(db: Session, path: Path, source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "drug_classes", source_name)
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    loaded = skipped = 0
    for r in rows[1:]:
        name = clean_text(r[idx.get("drug_class_name", 1)])
        if not name:
            skipped += 1
            continue
        row = db.scalar(select(M.DrugClass).where(M.DrugClass.name == name))
        if not row:
            row = M.DrugClass(name=name)
            db.add(row)
        row.med_code = clean_text(r[idx.get("drug_class_id", 0)])
        row.subclasses_json = clean_multiline(r[idx.get("subclasses", 2)]) or "[]"
        row.source_name = source_name
        row.source_url = clean_text(r[idx.get("url", 3)])
        row.collected_at = _now()
        row.batch_id = b.id
        loaded += 1
    db.commit()
    _finish(db, b, len(rows) - 1, loaded, skipped, {"entity": "drug_classes"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_dosage_forms(db: Session, path: Path, source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "dosage_forms", source_name)
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    loaded = skipped = 0
    for r in rows[1:]:
        raw = clean_text(r[idx.get("dosage_form_name", 1)])
        if not raw:
            skipped += 1
            continue
        name = re.sub(r"\s*available brand names?\s*$", "", raw, flags=re.IGNORECASE).strip()
        row = db.scalar(select(M.DosageForm).where(M.DosageForm.name == name))
        if not row:
            row = M.DosageForm(name=name)
            db.add(row)
        row.med_code = clean_text(r[idx.get("dosage_form_id", 0)])
        row.source_name = source_name
        row.source_url = clean_text(r[idx.get("url", 2)])
        row.collected_at = _now()
        row.batch_id = b.id
        loaded += 1
    db.commit()
    _finish(db, b, len(rows) - 1, loaded, skipped, {"entity": "dosage_forms"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_generics(db: Session, path: Path, source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "generics", source_name)
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    loaded = skipped = 0
    for r in rows[1:]:
        name = clean_text(r[idx.get("generic_name", 1)])
        if not name:
            skipped += 1
            continue
        row = db.scalar(select(M.Generic).where(M.Generic.name == name))
        if not row:
            row = M.Generic(name=name)
            db.add(row)
            db.commit()
            db.refresh(row)
        row.med_code = clean_text(r[idx.get("generic_id", 0)])
        row.therapeutic_class = clean_text(r[idx.get("therapeutic_class", 11)])
        preg_text = clean_multiline(r[idx.get("pregnancy_lactation", 8)])
        row.pregnancy_text = preg_text
        row.pregnancy_category = parse_pregnancy_category(preg_text)
        row.source_name = source_name
        row.source_url = clean_text(r[idx.get("url", 13)])
        row.collected_at = _now()
        row.batch_id = b.id
        # content sections
        for col, section in SECTION_MAP.items():
            if col not in idx:
                continue
            text = clean_multiline(r[idx[col]])
            if not text:
                continue
            existing = db.scalar(
                select(M.GenericContent).where(
                    M.GenericContent.generic_id == row.id,
                    M.GenericContent.lang == "en",
                    M.GenericContent.section == section,
                )
            )
            if existing:
                existing.text = text
            else:
                db.add(M.GenericContent(generic_id=row.id, lang="en", section=section, text=text))
        loaded += 1
    db.commit()
    _finish(db, b, len(rows) - 1, loaded, skipped, {"entity": "generics"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_indications(db: Session, path: Path, source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "indications", source_name)
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(hdr)}
    loaded = skipped = 0
    for r in rows[1:]:
        name = clean_text(r[idx.get("indication_name", 1)])
        if not name:
            skipped += 1
            continue
        row = db.scalar(select(M.Indication).where(M.Indication.name == name))
        if not row:
            row = M.Indication(name=name)
            db.add(row)
        row.med_code = clean_text(r[idx.get("indication_id", 0)])
        row.generics_json = clean_multiline(r[idx.get("generics_indicated", 2)]) or "[]"
        row.source_name = source_name
        row.source_url = clean_text(r[idx.get("url", 3)])
        row.collected_at = _now()
        row.batch_id = b.id
        loaded += 1
    db.commit()
    _finish(db, b, len(rows) - 1, loaded, skipped, {"entity": "indications"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_brands(db: Session, paths: list[Path], source_name: str) -> dict:
    import openpyxl

    b = _batch(db, "brands", source_name)
    # caches
    gen_cache = {g.name: g.id for g in db.scalars(select(M.Generic)).all()}
    comp_cache = {c.name: c.id for c in db.scalars(select(M.Company)).all()}
    form_cache = {f.name: f.id for f in db.scalars(select(M.DosageForm)).all()}
    loaded = skipped = 0
    total_in = 0
    for path in paths:
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        hdr = [str(h) if h else "" for h in rows[0]]
        idx = {h: i for i, h in enumerate(hdr)}
        total_in += len(rows) - 1
        for r in rows[1:]:
            name = clean_text(r[idx.get("brand_name", 1)])
            if not name:
                skipped += 1
                continue
            med_code = clean_text(r[idx.get("brand_id", 0)])
            row = None
            if med_code:
                row = db.scalar(select(M.Brand).where(M.Brand.med_code == med_code))
            if not row:
                row = db.scalar(select(M.Brand).where(M.Brand.name == name, M.Brand.strength_text == clean_text(r[idx.get("strength", 3)])))
            if not row:
                row = M.Brand(name=name)
                db.add(row)
            row.med_code = med_code
            gname = clean_text(r[idx.get("generic_name", 4)])
            row.generic_id = gen_cache.get(gname) if gname else None
            cname = clean_text(r[idx.get("company_name", 7)])
            row.company_id = comp_cache.get(cname) if cname else None
            fname = clean_text(r[idx.get("dosage_form", 2)])
            row.form_name = fname
            row.form_id = form_cache.get(fname) if fname else None
            row.strength_text = clean_text(r[idx.get("strength", 3)])
            m = re.search(r"(\d+(\.\d+)?)", row.strength_text or "")
            row.strength_value = float(m.group(1)) if m else None
            um = re.search(r"[a-zA-Z%]+", (row.strength_text or "").replace("mg", "mg"))
            row.strength_unit = um.group() if um else None
            row.unit_price = to_float(r[idx.get("unit_price_bdt", 10)])
            row.strip_price = to_float(r[idx.get("strip_price_bdt", 11)])
            row.pack_size = clean_text(r[idx.get("pack_size", 12)])
            row.pack_price = to_float(r[idx.get("pack_price_bdt", 13)])
            pcs, pinfo = parse_pack(row.pack_size, fname)
            row.pieces_per_strip = pcs
            row.pack_json = json.dumps(pinfo)
            row.indications = clean_multiline(r[idx.get("indications", 16)])
            row.pharmacology = clean_multiline(r[idx.get("pharmacology", 17)])
            row.dosage_administration = clean_multiline(r[idx.get("dosage_administration", 18)])
            row.interaction = clean_multiline(r[idx.get("interaction", 19)])
            row.contraindications = clean_multiline(r[idx.get("contraindications", 20)])
            row.side_effects = clean_multiline(r[idx.get("side_effects", 21)])
            row.pregnancy_lactation = clean_multiline(r[idx.get("pregnancy_lactation", 22)])
            row.precautions_warnings = clean_multiline(r[idx.get("precautions_warnings", 23)])
            row.overdose_effects = clean_multiline(r[idx.get("overdose_effects", 24)])
            row.therapeutic_class = clean_text(r[idx.get("therapeutic_class", 25)])
            row.storage_conditions = clean_multiline(r[idx.get("storage_conditions", 26)])
            row.source_name = source_name
            row.source_url = clean_text(r[idx.get("url", 28)])
            row.collected_at = _now()
            row.batch_id = b.id
            row.data_status = "unverified"
            row.completeness = completeness_score(row)
            loaded += 1
            if loaded % 2000 == 0:
                db.commit()
    db.commit()
    _finish(db, b, total_in, loaded, skipped, {"entity": "brands", "files": [p.name for p in paths]})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_doctors(db: Session, path: Path, source_name: str) -> dict:
    import csv

    b = _batch(db, "doctors", source_name)
    loaded = skipped = 0
    spec_cache: dict[str, int] = {s.name: s.id for s in db.scalars(select(M.Speciality)).all()}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    for i, r in enumerate(rows):
        name = clean_text(r.get("Name"))
        if not name:
            skipped += 1
            continue
        spec = clean_text(r.get("Specialty"))
        if spec and spec not in spec_cache:
            s = M.Speciality(name=spec)
            db.add(s)
            db.commit()
            db.refresh(s)
            spec_cache[spec] = s.id
        code = f"DOC-BD-{i + 1:06d}"
        row = db.scalar(select(M.Doctor).where(M.Doctor.doctor_code == code))
        if not row:
            row = M.Doctor(doctor_code=code, name=name)
            db.add(row)
        row.name = name
        row.speciality_name = spec
        row.speciality_id = spec_cache.get(spec) if spec else None
        quals = clean_multiline(r.get("Qualifications & Designation"))
        row.qualifications = quals
        row.designation = quals[:300] if quals else None
        row.profile_url = clean_text(r.get("Profile URL"))
        row.source_name = source_name
        row.source_url = clean_text(r.get("Profile URL"))
        row.collected_at = _now()
        row.batch_id = b.id
        row.data_status = "unverified"
        loaded += 1
        if loaded % 500 == 0:
            db.commit()
    db.commit()
    _finish(db, b, len(rows), loaded, skipped, {"entity": "doctors"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def _district_from_address(addr: str | None) -> str | None:
    if not addr:
        return None
    low = addr.lower()
    for alias, dist in CITY_ALIASES.items():
        if alias in low:
            return dist
    return None


def load_hospitals(db: Session, path: Path, source_name: str, geo: dict) -> dict:
    import csv

    b = _batch(db, "hospitals", source_name)
    loaded = skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        name = clean_text(r.get("Hospital / Centre"))
        if not name:
            skipped += 1
            continue
        addr = clean_text(r.get("Address"))
        dist = _district_from_address(addr) or _district_from_address(name)
        row = db.scalar(select(M.Hospital).where(M.Hospital.name == name))
        if not row:
            row = M.Hospital(name=name)
            db.add(row)
        row.address = addr
        row.phone = clean_text(r.get("Phone"))
        row.hours = clean_text(r.get("Hours"))
        row.about = clean_multiline(r.get("About"))
        row.district_name = dist
        row.district_id = geo["districts"].get(dist) if dist else None
        row.division_id = geo["divisions"].get(DISTRICT_TO_DIVISION.get(dist)) if dist else None
        row.source_name = source_name
        row.source_url = clean_text(r.get("URL"))
        row.collected_at = _now()
        row.batch_id = b.id
        row.data_status = "unverified"
        loaded += 1
    db.commit()
    _finish(db, b, len(rows), loaded, skipped, {"entity": "hospitals"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def load_tests(db: Session, path: Path, source_name: str) -> dict:
    b = _batch(db, "tests", source_name)
    data = json.loads(path.read_text(encoding="utf-8"))
    tests = data.get("tests", [])
    loaded = skipped = 0
    for t in tests:
        name = clean_text(t.get("test_name_ld")) or clean_text(t.get("h1"))
        if not name:
            skipped += 1
            continue
        slug = clean_text(t.get("slug"))
        row = db.scalar(select(M.LabTest).where(M.LabTest.slug == slug)) if slug else None
        if not row:
            row = M.LabTest(name=name, slug=slug)
            db.add(row)
            db.commit()
            db.refresh(row)
        row.name = name
        row.price_min = to_float(t.get("low_price"))
        row.price_max = to_float(t.get("high_price"))
        row.source_name = source_name
        row.source_url = clean_text(t.get("url"))
        row.collected_at = _now()
        row.batch_id = b.id
        row.data_status = "unverified"
        # procedure text from sections if present
        sections = t.get("sections") or []
        for sec in sections:
            if isinstance(sec, dict):
                heading = (sec.get("heading") or "").lower()
                body = sec.get("body") or sec.get("text")
                if "how" in heading and body:
                    row.procedure_text = clean_multiline(body)
                    row.procedure_source = "seed"
                if "fast" in heading and body:
                    row.prep_text = clean_multiline(body)
                    row.fasting_required = True
        # offers -> test prices
        for off in t.get("offers", []) or []:
            hn = clean_text(off.get("hospital_name"))
            if not hn:
                continue
            existing = db.scalar(
                select(M.TestPrice).where(M.TestPrice.test_id == row.id, M.TestPrice.hospital_name == hn)
            )
            if not existing:
                existing = M.TestPrice(test_id=row.id, hospital_name=hn)
                db.add(existing)
            existing.location = clean_text(off.get("location"))
            existing.price = to_float(off.get("price"))
            existing.badge = clean_text(off.get("badge"))
        loaded += 1
    db.commit()
    _finish(db, b, len(tests), loaded, skipped, {"entity": "tests"})
    return {"loaded": loaded, "skipped": skipped, "batch_id": b.id}


def build_fts(db: Session) -> dict:
    """Rebuild the medicine_fts search index from brands.

    The normalised columns (``brand_n``, ``generic_n``, ``company_n``,
    ``form_n``, ``strength_n``, ``first_token``, ``brand_root``) are computed
    ONCE here, at import time, using the same ``services/norm`` functions the
    query path uses. That is what removes ~150k regex calls per keystroke from
    the search hot path and lets SQLite serve prefix narrowing from an index.
    """
    from .norm import first_token as _ft
    from .norm import norm as _n

    db.query(M.MedicineFts).delete()
    db.commit()
    brands = db.scalars(select(M.Brand)).all()
    gen_names = {g.id: g.name for g in db.scalars(select(M.Generic)).all()}
    comp_names = {c.id: c.name for c in db.scalars(select(M.Company)).all()}
    n = 0
    for br in brands:
        row = M.MedicineFts(
            brand_id=br.id,
            brand=br.name or "",
            generic=gen_names.get(br.generic_id, "") or "",
            company=comp_names.get(br.company_id, "") or "",
            aliases="",
            name_bn="",
            strength=br.strength_text or "",
            form=br.form_name or "",
        )
        row.brand_n = _n(row.brand)
        row.generic_n = _n(row.generic)
        row.company_n = _n(row.company)
        row.form_n = _n(row.form)
        row.strength_n = _n(row.strength)
        row.first_token = _ft(row.brand)
        row.brand_root = _ft(row.brand)
        db.add(row)
        n += 1
        if n % 3000 == 0:
            db.commit()
    db.commit()
    return {"fts_rows": n}
