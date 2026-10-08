"""End-to-end: prescription -> safety -> finalize -> verify -> cost -> booking."""
from __future__ import annotations

from tests.conftest import auth


def _first_brand(client, q):
    return client.get("/api/medicines/search", params={"q": q}).json()["results"][0]


def test_full_prescription_workflow(client, doctor_token, patient_token):
    # doctor finds a patient
    pts = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()["results"]
    assert pts
    patient_id = pts[0]["id"]
    brand = _first_brand(client, "celofen")
    payload = {
        "patient_id": patient_id,
        "diagnosis": "Test diagnosis",
        "items": [{"brand_id": brand["brand_id"], "dose": {"slots": {"morning": 1, "night": 1}, "unit": "tablet",
                                                           "meal": "after", "duration": {"value": 7, "unit": "day"}}}],
        "tests": [],
        "acknowledgements": [],
    }
    r = client.post("/api/prescriptions", json=payload, headers=auth(doctor_token))
    assert r.status_code == 200, r.text
    rx = r.json()
    assert rx["rx_code"].startswith("RX-BD-")
    # finalize
    f = client.post(f"/api/prescriptions/{rx['id']}/finalize", headers=auth(doctor_token))
    assert f.status_code == 200
    assert f.json()["signature"]
    # verify
    v = client.get(f"/api/prescriptions/{rx['id']}/verify")
    assert v.status_code == 200
    assert v.json()["verified"] is True
    # patient can read own
    g = client.get(f"/api/prescriptions/{rx['id']}", headers=auth(patient_token))
    assert g.status_code == 200
    assert g.json()["items"][0]["bn_dosage_text"]


def test_safety_duplicate_warning(client, doctor_token):
    pts = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()["results"]
    patient_id = pts[0]["id"]
    brand = _first_brand(client, "celofen")
    payload = {"patient_id": patient_id, "items": [
        {"brand_id": brand["brand_id"]}, {"brand_id": brand["brand_id"]}]}
    r = client.post("/api/prescriptions/safety-check", json=payload, headers=auth(doctor_token))
    assert r.status_code == 200
    codes = {w["code"] for w in r.json()["warnings"]}
    assert "duplicate_ingredient" in codes


def test_cost_estimate(client):
    brand = _first_brand(client, "celofen")
    r = client.post("/api/cost/estimate", json={"items": [
        {"brand_id": brand["brand_id"], "per_dose_qty": 1, "doses_per_day": 2, "duration_days": 7, "kind": "course"}]})
    assert r.status_code == 200
    assert r.json()["totals"]["full_course"] > 0


def test_booking_concurrency(client, patient_token, doctor_token):
    """Two patients race for the same serial; exactly one wins."""
    import uuid
    from datetime import datetime, timedelta, timezone

    # a fresh schedule with a unique date so the test is idempotent across runs
    doc = client.get("/api/doctor/profile", headers=auth(doctor_token)).json()
    date = (datetime.now(timezone.utc) + timedelta(days=400 + uuid.uuid4().int % 1000)).date().isoformat()
    sched = client.post("/api/appointments/schedules",
                        json={"doctor_id": doc["id"], "date": date, "total_serials": 5},
                        headers=auth(doctor_token)).json()
    sid = sched["id"]
    tag = uuid.uuid4().hex[:6]
    p1 = client.post("/api/patients", json={"full_name": f"Race A {tag}", "relation": "self"}, headers=auth(patient_token)).json()
    p2 = client.post("/api/patients", json={"full_name": f"Race B {tag}", "relation": "child"}, headers=auth(patient_token)).json()
    r1 = client.post("/api/appointments/book", json={"schedule_id": sid, "patient_id": p1["id"], "serial_no": 1}, headers=auth(patient_token))
    r2 = client.post("/api/appointments/book", json={"schedule_id": sid, "patient_id": p2["id"], "serial_no": 1}, headers=auth(patient_token))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409], (r1.text, r2.text)


def test_booking_duplicate_patient(client, patient_token, doctor_token):
    """The same patient cannot hold two serials for one schedule."""
    import uuid
    from datetime import datetime, timedelta, timezone

    doc = client.get("/api/doctor/profile", headers=auth(doctor_token)).json()
    date = (datetime.now(timezone.utc) + timedelta(days=1400 + uuid.uuid4().int % 1000)).date().isoformat()
    sid = client.post("/api/appointments/schedules",
                      json={"doctor_id": doc["id"], "date": date, "total_serials": 5},
                      headers=auth(doctor_token)).json()["id"]
    tag = uuid.uuid4().hex[:6]
    p = client.post("/api/patients", json={"full_name": f"Dup {tag}", "relation": "self"}, headers=auth(patient_token)).json()
    first = client.post("/api/appointments/book", json={"schedule_id": sid, "patient_id": p["id"]}, headers=auth(patient_token))
    assert first.status_code == 200
    second = client.post("/api/appointments/book", json={"schedule_id": sid, "patient_id": p["id"]}, headers=auth(patient_token))
    assert second.status_code == 400


def test_interpreter_match(client):
    r = client.get("/api/interpreter/match", params={"name": "celofen"})
    assert r.status_code == 200
    assert r.json()["candidates"]


def test_interpreter_capabilities(client):
    r = client.get("/api/interpreter/capabilities")
    assert r.status_code == 200
    assert r.json()["typed_fallback"] is True


def test_reminder_flow(client, patient_token):
    p = client.get("/api/patients", headers=auth(patient_token)).json()["results"][0]
    r = client.post("/api/reminders", json={"patient_id": p["id"], "title": "Test reminder",
                                            "items": [{"medicine_name": "Celofen", "times": ["08:00", "20:00"]}]},
                    headers=auth(patient_token))
    assert r.status_code == 200
    lst = client.get("/api/reminders", params={"patient_id": p["id"]}, headers=auth(patient_token))
    assert lst.status_code == 200
    assert len(lst.json()["results"]) >= 1


def test_access_code_flow(client, doctor_token):
    pts = client.get("/api/doctor/patients", headers=auth(doctor_token)).json()["results"]
    pid = pts[0]["id"]
    c = client.post("/api/doctor/access-codes", json={"patient_id": pid}, headers=auth(doctor_token))
    assert c.status_code == 200
    code = c.json()["code"]
    r = client.post("/api/doctor/access-codes/redeem", json={"patient_id": pid, "code": code}, headers=auth(doctor_token))
    assert r.status_code == 200
    bad = client.post("/api/doctor/access-codes/redeem", json={"patient_id": pid, "code": "000000"}, headers=auth(doctor_token))
    assert bad.status_code == 400
