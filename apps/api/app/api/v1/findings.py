"""Finding endpoints: listing with filters and the human-review transition."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case as sa_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.security import Principal
from ...db.helpers import utcnow
from ...db.session import get_db
from ...models import Finding
from ...schemas import FindingList, FindingOut, FindingReview
from ...services import audit_service, case_service
from ..deps import PageParams, get_principal, require_inspector

router = APIRouter(tags=["findings"])

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@router.get("/cases/{case_id}/findings", response_model=FindingList)
def list_findings(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    status: str | None = Query(default=None, pattern="^(needs_review|confirmed|dismissed)$"),
    severity: str | None = Query(default=None, pattern="^(low|medium|high)$"),
    origin: str | None = Query(default=None, pattern="^(rule|ai)$"),
    document_id: str | None = Query(default=None, max_length=36),
    sort: str = Query(default="-created_at", pattern="^-?(created_at|severity|confidence)$"),
    page: PageParams = Depends(PageParams.depends),
) -> FindingList:
    case_service.get_case_or_404(db, principal, case_id)
    conditions = [Finding.case_id == case_id, Finding.org_id == principal.org_id]
    if status:
        conditions.append(Finding.status == status)
    if severity:
        conditions.append(Finding.severity == severity)
    if origin:
        conditions.append(Finding.origin == origin)
    if document_id:
        conditions.append(Finding.document_id == document_id)

    total = db.scalar(select(func.count(Finding.id)).where(*conditions)) or 0
    stmt = select(Finding).where(*conditions)
    if sort == "severity":
        stmt = stmt.order_by(
            sa_case((Finding.severity == "high", 0), (Finding.severity == "medium", 1), else_=2),
            Finding.created_at.desc(),
        )
    elif sort == "-severity":
        stmt = stmt.order_by(
            sa_case((Finding.severity == "low", 0), (Finding.severity == "medium", 1), else_=2),
            Finding.created_at.desc(),
        )
    elif sort == "confidence":
        stmt = stmt.order_by(Finding.confidence.asc(), Finding.created_at.desc())
    elif sort == "-confidence":
        stmt = stmt.order_by(Finding.confidence.desc(), Finding.created_at.desc())
    elif sort == "created_at":
        stmt = stmt.order_by(Finding.created_at.asc())
    else:
        stmt = stmt.order_by(Finding.created_at.desc())
    findings = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return FindingList(
        items=[FindingOut.model_validate(f).model_dump(by_alias=True) for f in findings],
        meta={"total": total, "limit": page.limit, "offset": page.offset},
    )


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def review_finding(finding_id: str, payload: FindingReview, db: Session = Depends(get_db),
                   principal: Principal = Depends(require_inspector)) -> FindingOut:
    finding = db.get(Finding, finding_id)
    if finding is None or finding.org_id != principal.org_id:
        from ...core.errors import NotFound

        raise NotFound("Finding not found.")
    if finding.status == payload.status and (payload.note is None or payload.note == finding.review_note):
        return FindingOut.model_validate(finding)

    finding.status = payload.status
    finding.review_note = payload.note
    if payload.status == "needs_review":
        finding.reviewed_by = None
        finding.reviewed_at = None
    else:
        finding.reviewed_by = principal.user_id
        finding.reviewed_at = utcnow()
    db.commit()
    audit_service.record(
        db, action="finding_reviewed", org_id=principal.org_id, case_id=finding.case_id,
        actor=principal,
        detail={
            "finding_id": finding.id,
            "rule_id": finding.rule_id,
            "origin": finding.origin,
            "status": finding.status,
        },
    )
    return FindingOut.model_validate(finding)
