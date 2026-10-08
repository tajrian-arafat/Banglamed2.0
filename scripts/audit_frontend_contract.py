#!/usr/bin/env python3
"""Frontend-contract audit: exercise EVERY path the built SPA calls.

The paths below are extracted from the production bundle, so this is the real
client/server contract rather than a hand-written guess. Each row declares the
roles allowed to reach it; anything else must be refused.

Usage:  python3 scripts/audit_frontend_contract.py [base_url]
Exit code is non-zero when any row does not match its expectation.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

CREDS = {
    "anon": None,
    "patient": ("patient.demo", "Patient@123"),
    "doctor": ("dr.rahman", "Doctor@123"),
    "hospital": ("hospital.dhaka", "Hospital@123"),
    "admin": ("admin", "Admin@123"),
}

CONTRACT: list[tuple[str, str, dict | None, dict[str, int]]] = [
    ("/api/auth/login", "POST", {"username": "patient.demo", "password": "Patient@123"},
     {"anon": 200}),
    ("/api/directory/specialities", "GET", None, {"anon": 200}),
    ("/api/medicines/search?q=napa", "GET", None, {"anon": 200}),
    ("/api/directory/doctors?limit=2", "GET", None, {"anon": 200}),
    ("/api/directory/hospitals?limit=2", "GET", None, {"anon": 200}),
    ("/api/tests/search?limit=2", "GET", None, {"anon": 200}),
    ("/api/medicines/1083", "GET", None, {"anon": 200}),
    ("/api/auth/me", "GET", None,
     {"patient": 200, "doctor": 200, "hospital": 200, "admin": 200, "anon": 401}),
    ("/api/patients", "GET", None,
     {"patient": 200, "doctor": 200, "hospital": 200, "admin": 200, "anon": 401}),
    ("/api/doctor/profile", "GET", None,
     {"doctor": 200, "patient": 403, "hospital": 403, "admin": 403, "anon": 401}),
    ("/api/doctor/patients", "GET", None,
     {"doctor": 200, "patient": 403, "hospital": 403, "anon": 401}),
    ("/api/appointments/mine", "GET", None,
     {"patient": 200, "doctor": 200, "hospital": 200, "anon": 401}),
    ("/api/appointments/schedules", "GET", None,
     {"anon": 200, "patient": 200, "doctor": 200, "hospital": 200}),
    ("/api/reminders?patient_id=1", "GET", None,
     {"patient": 200, "anon": 401}),
    ("/api/prescriptions/safety-check", "POST", {}, {"doctor": 422, "anon": 401}),
    ("/api/analytics/hospital", "GET", None,
     {"hospital": 200, "doctor": 403, "patient": 403, "anon": 401}),
    ("/api/analytics/system", "GET", None,
     {"admin": 200, "doctor": 403, "patient": 403, "anon": 401}),
    ("/api/admin/users", "GET", None,
     {"admin": 200, "doctor": 403, "patient": 403, "hospital": 403, "anon": 401}),
    ("/api/admin/modules", "GET", None, {"admin": 200, "anon": 401}),
    ("/api/geo/districts", "GET", None, {"anon": 200}),
]


def call(path: str, method: str, body: dict | None, token: str | None) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=25) as fh:
            return fh.status, fh.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    tokens: dict[str, str | None] = {"anon": None}
    print("=== obtaining role tokens ===")
    for role, cred in CREDS.items():
        if cred is None:
            continue
        data = json.dumps({"username": cred[0], "password": cred[1]}).encode()
        req = urllib.request.Request(BASE + "/api/auth/login", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=25) as fh:
            payload = json.loads(fh.read().decode())
        tokens[role] = payload.get("access_token")
        print(f"  {role:<10} role_field={payload.get('role')!r} name={payload.get('full_name')!r}")

    print(f"\n{'path':<40} {'method':<6} " + " ".join(f"{r:<9}" for r in CREDS) + " verdict")
    print("-" * 108)
    failures: list[str] = []
    for path, method, body, expect in CONTRACT:
        cells = []
        row_ok = True
        for role in CREDS:
            want = expect.get(role)
            if want is None:
                cells.append("     -   ")
                continue
            got, _ = call(path, method, body, tokens[role])
            ok = got == want
            row_ok &= ok
            cells.append(f"{got:<4}{'ok ' if ok else 'BAD'}")
            if not ok:
                failures.append(f"{path} [{role}] expected {want} got {got}")
        short = path if len(path) <= 39 else path[:36] + "..."
        print(f"{short:<40} {method:<6} " + " ".join(f"{c:<9}" for c in cells) + ("PASS" if row_ok else "FAIL"))

    print("-" * 108)
    print(f"rows: {len(CONTRACT)}   assertions: {sum(len(e) for _, _, _, e in CONTRACT)}   failures: {len(failures)}")
    for f in failures:
        print("  !", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
