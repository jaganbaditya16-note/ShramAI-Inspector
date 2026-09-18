"""Case endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.security import Principal
from ...db.session import get_db
from ...models import Case
from ...schemas import CaseCreate, CaseList, CaseOut, CaseUpdate
from ...services import audit_service, case_service
from ..deps import PageParams, get_principal, require_inspector

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CaseList)
def list_cases(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    status: str | None = Query(default=None, pattern="^(draft|in_review|closed)$"),
    search: str | None = Query(default=None, max_length=100),
    page: PageParams = Depends(PageParams.depends),
) -> CaseList:
    conditions = [Case.org_id == principal.org_id, Case.deleted_at.is_(None)]
    if status:
        conditions.append(Case.status == status)
    if search:
        conditions.append(Case.title.ilike(f"%{search}%"))
    total = db.scalar(select(func.count(Case.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Case)
        .where(*conditions)
        .order_by(Case.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    doc_counts, finding_counts = case_service.case_counts(db, [c.id for c in rows])
    items = []
    for case in rows:
        item = CaseOut.model_validate(case)
        items.append(
            {
                **item.model_dump(),
                "document_count": doc_counts.get(case.id, 0),
                "finding_count": finding_counts.get(case.id, 0),
            }
        )
    return CaseList(items=items, meta={"total": total, "limit": page.limit, "offset": page.offset})


@router.post("", status_code=201)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_inspector),
) -> dict:
    case = case_service.create_case(
        db, principal,
        title=payload.title.strip(),
        establishment_name=payload.establishment_name.strip(),
        establishment_reference=(payload.establishment_reference or "").strip() or None,
        notes=payload.notes.strip(),
    )
    audit_service.record(
        db, action="case_created", org_id=principal.org_id, case_id=case.id,
        actor=principal, detail={"title": case.title, "code": case.display_code},
    )
    return {**CaseOut.model_validate(case).model_dump(), "document_count": 0, "finding_count": 0}


@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db),
             principal: Principal = Depends(get_principal)) -> dict:
    case = case_service.get_case_or_404(db, principal, case_id)
    doc_counts, finding_counts = case_service.case_counts(db, [case.id])
    return {
        **CaseOut.model_validate(case).model_dump(),
        "document_count": doc_counts.get(case.id, 0),
        "finding_count": finding_counts.get(case.id, 0),
    }


@router.patch("/{case_id}")
def update_case(case_id: str, payload: CaseUpdate, db: Session = Depends(get_db),
                principal: Principal = Depends(require_inspector)) -> dict:
    case = case_service.get_case_or_404(db, principal, case_id)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        case_service.validate_status_transition(case.status, changes["status"])
    case = case_service.update_case(db, principal, case, changes)
    audit_service.record(
        db, action="case_updated", org_id=principal.org_id, case_id=case.id,
        actor=principal, detail={"fields": sorted(changes.keys())},
    )
    doc_counts, finding_counts = case_service.case_counts(db, [case.id])
    return {
        **CaseOut.model_validate(case).model_dump(),
        "document_count": doc_counts.get(case.id, 0),
        "finding_count": finding_counts.get(case.id, 0),
    }


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str, db: Session = Depends(get_db),
                principal: Principal = Depends(require_inspector)) -> Response:
    case = case_service.get_case_or_404(db, principal, case_id)
    case_service.soft_delete_case(db, principal, case)
    audit_service.record(
        db, action="case_deleted", org_id=principal.org_id, case_id=case.id,
        actor=principal, detail={"code": case.display_code},
    )
    return Response(status_code=204)
