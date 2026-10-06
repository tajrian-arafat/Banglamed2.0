"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---- auth
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=160)
    account_type: str = "personal"  # personal|family
    email: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    full_name: str


class MeOut(BaseModel):
    id: int
    username: str
    role: str
    account_type: str
    full_name: str
    email: str | None = None


# ---- patients
class PatientIn(BaseModel):
    full_name: str
    dob: str | None = None
    sex: str | None = None
    relation: str | None = None
    blood_group: str | None = None
    is_pregnant: bool = False
    is_lactating: bool = False
    phone: str | None = None


class PatientOut(PatientIn):
    id: int
    patient_code: str


class AllergyIn(BaseModel):
    substance: str
    note: str | None = None


# ---- prescriptions
class DoseIn(BaseModel):
    slots: dict[str, float] = Field(default_factory=dict)  # morning/noon/evening/night
    unit: str = "tablet"
    meal: str = "after"
    duration: dict[str, Any] = Field(default_factory=dict)  # {value, unit} or {kind:"continue"}
    every_hours: int | None = None


class RxItemIn(BaseModel):
    brand_id: int | None = None
    generic_id: int | None = None
    free_text_name: str | None = None
    form: str | None = None
    strength: str | None = None
    dose: DoseIn | None = None
    instructions: str | None = None


class RxTestIn(BaseModel):
    test_id: int | None = None
    free_text_name: str | None = None
    note: str | None = None


class PrescriptionIn(BaseModel):
    patient_id: int
    hospital_id: int | None = None
    appointment_id: int | None = None
    diagnosis: str | None = None
    chief_complaints: str | None = None
    notes: str | None = None
    advice: str | None = None
    items: list[RxItemIn] = Field(default_factory=list)
    tests: list[RxTestIn] = Field(default_factory=list)
    acknowledgements: list[dict[str, Any]] = Field(default_factory=list)


class SafetyCheckIn(BaseModel):
    patient_id: int
    items: list[RxItemIn] = Field(default_factory=list)


# ---- cost
class CostItemIn(BaseModel):
    brand_id: int
    per_dose_qty: float = 1
    doses_per_day: float = 1
    duration_days: int | None = None
    kind: str = "course"  # course|continue|as_needed


class CostIn(BaseModel):
    items: list[CostItemIn] = Field(default_factory=list)
    test_ids: list[int] = Field(default_factory=list)


# ---- appointments
class ScheduleIn(BaseModel):
    doctor_id: int
    hospital_id: int | None = None
    date: str
    total_serials: int = 30
    booking_opens_at: str | None = None
    booking_closes_at: str | None = None
    session_start: str | None = None
    session_end: str | None = None
    fee: float | None = None


class BookIn(BaseModel):
    schedule_id: int
    patient_id: int
    serial_no: int | None = None  # None -> next available


# ---- reminders
class ReminderIn(BaseModel):
    patient_id: int
    source: str = "manual"
    rx_id: int | None = None
    title: str = "Medicine reminder"
    items: list[dict[str, Any]] = Field(default_factory=list)


# ---- admin
class CreateStaffIn(BaseModel):
    username: str
    password: str
    full_name: str
    role: str  # doctor|hospital_admin|system_admin
    hospital_id: int | None = None
    speciality: str | None = None
    bmdc_no: str | None = None
