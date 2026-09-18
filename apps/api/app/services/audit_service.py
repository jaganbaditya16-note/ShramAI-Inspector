"""Append-only audit trail writer.

Audit events never contain document text — only ids, filenames, sizes,
statuses and decision metadata — so the trail is safe to export and review.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..core.logging import request_id_var
from ..core.security import Principal
from ..models import AuditEvent


def record(
    db: Session,
    *,
    action: str,
    org_id: str | None,
    case_id: str | None = None,
    actor: Principal | None = None,
    detail: dict[str, Any] | None = None,
    commit: bool = True,
) -> AuditEvent:
    safe_detail = detail or {}
    event = AuditEvent(
        org_id=org_id,
        case_id=case_id,
        actor_user_id=actor.user_id if actor else None,
        actor_label=actor.display_name if actor else "system",
        action=action,
        detail=json.loads(json.dumps(safe_detail, ensure_ascii=False, default=str)),
        request_id=request_id_var.get(),
    )
    db.add(event)
    if commit:
        db.commit()
    return event
