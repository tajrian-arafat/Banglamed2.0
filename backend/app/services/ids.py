"""Human-readable, non-guessable identifiers.

Runtime behaviour is unchanged: codes and tokens come from ``secrets``, so a
prescription written by a doctor is unguessable.

During a *deterministic catalog build* (BANGLAMED_BUILD_EPOCH set — see
models.build_epoch) the generators switch to a deterministic hash instead. The
build re-runs from the committed source data on every deploy on hosts without a
persistent disk, and the seeded demo history would otherwise mint different
``rx_code`` / ``public_token`` values on every rebuild. Deriving them from a
caller-supplied **key** keeps them unguessable-looking yet identical across
builds, which is what makes the state fingerprint stable (scripts/
state_fingerprint.py) and the "database unchanged across redeploys" guarantee
checkable.

The key must be unique per row. An earlier revision derived determinism from a
per-process counter instead, which silently broke: each build script is its own
process, so every script restarted the counter at 1 and ``seed_demo_accounts``
and ``seed_demo_history`` minted the *same* first token — surfacing as
"UNIQUE constraint failed: prescriptions.public_token". A caller-owned key cannot
collide that way.
"""
from __future__ import annotations

import base64
import hashlib
import itertools
import os
import secrets
import string

ALPHABET = string.ascii_uppercase + string.digits

#: Set by scripts/render_pipeline.sh for the duration of a catalog build.
BUILD_EPOCH_ENV = "BANGLAMED_BUILD_EPOCH"

_fallback = itertools.count(1)


def _deterministic_mode() -> bool:
    return bool(os.environ.get(BUILD_EPOCH_ENV))


def _det(*parts: object, n: int) -> str:
    """n hex characters derived from a stable key (uppercase)."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest().upper()[:n]


def _rand(n: int = 8, key: object | None = None) -> str:
    """n random characters from A-Z0-9 (deterministic from ``key`` in a build)."""
    if _deterministic_mode():
        if key is None:
            key = f"fallback-{next(_fallback)}"
        return _det("banglamed-id", key, n=n)
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def doc_code(n: int) -> str:
    return f"DOC-BD-{n:06d}"


def patient_code(n: int) -> str:
    return f"PAT-BD-{n:06d}"


def rx_code(year: int, key: object | None = None) -> str:
    """Prescription number. Pass a stable, row-unique ``key`` during a build."""
    return f"RX-BD-{year}-{_rand(8, key=key)}"


def apt_code(year: int, key: object | None = None) -> str:
    return f"APT-BD-{year}-{_rand(6, key=key)}"


def med_code(n: int) -> str:
    return f"MED-BD-{n:05d}"


def public_token(key: object | None = None) -> str:
    """URL-safe token. 24 bytes of entropy at runtime; deterministic from ``key``
    in a build. ``key`` MUST be unique per row when deterministic mode is on."""
    if _deterministic_mode():
        if key is None:
            key = f"fallback-{next(_fallback)}"
        digest = hashlib.sha256(f"banglamed-token|{key}".encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:24]
    return secrets.token_urlsafe(24)
