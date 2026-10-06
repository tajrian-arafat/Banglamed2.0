"""Uniform error envelope: {code, message, details}."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details})


def not_found(message: str = "Resource not found") -> AppError:
    return AppError("not_found", message, status.HTTP_404_NOT_FOUND)


def forbidden(message: str = "Not permitted") -> AppError:
    return AppError("forbidden", message, status.HTTP_403_FORBIDDEN)


def unauthorized(message: str = "Authentication required") -> AppError:
    return AppError("unauthorized", message, status.HTTP_401_UNAUTHORIZED)


def bad_request(message: str, details: Any = None) -> AppError:
    return AppError("bad_request", message, status.HTTP_400_BAD_REQUEST, details)
