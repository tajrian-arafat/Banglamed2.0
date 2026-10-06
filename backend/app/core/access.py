from __future__ import annotations

from .config import load_json_config


def access_rules() -> dict:
    return load_json_config("access_rules.json")
