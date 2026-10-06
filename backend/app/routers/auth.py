"""M1 Auth & accounts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..core.audit import log_action
from ..core.config import get_settings
from ..core.db import get_db
from ..core.errors import AppError, bad_request, unauthorized
from ..core.ratelimit import check_rate_limit
from ..core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from ..deps import get_current_user
from ..schemas import LoginIn, MeOut, RegisterIn, TokenOut
from ..services.ids import patient_code

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if not check_rate_limit(f"register:{request.client.host if request.client else 'x'}", limit=20):
        raise AppError("rate_limited", "Too many attempts, slow down.", 429)
    if payload.account_type not in ("personal", "family"):
        raise bad_request("account_type must be personal or family")
    if db.scalar(select(M.User).where(M.User.username == payload.username)):
        raise bad_request("Username already taken")
    user = M.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="patient",
        account_type=payload.account_type,
        full_name=payload.full_name,
        email=payload.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    # create the primary patient profile
    n = db.query(M.Patient).count() + 1
    db.add(M.Patient(patient_code=patient_code(n), account_id=user.id, full_name=payload.full_name, relation="self"))
    db.commit()
    log_action(db, user.id, "register", "user", user.id, {"role": "patient"})
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
    )


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "x"
    if not check_rate_limit(f"login:{ip}", limit=settings.login_max_attempts * 4):
        raise AppError("rate_limited", "Too many login attempts. Try again later.", 429)
    user = db.scalar(select(M.User).where(M.User.username == payload.username))
    if not user:
        raise unauthorized("Invalid credentials")
    if user.locked_until and user.locked_until > datetime.now(timezone.utc).replace(tzinfo=None):
        raise AppError("locked", "Account temporarily locked. Try again later.", 423)
    if not verify_password(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_max_attempts:
            user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_attempts = 0
        db.commit()
        log_action(db, user.id, "login_failed", "user", user.id)
        raise unauthorized("Invalid credentials")
    if not user.is_active:
        raise unauthorized("Account disabled")
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    log_action(db, user.id, "login", "user", user.id, {"role": user.role})
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(body: dict, db: Session = Depends(get_db)):
    token = body.get("refresh_token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise unauthorized("Invalid refresh token")
    user = db.get(M.User, int(payload["sub"]))
    if not user or not user.is_active:
        raise unauthorized("Account disabled")
    return TokenOut(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id)),
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
    )


@router.get("/me", response_model=MeOut)
def me(user: M.User = Depends(get_current_user)):
    return MeOut(
        id=user.id, username=user.username, role=user.role,
        account_type=user.account_type, full_name=user.full_name, email=user.email,
    )


@router.post("/logout")
def logout(user: M.User = Depends(get_current_user), db: Session = Depends(get_db)):
    log_action(db, user.id, "logout", "user", user.id)
    return {"ok": True}
