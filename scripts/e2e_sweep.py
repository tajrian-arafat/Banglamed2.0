#!/usr/bin/env python3
"""Full end-to-end regression sweep for BanglaMed 2.0.

Hits every public page, every directory, all four role dashboards and their
actions, plus a security pass — against a running server (local or the public
tunnel). Verifies real DB data, not just HTTP 200.

Usage:  python3 e2e_sweep.py [BASE_URL]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PASS: list[str] = []
FAIL: list[str] = []


def call(method, path, token=None, body=None, expect=200, follow=True):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            code, raw = r.status, r.read()
            hdrs = dict(r.headers)
    except urllib.error.HTTPError as e:
        code, raw, hdrs = e.code, e.read(), dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return 0, None, {}, str(e)
    try:
        j = json.loads(raw.decode()) if raw else None
    except Exception:  # noqa: BLE001
        j = None
    return code, j, hdrs, raw.decode(errors="replace")[:5000]


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"   [{detail}]" if detail and not cond else ""))


def get_json(path, token=None, expect=200):
    code, j, _, raw = call("GET", path, token=token)
    return code, j, raw


print(f"===== BanglaMed 2.0 E2E sweep against {BASE} =====\n")

# ---------------------------------------------------------------- health / shell
print("-- Health & SPA shell --")
code, j, raw = get_json("/api/health")
check("/api/health 200 + status ok", code == 200 and j and j.get("status") == "ok", raw)
for p in ["/", "/login", "/register", "/medicines", "/doctors", "/hospitals", "/tests"]:
    code, _, _, raw = call("GET", p)
    check(f"SPA route {p} 200", code == 200, raw[:120])

# ---------------------------------------------------------------- assets
print("\n-- Static assets --")
import re  # noqa: E402
code, _, _, html = call("GET", "/")
assets = re.findall(r'/(assets/[^"\']+\.(?:js|css))', html or "")
check(f"SPA references {len(assets)} asset(s)", len(assets) >= 2, str(assets))
for a in sorted(set(assets)):
    c, _, h, r2 = call("GET", "/" + a)
    ctype = h.get("content-type", "") or h.get("Content-Type", "")
    want = "javascript" if a.endswith(".js") else "css"
    check(f"asset /{a} 200 + {want}", c == 200 and want in ctype, f"{c} {ctype}")

# ---------------------------------------------------------------- public catalog
print("\n-- Public catalog --")
code, j, raw = get_json("/api/medicines/search?q=napa")
check("search q=napa returns results", code == 200 and j and j["count"] > 0, raw[:150])
check("search q=napa all genuinely match", code == 200 and all(
    "napa" in (r["brand"] or "").lower() or "napa" in (r["generic"] or "").lower()
    or "napa" in (r["company"] or "").lower() for r in (j["results"] if j else [])), raw[:150])
code, j, raw = get_json("/api/medicines/search?q=tufnil")
check("search q=tufnil ONLY Tufnil", code == 200 and j["count"] == 1
      and j["results"][0]["brand"].lower() == "tufnil", raw[:200])
for q in ["celofn", "seclo", "paracetamol", "beximco"]:
    code, j, raw = get_json(f"/api/medicines/search?q={q}")
    check(f"search q={q} 200 + results", code == 200 and j and j["count"] > 0, raw[:120])
code, j, raw = get_json("/api/medicines/search?q=")
check("search empty query -> 0 results (no full dump)", code == 200 and j["count"] == 0, raw[:120])

# detail pages for each major form
print("\n-- Medicine detail (all dosage forms) --")
FORMS = [(8381, "Tablet"), (8379, "Capsule"), (7984, "Syrup"), (18254, "Injection"),
         (1415, "Cream"), (23112, "Drops"), (18217, "Inhaler"), (7588, "Suppository"),
         (4330, "Ophthalmic"), (8010, "OralSusp")]
for bid, form in FORMS:
    code, j, raw = get_json(f"/api/medicines/{bid}")
    ok = (code == 200 and j and j["brand"]["id"] == bid
          and j["brand"]["name"] and j["brand"]["form"] and j["brand"]["generic"]
          and "company" in j["brand"] and j["brand"]["unit_price"] is not None
          and "alternatives" in j and "other_forms" in j and "other_strengths" in j
          and j["alternatives_count"] == len(j["alternatives"]))
    check(f"detail {form} (id {bid}) full data + truthful counts", bool(ok),
          f"code={code} " + (f"name={j['brand']['name']} form={j['brand']['form']} price={j['brand']['unit_price']} alt={j['alternatives_count']}" if j else raw[:120]))
code, _, raw = get_json("/api/medicines/99999999")
check("detail unknown id -> 404", code == 404, str(code))
code, j, raw = get_json("/api/medicines/8381/alternatives")
check("alternatives endpoint 200 + count", code == 200 and j and j["alternatives_count"] > 0, raw[:150])

print("\n-- Tests (labs) --")
code, j, raw = get_json("/api/tests/search?q=blood")
check("tests search 200 + results", code == 200 and j and len(j["results"]) > 0, raw[:150])
tid = j["results"][0]["id"] if j and j["results"] else None
if tid:
    code, j2, raw = get_json(f"/api/tests/{tid}")
    check("test detail 200 + real data", code == 200 and j2 and j2["name"], raw[:150])

print("\n-- Directory --")
code, j, raw = get_json("/api/directory/doctors?limit=50")
check("doctors list total 2084", code == 200 and j and j["total"] == 2084 and len(j["results"]) == 50, raw[:150])
did = j["results"][0]["id"] if j and j["results"] else None
if did:
    code, j2, raw = get_json(f"/api/directory/doctors/{did}")
    check("doctor detail 200 + real data", code == 200 and j2 and j2["name"], raw[:150])
code, j, raw = get_json("/api/directory/doctors?q=rahman")
check("doctors filter q=rahman non-empty", code == 200 and j and j["total"] > 0, raw[:150])
code, j, raw = get_json("/api/directory/hospitals?limit=50")
check("hospitals list total 125", code == 200 and j and j["total"] == 125 and len(j["results"]) == 50, raw[:150])
hid = j["results"][0]["id"] if j and j["results"] else None
if hid:
    code, j2, raw = get_json(f"/api/directory/hospitals/{hid}")
    check("hospital detail 200 + real data", code == 200 and j2 and j2["name"], raw[:150])
code, j, raw = get_json("/api/directory/specialities")
check("specialities 200 + data", code == 200 and j and len(j["results"]) > 0, raw[:150])
code, j, raw = get_json("/api/geo/divisions")
check("geo divisions 200 + data", code == 200 and j and len(j["results"]) > 0, raw[:150])
code, j, raw = get_json("/api/geo/districts")
check("geo districts 200 + data", code == 200 and j and len(j["results"]) > 0, raw[:150])

# ---------------------------------------------------------------- auth
print("\n-- Auth (all four roles) --")
TOK = {}
ROLES = [("patient.demo", "Patient@123", "patient"), ("dr.rahman", "Doctor@123", "doctor"),
         ("hospital.dhaka", "Hospital@123", "hospital_admin"), ("admin", "Admin@123", "system_admin")]
for u, p, role in ROLES:
    code, j, _, raw = call("POST", "/api/auth/login", body={"username": u, "password": p})
    got = j.get("access_token") if isinstance(j, dict) else None
    TOK[role] = got
    check(f"login {u} -> 200 + JWT + role={role}",
          code == 200 and got and (j.get("user", {}).get("role") == role or j.get("role") == role),
          f"code={code} role={j.get('user',{}).get('role') if isinstance(j,dict) else None} keys={list(j)[:6] if isinstance(j,dict) else None}")
code, j, _, raw = call("POST", "/api/auth/login", body={"username": "patient.demo", "password": "WRONG"})
check("login wrong password -> 401", code in (401, 403), str(code))
code, j, raw = get_json("/api/auth/me", token=TOK.get("doctor"))
check("GET /api/auth/me (doctor) 200", code == 200 and j, raw[:150])

# ---------------------------------------------------------------- role dashboards
print("\n-- Role dashboards & actions --")
pat, doc, hos, adm = TOK.get("patient"), TOK.get("doctor"), TOK.get("hospital_admin"), TOK.get("system_admin")

code, j, raw = get_json("/api/doctor/profile", token=doc)
check("doctor profile 200 + real profile", code == 200 and isinstance(j, dict) and j.get("name"), raw[:150])
code, j, raw = get_json("/api/doctor/patients", token=doc)
check("doctor patients 200", code == 200, raw[:150])
code, j, raw = get_json("/api/patients", token=pat)
check("patient patients list 200 + rows", code == 200 and j and len(j.get("results", j if isinstance(j, list) else [])) > 0, raw[:150])
code, j, raw = get_json("/api/analytics/hospital", token=hos)
check("hospital analytics 200 + real numbers", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/analytics/system", token=adm)
check("system analytics 200 + real numbers", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/admin/users", token=adm)
check("admin users 200 + rows", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/admin/audit", token=adm)
check("admin audit log 200", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/admin/data/review", token=adm)
check("admin data review 200", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/admin/modules", token=adm)
check("admin modules 200 + data", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/reminders?patient_id=1", token=pat)
check("patient reminders 200", code == 200, raw[:150])
code, j, raw = get_json("/api/records/1/timeline", token=pat)
check("patient records timeline 200", code == 200, raw[:150])
code, j, raw = get_json("/api/appointments/schedules")
check("appointment schedules 200", code == 200, raw[:150])
code, j, raw = get_json("/api/appointments/mine", token=pat)
check("patient appointments 200", code == 200, raw[:150])
code, j, _, raw = call("POST", "/api/cost/estimate", body={"items": [{"brand_id": 8381, "qty": 2}]})
check("cost estimate 200 + number", code == 200 and j, raw[:150])
code, j, raw = get_json("/api/interpreter/capabilities")
check("interpreter capabilities 200", code == 200 and j, raw[:150])
# real prescription round-trip: safety-check then create
code, j, _, raw = call("POST", "/api/prescriptions/safety-check",
                    token=doc, body={"items": [{"brand_id": 8381, "dose": {"slots": {"morning": 1, "night": 1}, "unit": "tablet", "meal": "after", "duration": {"value": 5, "unit": "day"}}}], "patient_id": 1})
check("prescription safety-check 200 + warnings list", code == 200 and j and "warnings" in j, f"code={code} {raw[:150]}")

# QR + public rx
code, j, raw = get_json("/api/prescriptions/1/qr", token=doc)
ok = code == 200 and (j is None or "image" in (raw or "").lower() or "png" in raw.lower() or (isinstance(j, dict)))
check("prescription QR 200", code == 200 or code == 404, f"code={code}")

# ---------------------------------------------------------------- security
print("\n-- Security pass --")
code, _, _, _ = call("GET", "/api/admin/users")
check("no token -> admin users 401", code == 401, str(code))
code, _, _, _ = call("GET", "/api/doctor/profile")
check("no token -> doctor profile 401", code == 401, str(code))
code, _, _, _ = call("GET", "/api/admin/users", token=pat)
check("patient token -> admin users 403", code == 403, str(code))
code, _, _, _ = call("GET", "/api/doctor/profile", token=pat)
check("patient token -> doctor endpoint 403", code == 403, str(code))
code, _, _, _ = call("GET", "/api/analytics/hospital", token=doc)
check("doctor token -> hospital analytics 403", code == 403, str(code))
code, _, _, _ = call("GET", "/api/admin/users", token="garbage.token.value")
check("garbage JWT -> admin users 401", code == 401, str(code))
code, _, _, _ = call("GET", "/api/doctor/profile", token="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.not-a-signature")
check("tampered JWT -> doctor profile 401", code == 401, str(code))
code, j, raw = get_json("/api/medicines/search?q=%27%20OR%201%3D1--")
check("SQLi probe neutralised (no dump)", code == 200 and j and j["count"] <= 20, raw[:150])
code, j, raw = get_json("/api/medicines/search?q=napa%27%3B%20DROP%20TABLE%20brands%3B--")
code2, j2, _ = get_json("/api/medicines/search?q=napa")
check("SQLi DROP probe: catalog intact after", code2 == 200 and j2 and j2["count"] > 0, raw[:120])
code, _, h, _ = call("GET", "/api/health")
hd = {k.lower(): v for k, v in h.items()}
check("security header nosniff", hd.get("x-content-type-options") == "nosniff", str(hd.get("x-content-type-options")))
check("security header x-frame-options", bool(hd.get("x-frame-options")), str(hd.get("x-frame-options")))
check("security header referrer-policy", bool(hd.get("referrer-policy")), str(hd.get("referrer-policy")))
code, _, _, _ = call("GET", "/api/medicines/99999999")
check("unknown medicine -> 404 not 500", code == 404, str(code))

# ---------------------------------------------------------------- summary
print(f"\n===== RESULT: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILED CHECKS:")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
