"""Report endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.errors import Conflict
from ...core.security import Principal
from ...db.session import get_db
from ...schemas import ReportOut
from ...services import audit_service, case_service, reporting
from ..deps import get_principal, require_inspector

router = APIRouter(prefix="/cases/{case_id}/report", tags=["reports"])


@router.post("", status_code=201, response_model=ReportOut)
def generate_case_report(case_id: str, db: Session = Depends(get_db),
                         principal: Principal = Depends(require_inspector)) -> ReportOut:
    case = case_service.get_case_or_404(db, principal, case_id)
    report = reporting.generate_report(db, principal, case)
    audit_service.record(
        db, action="report_generated", org_id=principal.org_id, case_id=case.id,
        actor=principal, detail={"report_id": report.id, "score": report.score},
    )
    payload = reporting.report_payload(report)
    return ReportOut(
        id=report.id, case_id=report.case_id, score=report.score,
        risk_level=report.risk_level, created_at=report.created_at, payload=payload,
    )


@router.get("", response_model=ReportOut)
def get_latest_report(case_id: str, db: Session = Depends(get_db),
                      principal: Principal = Depends(get_principal)) -> ReportOut:
    case = case_service.get_case_or_404(db, principal, case_id)
    report = reporting.latest_report(db, case)
    if report is None:
        raise Conflict("No report has been generated for this case yet.")
    payload = reporting.report_payload(report)
    return ReportOut(
        id=report.id, case_id=report.case_id, score=report.score,
        risk_level=report.risk_level, created_at=report.created_at, payload=payload,
    )


def require_inspector_principal():  # thin alias to keep import surface small
    from ..deps import require_inspector

    return require_inspector
