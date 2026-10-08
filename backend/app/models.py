"""SQLAlchemy 2.x models for BanglaMed (all modules)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Deterministic build clock ───────────────────────────────────────────────
# The catalog is reconstructed from the committed source data on every deploy
# (see scripts/build_db.py), because Render's free tier has no persistent disk.
# For the rebuilt state to be *identical* every time, the rows written during
# that rebuild must not carry the wall-clock time of the build.
#
# When BANGLAMED_BUILD_EPOCH is set (build/redeploy only), every catalog
# timestamp resolves to that single fixed instant, so two independent builds
# produce byte-identical rows and the state fingerprint (scripts/
# state_fingerprint.py) is stable across redeploys. At runtime the variable is
# unset, so real user activity is stamped with the real time as before.
BUILD_EPOCH_ENV = "BANGLAMED_BUILD_EPOCH"
DEFAULT_BUILD_EPOCH = "2026-01-01T00:00:00+00:00"


def build_epoch() -> datetime | None:
    raw = os.environ.get(BUILD_EPOCH_ENV)
    if not raw:
        return None
    if raw.strip().lower() in ("1", "true", "yes"):
        raw = DEFAULT_BUILD_EPOCH
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stamp() -> datetime:
    """Timestamp for a new row: fixed during a deterministic build, else now."""
    epoch = build_epoch()
    return epoch if epoch is not None else utcnow()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=stamp, onupdate=stamp)


# ---------------------------------------------------------------- Identity
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)  # patient|doctor|hospital_admin|system_admin
    account_type: Mapped[str] = mapped_column(String(20), default="personal")  # personal|family
    full_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HospitalAdmin(Base):
    __tablename__ = "hospital_admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"), index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=stamp, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")


# ---------------------------------------------------------------- Geo
class GeoDivision(Base):
    __tablename__ = "geo_divisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    name_bn: Mapped[str | None] = mapped_column(String(80), nullable=True)


class GeoDistrict(Base):
    __tablename__ = "geo_districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    division_id: Mapped[int] = mapped_column(ForeignKey("geo_divisions.id"), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    name_bn: Mapped[str | None] = mapped_column(String(80), nullable=True)


class GeoUpazila(Base):
    __tablename__ = "geo_upazilas"
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("geo_districts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))


class GeoThana(Base):
    __tablename__ = "geo_thanas"
    id: Mapped[int] = mapped_column(primary_key=True)
    upazila_id: Mapped[int] = mapped_column(ForeignKey("geo_upazilas.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))


# ---------------------------------------------------------------- Catalog
class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_name: Mapped[str] = mapped_column(String(160), default="")
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    entity: Mapped[str] = mapped_column(String(60), default="")
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    report_json: Mapped[str] = mapped_column(Text, default="{}")


class Company(Base, TimestampMixin):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    established: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_share: Mapped[str | None] = mapped_column(String(20), nullable=True)
    growth: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_generics: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headquarter: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contact_details: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class DrugClass(Base, TimestampMixin):
    __tablename__ = "drug_classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    subclasses_json: Mapped[str] = mapped_column(Text, default="[]")
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class DosageForm(Base, TimestampMixin):
    __tablename__ = "dosage_forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class Generic(Base, TimestampMixin):
    __tablename__ = "generics"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    name_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    drug_class_id: Mapped[int | None] = mapped_column(ForeignKey("drug_classes.id"), nullable=True)
    therapeutic_class: Mapped[str | None] = mapped_column(String(300), nullable=True)
    pregnancy_category: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pregnancy_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class GenericContent(Base):
    __tablename__ = "generic_content"
    __table_args__ = (UniqueConstraint("generic_id", "lang", "section", name="uq_generic_content"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    generic_id: Mapped[int] = mapped_column(ForeignKey("generics.id"), index=True)
    lang: Mapped[str] = mapped_column(String(5), default="en")
    section: Mapped[str] = mapped_column(String(40), index=True)
    text: Mapped[str] = mapped_column(Text, default="")


class Brand(Base, TimestampMixin):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    generic_id: Mapped[int | None] = mapped_column(ForeignKey("generics.id"), nullable=True, index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    form_id: Mapped[int | None] = mapped_column(ForeignKey("dosage_forms.id"), nullable=True)
    form_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    strength_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    strength_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    strength_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    strip_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    pack_size: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pack_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    pack_json: Mapped[str] = mapped_column(Text, default="{}")
    pieces_per_strip: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_herbal: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    # denormalised content (from brand scrape) for fast detail pages
    indications: Mapped[str | None] = mapped_column(Text, nullable=True)
    pharmacology: Mapped[str | None] = mapped_column(Text, nullable=True)
    dosage_administration: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    contraindications: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    pregnancy_lactation: Mapped[str | None] = mapped_column(Text, nullable=True)
    precautions_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    overdose_effects: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    therapeutic_class: Mapped[str | None] = mapped_column(String(300), nullable=True)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class BrandAlias(Base):
    __tablename__ = "brand_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200), index=True)


class Indication(Base, TimestampMixin):
    __tablename__ = "indications"
    id: Mapped[int] = mapped_column(primary_key=True)
    med_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    generics_json: Mapped[str] = mapped_column(Text, default="[]")
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class InteractionCurated(Base):
    __tablename__ = "interactions_curated"
    id: Mapped[int] = mapped_column(primary_key=True)
    generic_a: Mapped[str] = mapped_column(String(200), index=True)
    generic_b: Mapped[str] = mapped_column(String(200), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warn")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------- Tests
class TestCategory(Base):
    __tablename__ = "test_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


class LabTest(Base, TimestampMixin):
    __tablename__ = "tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    name_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aliases: Mapped[str | None] = mapped_column(String(400), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("test_categories.id"), nullable=True)
    sample_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    price_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fasting_required: Mapped[bool] = mapped_column(Boolean, default=False)
    fasting_hours_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fasting_hours_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prep_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    procedure_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedure_source: Mapped[str] = mapped_column(String(20), default="seed")
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class TestPrice(Base):
    __tablename__ = "test_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id"), index=True)
    hospital_name: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    badge: Mapped[str | None] = mapped_column(String(40), nullable=True)


# ---------------------------------------------------------------- Directory
class Hospital(Base, TimestampMixin):
    __tablename__ = "hospitals"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    name_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    division_id: Mapped[int | None] = mapped_column(ForeignKey("geo_divisions.id"), nullable=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("geo_districts.id"), nullable=True, index=True)
    district_name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    upazila_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thana_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hours: Mapped[str | None] = mapped_column(String(200), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Number of doctors the source listing advertises for this facility.
    listed_doctors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


class Speciality(Base):
    __tablename__ = "specialities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    bmdc_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    speciality_id: Mapped[int | None] = mapped_column(ForeignKey("specialities.id"), nullable=True, index=True)
    speciality_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    qualifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    designation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    district_name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    signature_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_status: Mapped[str] = mapped_column(String(20), default="unverified")


class DoctorAffiliation(Base):
    __tablename__ = "doctor_affiliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)


# ---------------------------------------------------------------- Patients
class Patient(Base, TimestampMixin):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    dob: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    relation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_pregnant: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lactating: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Allergy(Base):
    __tablename__ = "allergies"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    substance: Mapped[str] = mapped_column(String(200))
    generic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccessCode(Base):
    __tablename__ = "access_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_by_doctor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


# ---------------------------------------------------------------- Prescriptions
class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    rx_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    public_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    chief_complaints: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|finalized|void
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    rx_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_text_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form: Mapped[str | None] = mapped_column(String(80), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dose_json: Mapped[str] = mapped_column(Text, default="{}")
    bn_dosage_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrescriptionTest(Base):
    __tablename__ = "prescription_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    rx_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    test_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_text_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SafetyAcknowledgement(Base):
    __tablename__ = "safety_acknowledgements"
    id: Mapped[int] = mapped_column(primary_key=True)
    rx_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


class PrescriptionVersion(Base):
    """Immutable snapshot of a prescription at one point in time (M5).

    The doctor may edit and save a prescription repeatedly. Each save appends a
    NEW row here and never rewrites an earlier one, so the full clinical history
    is preserved: version 1 is what was first written, version N is the current
    text, and every intermediate revision in between is still readable.
    ``version_no`` is 1-based and unique per ``rx_id``.
    """
    __tablename__ = "prescription_versions"
    __table_args__ = (UniqueConstraint("rx_id", "version_no", name="uq_rx_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rx_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


# ---------------------------------------------------------------- Uploads
class RxUpload(Base):
    __tablename__ = "rx_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    image_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    quality_json: Mapped[str] = mapped_column(Text, default="{}")
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


class TestRecord(Base):
    __tablename__ = "test_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id"), index=True)
    rx_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performed_on: Mapped[str | None] = mapped_column(String(20), nullable=True)


# ---------------------------------------------------------------- Reminders
class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    rx_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="Medicine reminder")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


class ReminderItem(Base):
    __tablename__ = "reminder_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id"), index=True)
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    medicine_name: Mapped[str] = mapped_column(String(200), default="")
    times_json: Mapped[str] = mapped_column(Text, default="[]")
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ReminderEvent(Base):
    __tablename__ = "reminder_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("reminder_items.id"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    action: Mapped[str] = mapped_column(String(20), default="pending")  # taken|snoozed|skipped|pending
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    keys_json: Mapped[str] = mapped_column(Text, default="{}")


# ---------------------------------------------------------------- Booking
class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    total_serials: Mapped[int] = mapped_column(Integer, default=30)
    booking_opens_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    booking_closes_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    session_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("schedule_id", "serial_no", name="uq_schedule_serial"),
        UniqueConstraint("schedule_id", "patient_id", name="uq_schedule_patient"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    apt_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("doctor_schedules.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    serial_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="waiting")  # waiting|completed|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=stamp)


# ---------------------------------------------------------------- FTS (raw, managed in import)
class MedicineFts(Base):
    """Denormalised search index over brands.

    ``brand``/``generic``/... keep the display text. The ``*_n`` columns hold the
    same text already normalised (lower-cased, punctuation folded) so a search
    never has to re-normalise 25k strings in Python per keystroke, and so an
    index can be used for prefix matching. ``ix_medicine_fts_brand_n`` and
    ``ix_medicine_fts_brand_id`` are declared here; the ``(brand_n, id)``
    covering index is added by scripts/build_indexes.py.
    """
    __tablename__ = "medicine_fts"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(Integer, index=True)
    brand: Mapped[str] = mapped_column(String(200), default="")
    generic: Mapped[str] = mapped_column(String(300), default="")
    company: Mapped[str] = mapped_column(String(200), default="")
    aliases: Mapped[str] = mapped_column(String(400), default="")
    name_bn: Mapped[str] = mapped_column(String(300), default="")
    strength: Mapped[str] = mapped_column(String(120), default="")
    form: Mapped[str] = mapped_column(String(120), default="")
    # normalised copies + a first-token key, all indexed, for fast prefix search
    brand_n: Mapped[str] = mapped_column(String(200), default="", index=True)
    generic_n: Mapped[str] = mapped_column(String(300), default="", index=True)
    company_n: Mapped[str] = mapped_column(String(200), default="", index=True)
    form_n: Mapped[str] = mapped_column(String(120), default="")
    strength_n: Mapped[str] = mapped_column(String(120), default="")
    first_token: Mapped[str] = mapped_column(String(60), default="", index=True)
    brand_root: Mapped[str] = mapped_column(String(60), default="", index=True)
