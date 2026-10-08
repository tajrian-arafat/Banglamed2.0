"""API + RBAC matrix (SPEC 9)."""
from __future__ import annotations

from tests.conftest import auth


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_modules_manifest(client):
    r = client.get("/api/modules")
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["modules"]}
    assert {"catalog", "prescriptions", "safety", "appointments", "admin"} <= ids


def test_medicine_search(client):
    r = client.get("/api/medicines/search", params={"q": "celofen"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_medicine_search_typo(client):
    r = client.get("/api/medicines/search", params={"q": "celofn"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_medicine_detail(client):
    s = client.get("/api/medicines/search", params={"q": "celofen"}).json()["results"][0]
    r = client.get(f"/api/medicines/{s['brand_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["brand"]["name"]
    assert "sections" in body
    assert "alternatives" in body


def test_tests_search(client):
    r = client.get("/api/tests/search", params={"q": "blood"})
    assert r.status_code == 200


def test_directory_doctors(client):
    r = client.get("/api/directory/doctors", params={"limit": 5})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_directory_hospitals(client):
    r = client.get("/api/directory/hospitals", params={"limit": 5})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


# ---- RBAC matrix
def test_patient_cannot_create_prescription(client, patient_token):
    r = client.post("/api/prescriptions", json={"patient_id": 1, "items": []}, headers=auth(patient_token))
    assert r.status_code == 403


def test_doctor_cannot_list_users(client, doctor_token):
    r = client.get("/api/admin/users", headers=auth(doctor_token))
    assert r.status_code == 403


def test_patient_cannot_view_analytics(client, patient_token):
    r = client.get("/api/analytics/hospital", headers=auth(patient_token))
    assert r.status_code == 403


def test_anonymous_cannot_view_records(client):
    r = client.get("/api/records/1/timeline")
    assert r.status_code == 401


def test_admin_can_list_users(client, admin_token):
    r = client.get("/api/admin/users", headers=auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 5


def test_admin_modules(client, admin_token):
    r = client.get("/api/admin/modules", headers=auth(admin_token))
    assert r.status_code == 200


def test_admin_audit(client, admin_token):
    r = client.get("/api/admin/audit", headers=auth(admin_token))
    assert r.status_code == 200
    assert len(r.json()["results"]) >= 1


def test_hospital_analytics(client, hospital_token):
    r = client.get("/api/analytics/hospital", headers=auth(hospital_token))
    assert r.status_code == 200
    assert "trend" in r.json()


def test_system_analytics(client, admin_token):
    r = client.get("/api/analytics/system", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["counts"]["brands"] > 20000


def test_login_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


def test_me(client, patient_token):
    r = client.get("/api/auth/me", headers=auth(patient_token))
    assert r.status_code == 200
    assert r.json()["role"] == "patient"
