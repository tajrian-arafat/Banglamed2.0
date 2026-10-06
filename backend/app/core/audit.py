"""Audit logging helper. Patient identifiers are masked in log output."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("banglamed.audit")


def mask(value: str | None) -> str:
    if not value:
        return ""
    s = str(value)
    if len(s) <= 2:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]


def log_action(
    db: Session,
    actor_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    from ..models import AuditLog

    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        meta_json=json.dumps(meta or {}, ensure_ascii=False),
    )
    db.add(entry)
    db.commit()
    logger.info("audit action=%s entity=%s entity_id=%s actor=%s", action, entity, mask(entity_id), actor_id)
