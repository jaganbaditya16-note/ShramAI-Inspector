"""Case lifecycle services. Every query is organisation-scoped."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import Conflict, Forbidden, NotFound, ValidationFailure
from ..core.security import Principal
from ..models import Case, Document, Finding

CASE_STATUSES = ("draft", "in_review", "closed")
_YEAR = None  # set lazily in _new_display_code


def _now() -> datetime:
    return datetime.now(UTC)


def new_display_code(db: Session) -> str:
    year = _now().year
    for _ in range(8):
        code = f"SH-{year}-{secrets.token_hex(3).upper()}"
        exists = db.scalar(select(Case.id).where(Case.display_code == code))
        if not exists:
            return code
    raise Conflict("Could not allocate a case code; please retry.")


def get_case_or_404(db: Session, principal: Principal, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None or case.is_deleted or case.org_id != principal.org_id:
        # Indistinguishable 404 for missing and cross-tenant cases (IDOR guard).
        raise NotFound("Case not found.")
    return case


def create_case(db: Session, principal: Principal, *, title: str, establishment_name: str,
                establishment_reference: str | None, notes: str) -> Case:
    case = Case(
        org_id=principal.org_id,
        display_code=new_display_code(db),
        title=title,
        establishment_name=establishment_name,
        establishment_reference=establishment_reference,
        notes=notes,
        created_by=principal.user_id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def update_case(db: Session, principal: Principal, case: Case, changes: dict) -> Case:
    if not principal.has_role("inspector"):
        raise Forbidden("Viewer role cannot modify cases.")
    allowed = {"title", "establishment_name", "establishment_reference", "notes", "status"}
    for key, value in changes.items():
        if key in allowed and value is not None:
            setattr(case, key, value)
    db.commit()
    db.refresh(case)
    return case


def soft_delete_case(db: Session, principal: Principal, case: Case) -> None:
    if not principal.has_role("inspector"):
        raise Forbidden("Viewer role cannot delete cases.")
    case.deleted_at = _now()
    db.commit()


def case_counts(db: Session, case_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """document and finding counts for the given cases (2 grouped queries)."""
    doc_counts: dict[str, int] = {}
    finding_counts: dict[str, int] = {}
    if not case_ids:
        return doc_counts, finding_counts
    doc_rows = db.execute(
        select(Document.case_id, func.count(Document.id))
        .where(Document.case_id.in_(case_ids))
        .group_by(Document.case_id)
    ).all()
    finding_rows = db.execute(
        select(Finding.case_id, func.count(Finding.id))
        .where(Finding.case_id.in_(case_ids))
        .group_by(Finding.case_id)
    ).all()
    doc_counts = {row[0]: row[1] for row in doc_rows}
    finding_counts = {row[0]: row[1] for row in finding_rows}
    return doc_counts, finding_counts


def validate_status_transition(current: str, target: str) -> None:
    if target not in CASE_STATUSES:
        raise ValidationFailure(f"Unknown case status '{target}'.")
    if current == target:
        return
    if current == "closed" and target != "draft":
        raise ValidationFailure("A closed case can only be reopened to draft.")
