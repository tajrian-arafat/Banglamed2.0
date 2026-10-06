"""BanglaMed FastAPI application: module registration, middleware, error envelope, static SPA."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import get_settings
from .core.db import init_db
from .core.modules import ModuleSpec, module_manifest, register_module, validate_dependencies
from .routers import (
    admin,
    analytics,
    appointments,
    auth,
    catalog,
    cost,
    doctor_workspace,
    interpreter,
    patients,
    prescriptions,
    records,
    reminders,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

# ---- module registry (SPEC 3.2) -------------------------------------------
register_module(ModuleSpec("core", "Core", nav=[], permissions=[]))
register_module(ModuleSpec("auth", "Auth & Accounts", requires=["core"], permissions=["auth"]))
register_module(ModuleSpec("catalog", "Medicine Catalog", requires=["core"], permissions=["catalog.read"],
                           nav=[{"label": "Medicines", "path": "/medicines", "roles": ["public", "patient", "doctor", "hospital_admin", "system_admin"]}]))
register_module(ModuleSpec("medicine_info", "Medicine Info", requires=["catalog"], permissions=["catalog.read"]))
register_module(ModuleSpec("tests", "Tests & Prices", requires=["core"], permissions=["tests.read"],
                           nav=[{"label": "Tests", "path": "/tests", "roles": ["public", "patient", "doctor", "hospital_admin", "system_admin"]}]))
register_module(ModuleSpec("prescriptions", "Prescriptions", requires=["catalog", "auth"], permissions=["rx.write"],
                           nav=[{"label": "Prescriptions", "path": "/doctor/prescribe", "roles": ["doctor", "system_admin"]}]))
register_module(ModuleSpec("safety", "Safety Engine", requires=["prescriptions"], permissions=["rx.write"]))
register_module(ModuleSpec("records", "Patient Records", requires=["auth"], permissions=["records.read"],
                           nav=[{"label": "My Records", "path": "/patient/history", "roles": ["patient"]}]))
register_module(ModuleSpec("interpreter", "Rx Interpreter", requires=["records"], permissions=["records.read"]))
register_module(ModuleSpec("cost", "Cost Calculator", requires=["catalog"], permissions=["cost.read"]))
register_module(ModuleSpec("reminders", "Reminders", requires=["auth"], permissions=["reminders.write"],
                           nav=[{"label": "Reminders", "path": "/patient/reminders", "roles": ["patient"]}]))
register_module(ModuleSpec("appointments", "Appointments", requires=["auth"], permissions=["appointments.write"],
                           nav=[{"label": "Appointments", "path": "/patient/appointments", "roles": ["patient"]}]))
register_module(ModuleSpec("directory", "Doctor Directory", requires=["core"], permissions=["directory.read"],
                           nav=[{"label": "Find a Doctor", "path": "/doctors", "roles": ["public", "patient", "doctor", "hospital_admin", "system_admin"]}]))
register_module(ModuleSpec("facilities", "Facilities", requires=["directory"], permissions=["directory.read"],
                           nav=[{"label": "Hospitals", "path": "/hospitals", "roles": ["public", "patient", "doctor", "hospital_admin", "system_admin"]}]))
register_module(ModuleSpec("doctor_workspace", "Doctor Workspace", requires=["prescriptions", "records"], permissions=["rx.write"],
                           nav=[{"label": "My Patients", "path": "/doctor/patients", "roles": ["doctor"]}]))
register_module(ModuleSpec("hospital_analytics", "Hospital Analytics", requires=["prescriptions"], permissions=["analytics.read"],
                           nav=[{"label": "Analytics", "path": "/hospital/analytics", "roles": ["hospital_admin", "system_admin"]}]))
register_module(ModuleSpec("admin", "System Admin", requires=["core"], permissions=["admin"],
                           nav=[{"label": "Admin", "path": "/admin", "roles": ["system_admin"]}]))

app = FastAPI(title="BanglaMed API", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"code": "error", "message": str(detail), "details": None})


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "validation_error", "message": "Invalid request", "details": exc.errors()})


@app.on_event("startup")
def _startup() -> None:
    init_db()
    problems = validate_dependencies()
    if problems:
        logging.getLogger("banglamed").warning("Module dependency problems: %s", problems)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": "2.0.0", "env": settings.env}


@app.get("/api/modules")
def modules_public():
    return module_manifest()


for r in (auth, catalog, patients, prescriptions, cost, records, interpreter, reminders, appointments, doctor_workspace, analytics, admin):
    app.include_router(r.router)

# ---- serve the built SPA (if present) -------------------------------------
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"code": "not_found", "message": "No such API route"})
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
