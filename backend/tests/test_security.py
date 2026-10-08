"""Signature tamper detection + password hashing."""
from __future__ import annotations

from app.core.security import hash_password, sign_content, verify_password, verify_signature


def test_password_roundtrip():
    h = hash_password("S3cret!pass")
    assert verify_password("S3cret!pass", h)
    assert not verify_password("wrong", h)


def test_long_password_ok():
    h = hash_password("x" * 200)
    assert verify_password("x" * 200, h)


def test_signature_valid():
    payload = {"rx_code": "RX-1", "items": [{"name": "A"}]}
    ch, sig = sign_content(payload)
    assert verify_signature(payload, ch, sig)


def test_signature_tamper_detected():
    payload = {"rx_code": "RX-1", "items": [{"name": "A"}]}
    ch, sig = sign_content(payload)
    tampered = {"rx_code": "RX-1", "items": [{"name": "B"}]}
    assert not verify_signature(tampered, ch, sig)


def test_signature_order_independent():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert sign_content(a) == sign_content(b)
