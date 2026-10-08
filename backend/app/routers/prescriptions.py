"""M5 prescriptions + version history + tests + print-with-QR + price lookup.

Flow contract (matches the doctor's "Write prescription" tab)
------------------------------------------------------------
1.  The doctor writes on screen. Nothing is persisted by the editor itself —
    the live preview is pure client state, which is why it can update on every
    keystroke without hammering the API.
2.  ``POST /api/prescriptions``      creates the prescription and stores
    **version 1** (status ``draft``).
3.  ``POST /{id}/finalize``          saves/seals. Deliberately does **NOT**
    produce a QR — sealing and printing are separate acts, and the QR only
    exists once someone prints.
4.  ``PUT /{id}``                    re-saves after an edit. This **appends a new
    version row** and never rewrites the previous one, so the earlier revision
    stays readable (``GET /{id}/versions``).
5.  ``GET /{id}/print``              returns the printable document **with** the
    QR. Scanning it opens ``/rx/{token}`` — a public, unauthenticated lookup of
    the prescribed medicines and tests with prices.

Every state-changing call is authorised against the issuing doctor and audited.
"""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from html import escape

import qrcode
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.db import get_db
from ..core.errors import bad_request, forbidden, not_found
from ..core.security import sign_content, verify_signature
from ..deps import get_current_user, require_role
from ..schemas import PrescriptionIn, SafetyCheckIn
from ..services.dosage import format_dosage
from ..services.ids import public_token, rx_code
from ..services.safety import check_prescription, interactions_for, side_effects_for

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


def _doctor_for_user(db: Session, user: M.User) -> M.Doctor | None:
    return db.scalar(select(M.Doctor).where(M.Doctor.user_id == user.id))


def _resolve_items(db: Session, items) -> list[dict]:
    out = []
    for it in items:
        brand = db.get(M.Brand, it.brand_id) if it.brand_id else None
        gid = it.generic_id or (brand.generic_id if brand else None)
        out.append({
            "brand_id": it.brand_id,
            "generic_id": gid,
            "form": it.form or (brand.form_name if brand else None),
            "strength": it.strength or (brand.strength_text if brand else None),
            "name": it.free_text_name or (brand.name if brand else None),
            "duration_days": (it.dose.duration.get("value") if it.dose and it.dose.duration else None),
        })
    return out


def _can_view(db: Session, rx: M.Prescription, user: M.User) -> bool:
    if user.role == "system_admin":
        return True
    patient = db.get(M.Patient, rx.patient_id)
    if patient and patient.account_id == user.id:
        return True
    doctor = _doctor_for_user(db, user)
    return bool(doctor and doctor.id == rx.doctor_id)


def _can_edit(db: Session, rx: M.Prescription, user: M.User) -> bool:
    if user.role == "system_admin":
        return True
    doctor = _doctor_for_user(db, user)
    return bool(doctor and doctor.id == rx.doctor_id)


