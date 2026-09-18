"""Organisation dashboard aggregates (SQL-computed, no full-table loads)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.security import Principal
from ...db.session import get_db
from ...models import AuditEvent, Case, Document, Finding, ModelRun
from ...schemas import AuditEventOut, DashboardSummary
from ..deps import get_principal

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db),
                      principal: Principal = Depends(get_principal)) -> DashboardSummary:
    org_id = principal.org_id

    cases_by_status_rows = db.execute(
        select(Case.status, func.count(Case.id))
        .where(Case.org_id == org_id, Case.deleted_at.is_(None))
        .group_by(Case.status)
    ).all()
    cases_by_status = {row[0]: row[1] for row in cases_by_status_rows}

    documents_total = db.scalar(
        select(func.count(Document.id)).where(Document.org_id == org_id)
    ) or 0
    documents_failed = db.scalar(
        select(func.count(Document.id)).where(
            Document.org_id == org_id, Document.status == "failed"
        )
    ) or 0

    findings_by_status_rows = db.execute(
        select(Finding.status, func.count(Finding.id))
        .where(Finding.org_id == org_id)
        .group_by(Finding.status)
    ).all()
    findings_by_status = {row[0]: row[1] for row in findings_by_status_rows}

    findings_by_severity_rows = db.execute(
        select(Finding.severity, func.count(Finding.id))
        .where(Finding.org_id == org_id, Finding.status != "dismissed")
        .group_by(Finding.severity)
    ).all()
    findings_by_severity = {row[0]: row[1] for row in findings_by_severity_rows}

    ai_runs_total = db.scalar(
        select(func.count(ModelRun.id)).where(ModelRun.org_id == org_id)
    ) or 0

    recent = db.scalars(
        select(AuditEvent).where(AuditEvent.org_id == org_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(8)
    ).all()

    return DashboardSummary(
        cases_total=sum(cases_by_status.values()),
        cases_by_status=cases_by_status,
        documents_total=documents_total,
        documents_failed=documents_failed,
        findings_total=sum(findings_by_status.values()),
        findings_by_status=findings_by_status,
        findings_by_severity=findings_by_severity,
        ai_runs_total=ai_runs_total,
        recent_activity=[AuditEventOut.model_validate(e) for e in recent],
    )
