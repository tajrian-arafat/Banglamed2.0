"""Human-readable, non-guessable identifiers."""
from __future__ import annotations

import secrets
import string

ALPHABET = string.ascii_uppercase + string.digits


def _rand(n: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def doc_code(n: int) -> str:
    return f"DOC-BD-{n:06d}"


def patient_code(n: int) -> str:
    return f"PAT-BD-{n:06d}"


def rx_code(year: int) -> str:
    return f"RX-BD-{year}-{_rand(8)}"


def apt_code(year: int) -> str:
    return f"APT-BD-{year}-{_rand(6)}"


def med_code(n: int) -> str:
    return f"MED-BD-{n:05d}"


def public_token() -> str:
    return secrets.token_urlsafe(24)
