"""Module registry: config-driven attach/detach with dependency validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import modules_config


@dataclass
class ModuleSpec:
    id: str
    name: str
    requires: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)
    nav: list[dict[str, Any]] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    hooks_provided: list[str] = field(default_factory=list)
    hooks_consumed: list[str] = field(default_factory=list)


_REGISTRY: dict[str, ModuleSpec] = {}


def register_module(spec: ModuleSpec) -> ModuleSpec:
    _REGISTRY[spec.id] = spec
    return spec


def all_modules() -> dict[str, ModuleSpec]:
    return dict(_REGISTRY)


def is_enabled(module_id: str) -> bool:
    return bool(modules_config().get(module_id, False))


def enabled_modules() -> list[ModuleSpec]:
    return [m for m in _REGISTRY.values() if is_enabled(m.id)]


def validate_dependencies() -> list[str]:
    """Return a list of problems; empty means the graph is valid."""
    cfg = modules_config()
    problems: list[str] = []
    for mid, spec in _REGISTRY.items():
        if not cfg.get(mid, False):
            continue
        for dep in spec.requires:
            if not cfg.get(dep, False):
                problems.append(f"Module '{mid}' requires '{dep}' which is disabled.")
    return problems


def module_manifest() -> dict[str, Any]:
    """Payload for GET /api/modules — the frontend builds itself from this."""
    mods = []
    for spec in _REGISTRY.values():
        mods.append(
            {
                "id": spec.id,
                "name": spec.name,
                "enabled": is_enabled(spec.id),
                "requires": spec.requires,
                "optional": spec.optional,
                "nav": spec.nav,
                "permissions": spec.permissions,
            }
        )
    return {"modules": mods, "problems": validate_dependencies()}
