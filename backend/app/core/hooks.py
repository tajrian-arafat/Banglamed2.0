"""Hook registry: modules extend each other without importing each other."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

_registry: dict[str, list[Callable[..., Any]]] = defaultdict(list)


def register(hook_name: str, fn: Callable[..., Any]) -> None:
    _registry[hook_name].append(fn)


def emit(hook_name: str, **kwargs: Any) -> list[Any]:
    results = []
    for fn in _registry.get(hook_name, []):
        try:
            results.append(fn(**kwargs))
        except Exception as exc:  # a broken optional module must not break the app
            results.append({"error": str(exc)})
    return results


def clear() -> None:
    _registry.clear()
