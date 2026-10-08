"""Configuration loading: .env + config/*.json."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]  # repo root
CONFIG_DIR = BASE_DIR / "config"

# Where the SQLite catalog lives. Defaults to <repo>/data, but honours
# BANGLAMED_DATA_DIR so a host that offers a persistent mount (e.g. Render's
# /var/data) can point the database at disk that survives a redeploy. Without a
# mount the default keeps the previous behaviour: rebuild on a cold start.
DATA_DIR = Path(os.environ.get("BANGLAMED_DATA_DIR") or (BASE_DIR / "data"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "BanglaMed"
    env: str = "development"
    secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    database_url: str = f"sqlite:///{DATA_DIR / 'banglamed.db'}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ocr_provider: str = "null"
    gemini_api_key: str = ""
    map_provider: str = "overpass"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    max_upload_mb: int = 8
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    rate_limit_per_minute: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in ("production", "prod")

    def assert_production_secrets(self) -> None:
        """Refuse to boot in production with the shipped development secret.

        ``SECRET_KEY`` is what signs JWTs and the prescription seal, so a default
        value in production would let anyone forge a token. Failing loudly at
        startup is the only safe behaviour — a silently insecure deployment is
        worse than one that does not come up.
        """
        if self.is_production and self.secret_key in ("", "dev-insecure-change-me"):
            raise RuntimeError(
                "SECRET_KEY must be set to a strong random value when ENV=production. "
                "Refusing to start with the development default."
            )
        if self.is_production and len(self.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_json_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def modules_config() -> dict[str, bool]:
    return load_json_config("modules.config.json")


def safety_rules() -> dict[str, Any]:
    return load_json_config("safety_rules.json")


def cost_rules() -> dict[str, Any]:
    return load_json_config("cost_rules.json")


def matching_config() -> dict[str, Any]:
    return load_json_config("matching.json")


def access_rules() -> dict[str, Any]:
    return load_json_config("access_rules.json")
