"""Audit trail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.security import Principal
from ...db.session import get_db
from ...models import AuditEvent
from ...schemas import AuditEventOut, AuditList
from ...services import case_service
from ..deps import PageParams, get_principal

router = APIRouter(tags=["audit"])


@router.get("/cases/{case_id}/audit", response_model=AuditList)
def list_case_audit(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    action: str | None = Query(default=None, max_length=80),
    page: PageParams = Depends(PageParams.depends),
) -> AuditList:
    case_service.get_case_or_404(db, principal, case_id)
    conditions = [AuditEvent.case_id == case_id, AuditEvent.org_id == principal.org_id]
    if action:
        conditions.append(AuditEvent.action == action)
    total = db.scalar(select(func.count(AuditEvent.id)).where(*conditions)) or 0
    events = db.scalars(
        select(AuditEvent).where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(page.limit).offset(page.offset)
    ).all()
    return AuditList(
        items=[AuditEventOut.model_validate(e) for e in events],
        meta={"total": total, "limit": page.limit, "offset": page.offset},
    )