# --------------------------------------------------------------------- safety
@router.post("/safety-check")
def safety_check(payload: SafetyCheckIn, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    patient = db.get(M.Patient, payload.patient_id)
    if not patient:
        raise not_found("Patient not found")
    items = _resolve_items(db, payload.items)
    warnings = check_prescription(db, patient, items)
    # The panel needs the detail as well as the verdict: the guards say whether
    # anything is wrong, the two lists below say what each medicine's side effects
    # are and which pairs interact. All read from the existing catalogue.
    return {
        "warnings": warnings,
        "count": len(warnings),
        "side_effects": side_effects_for(db, items),
        "interactions": interactions_for(db, items),
    }


# ---------------------------------------------------------------- persistence
def _write_items(db: Session, rx: M.Prescription, payload: PrescriptionIn) -> None:
    """Replace the prescription's items/tests from the payload.

    Only the child rows are replaced; the prior state is preserved by the
    ``prescription_versions`` snapshot appended on every save, not by the
    children themselves.
    """
    for row in db.scalars(select(M.PrescriptionItem).where(M.PrescriptionItem.rx_id == rx.id)).all():
        db.delete(row)
    for row in db.scalars(select(M.PrescriptionTest).where(M.PrescriptionTest.rx_id == rx.id)).all():
        db.delete(row)
    db.flush()
    for it in payload.items:
        brand = db.get(M.Brand, it.brand_id) if it.brand_id else None
        dose = it.dose.model_dump() if it.dose else {}
        bn = format_dosage(dose) if dose else None
        db.add(M.PrescriptionItem(
            rx_id=rx.id, brand_id=it.brand_id,
            generic_id=it.generic_id or (brand.generic_id if brand else None),
            free_text_name=it.free_text_name,
            form=it.form or (brand.form_name if brand else None),
            strength=it.strength or (brand.strength_text if brand else None),
            dose_json=json.dumps(dose, ensure_ascii=False), bn_dosage_text=bn,
            instructions=it.instructions,
        ))
    for t in payload.tests:
        if t.test_id is None and not t.free_text_name:
            continue  # ignore an empty row rather than storing a blank test
        db.add(M.PrescriptionTest(rx_id=rx.id, test_id=t.test_id,
                                  free_text_name=t.free_text_name, note=t.note))


def _snapshot(db: Session, rx: M.Prescription, user: M.User, reason: str) -> M.PrescriptionVersion:
    """Append a NEW immutable version row. Never mutates an earlier version."""
    payload = _signable_payload(db, rx)
    ch, sig = sign_content(payload)
    last = db.scalar(
        select(M.PrescriptionVersion.version_no)
        .where(M.PrescriptionVersion.rx_id == rx.id)
        .order_by(M.PrescriptionVersion.version_no.desc()).limit(1)
    ) or 0
    ver = M.PrescriptionVersion(
        rx_id=rx.id, version_no=last + 1,
        snapshot_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        content_hash=ch, signature=sig, reason=reason, created_by=user.id,
    )
    db.add(ver)
    rx.content_hash, rx.signature = ch, sig
    return ver


@router.post("")
def create_prescription(payload: PrescriptionIn, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    doctor = _doctor_for_user(db, user)
    if not doctor:
        raise bad_request("No doctor profile linked to this account")
    patient = db.get(M.Patient, payload.patient_id)
    if not patient:
        raise not_found("Patient not found")
    items = _resolve_items(db, payload.items)
    warnings = check_prescription(db, patient, items)
    critical = [w for w in warnings if w["severity"] == "critical"]
    ack_codes = {a.get("code") for a in payload.acknowledgements}
    unacked = [w for w in critical if w["code"] not in ack_codes]
    if unacked:
        raise bad_request("Critical safety warnings must be acknowledged", details=unacked)

    year = datetime.now(timezone.utc).year
    rx = M.Prescription(
        rx_code=rx_code(year), public_token=public_token(), doctor_id=doctor.id,
        hospital_id=payload.hospital_id, patient_id=patient.id,
        appointment_id=payload.appointment_id,
        diagnosis=payload.diagnosis, chief_complaints=payload.chief_complaints,
        notes=payload.notes, advice=payload.advice, status="draft",
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)
    _write_items(db, rx, payload)
    for a in payload.acknowledgements:
        db.add(M.SafetyAcknowledgement(rx_id=rx.id, code=a.get("code", ""),
                                       reason=a.get("reason"), doctor_id=doctor.id))
    db.commit()
    ver = _snapshot(db, rx, user, "initial")
    db.commit()
    log_action(db, user.id, "prescription_create", "prescription", rx.rx_code,
               {"patient": patient.patient_code, "version": ver.version_no})
    return {"id": rx.id, "rx_code": rx.rx_code, "status": rx.status,
            "version": ver.version_no, "warnings": warnings}


@router.put("/{rx_id}")
def update_prescription(rx_id: int, payload: PrescriptionIn, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    """Re-save after an edit. Adds a version; the previous one is left intact."""
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_edit(db, rx, user):
        raise forbidden("Only the issuing doctor can edit this prescription")
    if rx.status == "void":
        raise bad_request("A void prescription cannot be edited")
    items = _resolve_items(db, payload.items)
    patient = db.get(M.Patient, rx.patient_id)
    warnings = check_prescription(db, patient, items) if patient else []
    critical = [w for w in warnings if w["severity"] == "critical"]
    ack_codes = {a.get("code") for a in payload.acknowledgements}
    unacked = [w for w in critical if w["code"] not in ack_codes]
    if unacked:
        raise bad_request("Critical safety warnings must be acknowledged", details=unacked)

    if payload.hospital_id is not None:
        rx.hospital_id = payload.hospital_id
    rx.diagnosis = payload.diagnosis
    rx.chief_complaints = payload.chief_complaints
    rx.notes = payload.notes
    rx.advice = payload.advice
    _write_items(db, rx, payload)
    for a in payload.acknowledgements:
        db.add(M.SafetyAcknowledgement(rx_id=rx.id, code=a.get("code", ""),
                                       reason=a.get("reason"), doctor_id=rx.doctor_id))
    db.commit()
    prior = db.scalar(
        select(func.count()).select_from(M.PrescriptionVersion)
        .where(M.PrescriptionVersion.rx_id == rx.id)
    ) or 0
    ver = _snapshot(db, rx, user, "edit")
    db.commit()
    log_action(db, user.id, "prescription_update", "prescription", rx.rx_code,
               {"version": ver.version_no})
    return {"id": rx.id, "rx_code": rx.rx_code, "status": rx.status,
            "version": ver.version_no, "warnings": warnings,
            "previous_versions_preserved": int(prior)}


@router.post("/{rx_id}/finalize")
def finalize(rx_id: int, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    """Seal and save. NO QR is produced here — the QR is added at print time."""
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_edit(db, rx, user):
        raise forbidden("Only the issuing doctor can finalize")
    payload = _signable_payload(db, rx)
    ch, sig = sign_content(payload)
    rx.content_hash, rx.signature = ch, sig
    rx.status = "finalized"
    db.commit()
    ver = _snapshot(db, rx, user, "finalize")
    db.commit()
    log_action(db, user.id, "prescription_finalize", "prescription", rx.rx_code,
               {"version": ver.version_no})
    return {"rx_code": rx.rx_code, "status": rx.status, "content_hash": ch,
            "signature": sig, "version": ver.version_no, "qr": None,
            "note": "No QR at this step — the QR is generated when the prescription is printed."}


@router.post("/{rx_id}/void")
def void_rx(rx_id: int, body: dict, user: M.User = Depends(require_role("doctor", "system_admin")), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_edit(db, rx, user):
        raise forbidden("Only the issuing doctor can void")
    rx.status = "void"
    rx.void_reason = body.get("reason", "")
    db.commit()
    log_action(db, user.id, "prescription_void", "prescription", rx.rx_code, {"reason": rx.void_reason})
    return {"rx_code": rx.rx_code, "status": rx.status}


# -------------------------------------------------------------- version history
@router.get("/{rx_id}/versions")
def list_versions(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_view(db, rx, user):
        raise forbidden("Not permitted to view this prescription")
    rows = db.scalars(
        select(M.PrescriptionVersion).where(M.PrescriptionVersion.rx_id == rx_id)
        .order_by(M.PrescriptionVersion.version_no)
    ).all()
    return {
        "rx_id": rx_id, "rx_code": rx.rx_code, "current_version": len(rows),
        "results": [{
            "version": v.version_no, "reason": v.reason,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "content_hash": v.content_hash,
            "item_count": len(json.loads(v.snapshot_json or "{}").get("items", [])),
            "test_count": len(json.loads(v.snapshot_json or "{}").get("tests", [])),
        } for v in rows],
    }


@router.get("/{rx_id}/versions/{version_no}")
def get_version(rx_id: int, version_no: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_view(db, rx, user):
        raise forbidden("Not permitted to view this prescription")
    v = db.scalar(select(M.PrescriptionVersion).where(
        M.PrescriptionVersion.rx_id == rx_id, M.PrescriptionVersion.version_no == version_no))
    if not v:
        raise not_found("Version not found")
    return {"version": v.version_no, "reason": v.reason, "content_hash": v.content_hash,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "snapshot": json.loads(v.snapshot_json or "{}")}


# -------------------------------------------------------------------- payload
def _signable_payload(db: Session, rx: M.Prescription) -> dict:
    """Canonical payload for the digital seal. Excludes volatile fields."""
    payload = _rx_payload(db, rx)
    payload.pop("status", None)
    payload.pop("versions_count", None)
    payload.pop("latest_version", None)
    return payload


def _version_count(db: Session, rx_id: int) -> int:
    return int(db.scalar(
        select(func.count()).select_from(M.PrescriptionVersion)
        .where(M.PrescriptionVersion.rx_id == rx_id)
    ) or 0)


def _rx_payload(db: Session, rx: M.Prescription) -> dict:
    items = db.scalars(select(M.PrescriptionItem).where(M.PrescriptionItem.rx_id == rx.id)).all()
    tests = db.scalars(select(M.PrescriptionTest).where(M.PrescriptionTest.rx_id == rx.id)).all()
    doctor = db.get(M.Doctor, rx.doctor_id)
    patient = db.get(M.Patient, rx.patient_id)
    hospital = db.get(M.Hospital, rx.hospital_id) if rx.hospital_id else None
    vcount = _version_count(db, rx.id)
    return {
        "id": rx.id,
        "rx_code": rx.rx_code,
        "public_token": rx.public_token,
        "issued_at": rx.issued_at.isoformat() if rx.issued_at else None,
        "status": rx.status,
        "versions_count": vcount,
        "latest_version": vcount,
        "doctor": {"id": doctor.id, "name": doctor.name, "bmdc_no": doctor.bmdc_no,
                   "speciality": doctor.speciality_name, "qualifications": doctor.qualifications,
                   "designation": doctor.designation, "district": doctor.district_name} if doctor else None,
        "hospital": {"id": hospital.id, "name": hospital.name,
                     "address": getattr(hospital, "address", None),
                     "district": hospital.district_name} if hospital else None,
        "patient": {"id": patient.id, "patient_code": patient.patient_code, "full_name": patient.full_name,
                    "sex": patient.sex, "dob": patient.dob} if patient else None,
        "diagnosis": rx.diagnosis, "chief_complaints": rx.chief_complaints,
        "notes": rx.notes, "advice": rx.advice,
        "items": [{
            "brand_id": i.brand_id,
            "name": i.free_text_name or (db.get(M.Brand, i.brand_id).name if i.brand_id and db.get(M.Brand, i.brand_id) else None),
            "form": i.form, "strength": i.strength, "dose": json.loads(i.dose_json or "{}"),
            "bn_dosage_text": i.bn_dosage_text, "instructions": i.instructions,
        } for i in items],
        "tests": [{
            "test_id": t.test_id,
            "name": t.free_text_name or (db.get(M.LabTest, t.test_id).name if t.test_id and db.get(M.LabTest, t.test_id) else None),
            "note": t.note,
        } for t in tests],
    }


@router.get("/mine")
def my_prescriptions(user: M.User = Depends(require_role("doctor", "system_admin")), limit: int = 50, db: Session = Depends(get_db)):
    """The doctor's own prescriptions, newest first — where a later edit starts."""
    doctor = _doctor_for_user(db, user)
    if not doctor and user.role != "system_admin":
        raise forbidden("No doctor profile linked to this account")
    stmt = select(M.Prescription).order_by(M.Prescription.issued_at.desc()).limit(limit)
    if doctor and user.role != "system_admin":
        stmt = stmt.where(M.Prescription.doctor_id == doctor.id)
    rows = db.scalars(stmt).all()
    out = []
    for rx in rows:
        p = db.get(M.Patient, rx.patient_id)
        out.append({
            "id": rx.id, "rx_code": rx.rx_code, "status": rx.status,
            "issued_at": rx.issued_at.isoformat() if rx.issued_at else None,
            "patient_name": p.full_name if p else None,
            "patient_code": p.patient_code if p else None,
            "diagnosis": rx.diagnosis, "versions": _version_count(db, rx.id),
        })
    return {"count": len(out), "results": out}


@router.get("/{rx_id}")
def get_prescription(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_view(db, rx, user):
        raise forbidden("Not permitted to view this prescription")
    log_action(db, user.id, "prescription_view", "prescription", rx.rx_code)
    return _rx_payload(db, rx)


@router.get("/{rx_id}/qr")
def rx_qr(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authenticated QR preview (the same code the print view embeds)."""
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_view(db, rx, user):
        raise forbidden("Not permitted")
    url = f"/rx/{rx.public_token}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"qr_png_base64": base64.b64encode(buf.getvalue()).decode(),
            "payload": url, "rx_code": rx.rx_code}


@router.get("/{rx_id}/verify")
def verify_rx(rx_id: int, db: Session = Depends(get_db)):
    """Public integrity check: recompute the seal and compare."""
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not rx.content_hash:
        return {"verified": False, "reason": "not_finalized"}
    ok = verify_signature(_signable_payload(db, rx), rx.content_hash, rx.signature or "")
    return {"verified": ok, "rx_code": rx.rx_code, "content_hash": rx.content_hash}


# ---------------------------------------------------------------------- print
@router.get("/{rx_id}/print", response_class=HTMLResponse)
def print_prescription(rx_id: int, user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Printable prescription WITH the QR code.

    The QR encodes an absolute link to the public lookup page, so a scanned code
    works from any device without a login.
    """
    rx = db.get(M.Prescription, rx_id)
    if not rx:
        raise not_found("Prescription not found")
    if not _can_view(db, rx, user):
        raise forbidden("Not permitted to print this prescription")
    data = _rx_payload(db, rx)
    # Prices are looked up at DISPLAY time, never stored on the prescription: the
    # digital seal covers the clinical content only, so enriching here (and on the
    # public scan route) cannot invalidate a signature that already exists.
    _add_prices(db, data, with_availability=True)
    scan_url = f"/rx/{rx.public_token}"
    img = qrcode.make(scan_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    log_action(db, user.id, "prescription_print", "prescription", rx.rx_code)
    return HTMLResponse(_render_print_html(data, qr_b64, scan_url))


def _add_prices(db: Session, payload: dict, with_availability: bool = False) -> None:
    """Attach catalogue prices to the prescribed medicines and tests.

    Deliberately NOT part of ``_rx_payload``: that dict is what gets signed, so
    putting prices in it would break every seal the moment a price changed. This
    runs on top of the sealed payload for display only.

    Raw SQL on purpose — the shape of the catalogue tables is not needed here,
    just two columns each, and this keeps working if the ORM models move.
    """
    from sqlalchemy import text as _sql

    def _f(v):
        return float(v) if v is not None else None

    for item in payload.get("items") or []:
        bid = item.get("brand_id")
        if not bid:
            continue
        row = db.execute(_sql(
            "SELECT b.unit_price, b.strip_price, b.pack_size, b.pack_price, c.name "
            "FROM brands b LEFT JOIN companies c ON c.id = b.company_id WHERE b.id = :i"
        ), {"i": bid}).fetchone()
        if not row:
            continue
        item["company"] = row[4]
        item["unit_price"] = _f(row[0])
        item["strip_price"] = _f(row[1])
        item["pack_size"] = row[2]
        item["pack_price"] = _f(row[3])
        if with_availability:
            alt = db.execute(_sql(
                "SELECT COUNT(DISTINCT b2.company_id) FROM brands b2 "
                "WHERE b2.generic_id = (SELECT generic_id FROM brands WHERE id = :i) "
                "AND b2.id <> :i AND b2.status = 'active'"
            ), {"i": bid}).fetchone()
            item["alternative_companies"] = int(alt[0]) if alt and alt[0] is not None else 0

    for t in payload.get("tests") or []:
        tid = t.get("test_id")
        if not tid:
            continue
        row = db.execute(_sql(
            "SELECT price_min, price_max FROM tests WHERE id = :i"
        ), {"i": tid}).fetchone()
        if not row:
            continue
        t["price_min"] = _f(row[0])
        t["price_max"] = _f(row[1])


def _price_txt(it: dict) -> str:
    """Short price label for one prescribed medicine, or "" when unknown."""
    bits = []
    if it.get("pack_price") is not None:
        bits.append(f"{it.get('pack_size') + ' ' if it.get('pack_size') else ''}৳{it['pack_price']:.2f}")
    elif it.get("unit_price") is not None:
        bits.append(f"৳{it['unit_price']:.2f}/unit")
    if it.get("alternative_companies"):
        bits.append(f"{it['alternative_companies']} alt.")
    return " · ".join(bits)


def _render_print_html(d: dict, qr_b64: str, scan_url: str) -> str:
    """Server-rendered document: header bands, patient block, Rx symbol, medicine
    table, investigations, advice, signature area and the QR."""
    doc = d.get("doctor") or {}
    pat = d.get("patient") or {}
    hos = d.get("hospital") or {}

    def esc(v) -> str:
        return escape(str(v)) if v not in (None, "") else "—"

    item_rows = []
    for i, it in enumerate(d.get("items") or [], 1):
        dose = it.get("dose") or {}
        slots = dose.get("slots") or {}
        slot_txt = " + ".join(f"{k[:2].title()} {v}" for k, v in slots.items() if v) or "—"
        dur = dose.get("duration") or {}
        dur_txt = (f"{dur.get('value')} {dur.get('unit', '')}".strip() if dur.get("value")
                   else (str(dur.get("kind", "")).replace("_", " ") or "—"))
        item_rows.append(
            "<tr>"
            f'<td class="n">{i}</td>'
            f"<td><b>{esc(it.get('name'))}</b><div class=\"muted\">{esc(it.get('strength'))} &middot; {esc(it.get('form'))}</div></td>"
            f"<td>{esc(slot_txt)}</td>"
            f"<td>{esc(dur_txt)}</td>"
            f"<td>{esc(it.get('bn_dosage_text') or it.get('instructions'))}</td>"
            f"<td class=\"muted\">{esc(_price_txt(it))}</td>"
            "</tr>"
        )
    if not item_rows:
        item_rows.append('<tr><td colspan="6" class="muted">No medicines recorded.</td></tr>')

    def _test_price(t: dict) -> str:
        if t.get("price_min") is None:
            return ""
        hi = f" – ৳{t['price_max']:.2f}" if t.get("price_max") else ""
        return f' <span class="muted">(৳{t["price_min"]:.2f}{hi})</span>'

    test_rows = "".join(
        f"<li><b>{esc(t.get('name'))}</b>{(' &mdash; ' + esc(t.get('note'))) if t.get('note') else ''}{_test_price(t)}</li>"
        for t in (d.get("tests") or [])
    ) or '<li class="muted">No investigations requested.</li>'

    css = """
  :root { --ink:#0e1726; --muted:#5b6b82; --line:#c9d4e2; --teal:#0e7c86; }
  * { box-sizing: border-box; }
  body { margin:0; background:#eef2f7; font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color:var(--ink); }
  .sheet { width: 210mm; min-height: 285mm; margin: 16px auto; background:#fff; padding: 14mm 14mm 10mm; box-shadow:0 6px 30px rgba(14,23,38,.16); position:relative; }
  .topbar { height:7px; background:linear-gradient(90deg,#0e7c86,#12b3c7 60%,#7fe3d4); border-radius:4px; }
  header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-top:12px; padding-bottom:10px; border-bottom:2px solid var(--ink); }
  .doc h1 { margin:0; font-size:21px; }
  .doc .qual { font-size:11.5px; color:var(--muted); margin-top:3px; line-height:1.45; }
  .doc .spec { display:inline-block; margin-top:5px; font-size:11px; font-weight:600; color:#fff; background:var(--teal); padding:2px 9px; border-radius:999px; }
  .clinic { text-align:right; font-size:11.5px; color:var(--muted); line-height:1.5; max-width:64mm; }
  .clinic .nm { font-weight:700; color:var(--ink); font-size:13px; }
  .meta { display:flex; justify-content:space-between; gap:14px; margin-top:12px; font-size:12px; }
  .meta .box { flex:1; border:1px solid var(--line); border-radius:8px; padding:8px 10px; }
  .meta .k { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.6px; }
  .rx { font-size:34px; font-weight:700; color:var(--teal); font-style:italic; margin:16px 0 4px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { text-align:left; background:#f4f8fb; border-bottom:1.5px solid var(--line); padding:7px 8px; font-size:10.5px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); }
  td { padding:7px 8px; border-bottom:1px solid #e8eef5; vertical-align:top; }
  td.n { width:26px; color:var(--muted); }
  .muted { color:var(--muted); font-size:11px; }
  section { margin-top:16px; }
  section h3 { font-size:12px; text-transform:uppercase; letter-spacing:.7px; color:var(--teal); margin:0 0 6px; border-bottom:1px solid var(--line); padding-bottom:4px; }
  ul { margin:0; padding-left:18px; font-size:12px; }
  .foot { display:flex; justify-content:space-between; align-items:flex-end; gap:18px; margin-top:26px; }
  .sign { border-top:1.5px solid var(--ink); width:62mm; text-align:center; padding-top:5px; font-size:11px; }
  .qr { text-align:center; }
  .qr img { width:31mm; height:31mm; }
  .qr .cap { font-size:9.5px; color:var(--muted); margin-top:3px; max-width:44mm; }
  .barcode { margin-top:8px; font-family:ui-monospace,Menlo,Consolas,monospace; font-size:9.5px; letter-spacing:1.5px; color:var(--muted); }
  .seal { margin-top:14px; border-top:1px dashed var(--line); padding-top:6px; font-size:9.5px; color:var(--muted); display:flex; justify-content:space-between; gap:10px; }
  .no-print { text-align:center; margin:14px; }
  .no-print button { background:var(--teal); color:#fff; border:0; border-radius:8px; padding:10px 18px; font-size:13px; cursor:pointer; }
  @media print { body { background:#fff; } .sheet { margin:0; box-shadow:none; width:auto; min-height:0; padding:10mm; } .no-print { display:none; } }
"""

    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(d.get('rx_code'))} &mdash; Prescription</title>
<style>{css}</style></head>
<body>
<div class="no-print"><button onclick="window.print()">Print prescription</button></div>
<div class="sheet">
  <div class="topbar"></div>
  <header>
    <div class="doc">
      <h1>{esc(doc.get('name'))}</h1>
      <div class="qual">{esc(doc.get('qualifications'))}<br>{esc(doc.get('designation'))}<br>BMDC Reg. No: {esc(doc.get('bmdc_no'))}</div>
      <span class="spec">{esc(doc.get('speciality'))}</span>
    </div>
    <div class="clinic">
      <div class="nm">{esc(hos.get('name'))}</div>
      <div>{esc(hos.get('address'))}<br>{esc(hos.get('district'))}</div>
    </div>
  </header>

  <div class="meta">
    <div class="box"><div class="k">Patient</div><b>{esc(pat.get('full_name'))}</b><div class="muted">{esc(pat.get('patient_code'))}</div></div>
    <div class="box"><div class="k">Date of birth / Sex</div><b>{esc(pat.get('dob') or '&#8212;')}</b><div class="muted">{esc(pat.get('sex'))}</div></div>
    <div class="box"><div class="k">Rx No.</div><b>{esc(d.get('rx_code'))}</b><div class="muted">{esc((d.get('issued_at') or '')[:10])}</div></div>
  </div>

  <div class="meta" style="margin-top:8px">
    <div class="box"><div class="k">Chief complaints</div><div>{esc(d.get('chief_complaints'))}</div></div>
    <div class="box"><div class="k">Diagnosis</div><div>{esc(d.get('diagnosis'))}</div></div>
  </div>

  <div class="rx">&#8478;</div>
  <table>
    <thead><tr><th></th><th>Medicine</th><th>Dose</th><th>Duration</th><th>Instructions</th><th>Price</th></tr></thead>
    <tbody>{''.join(item_rows)}</tbody>
  </table>

  <section>
    <h3>Investigations requested</h3>
    <ul>{test_rows}</ul>
  </section>

  <section>
    <h3>Advice</h3>
    <div style="font-size:12px">{esc(d.get('advice'))}</div>
  </section>

  <div class="foot">
    <div class="sign">{esc(doc.get('name'))}<div class="muted">Signature &amp; seal</div></div>
    <div class="qr">
      <img src="data:image/png;base64,{qr_b64}" alt="Scan for medicine and test prices">
      <div class="cap">Scan to look up medicine &amp; test prices</div>
      <div class="barcode">{esc(d.get('rx_code'))}</div>
    </div>
  </div>

  <div class="seal">
    <span>Digital seal: {esc((d.get('status') or '').upper())} &middot; version {esc(d.get('versions_count'))}</span>
    <span>{esc(scan_url)}</span>
  </div>
</div>
</body></html>"""
    return body


# ------------------------------------------------------- public price lookup
@router.get("/public/{token}")
def public_rx(token: str, db: Session = Depends(get_db)):
    """Read-only public view reached by scanning the QR (no login)."""
    rx = db.scalar(select(M.Prescription).where(M.Prescription.public_token == token))
    if not rx:
        raise not_found("Prescription not found")
    payload = _rx_payload(db, rx)
    # The point of the scan: the prescribed medicines and tests WITH their
    # catalogue prices.
    _add_prices(db, payload, with_availability=True)
    payload["verified"] = bool(rx.content_hash) and verify_signature(
        _signable_payload(db, rx), rx.content_hash, rx.signature or "")
    payload["disclaimer"] = "Informational only. Not medical advice."
    return payload
