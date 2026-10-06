"""FastAPI dependencies: current user, role guards, object-level checks."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .core.db import get_db
from .core.errors import forbidden, unauthorized
from .core.security import decode_token
from . import models as M


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("access_token")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> M.User:
    token = _extract_token(request)
    if not token:
        raise unauthorized()
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise unauthorized("Invalid or expired token")
    user = db.get(M.User, int(payload["sub"]))
    if not user or not user.is_active:
        raise unauthorized("Account disabled or missing")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> M.User | None:
    try:
        return get_current_user(request, db)
    except Exception:
        return None


def require_role(*roles: str) -> Callable[..., M.User]:
    def _dep(user: M.User = Depends(get_current_user)) -> M.User:
        if user.role not in roles:
            raise forbidden(f"Requires role: {', '.join(roles)}")
        return user

    return _dep


def require_any_role(*roles: str) -> Callable[..., M.User]:
    return require_role(*roles)
