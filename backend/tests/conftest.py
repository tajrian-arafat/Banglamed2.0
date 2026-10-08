from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'banglamed.db'}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client):
    return _login(client, "admin", "Admin@123")


@pytest.fixture(scope="session")
def doctor_token(client):
    return _login(client, "dr.rahman", "Doctor@123")


@pytest.fixture(scope="session")
def patient_token(client):
    return _login(client, "patient.demo", "Patient@123")


@pytest.fixture(scope="session")
def hospital_token(client):
    return _login(client, "hospital.dhaka", "Hospital@123")


def auth(token):
    return {"Authorization": f"Bearer {token}"}
