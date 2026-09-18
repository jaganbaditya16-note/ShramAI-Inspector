"""Demo-mode provisioning.

In ``auth_mode=demo`` the API injects a virtual demo principal. On startup the
demo organisation receives one synthetic inspection case with a generated,
clearly-labelled synthetic payslip so the workspace is never empty. Demo
seeding runs only when the demo organisation contains no cases, so restarting
never duplicates data, and it is disabled entirely in ``auth_mode=required``.
"""

from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging import get_logger
from ..core.security import DEMO_ROLE, hash_password
from ..models import Case, Document, Organization, User
from .storage import get_store
from .synthetic import build_synthetic_pdf

logger = get_logger(__name__)

DEMO_ORG_SLUG = "demo-inspectorate"
DEMO_USER_EMAIL = "demo@shramai.local"


def ensure_demo_org(db: Session) -> tuple[Organization, User]:
    org = db.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    if org is None:
        org = Organization(name=settings.demo_org_name, slug=DEMO_ORG_SLUG)
        db.add(org)
        db.flush()
    user = db.scalar(select(User).where(User.email == DEMO_USER_EMAIL))
    if user is None:
        user = User(
            org_id=org.id,
            email=DEMO_USER_EMAIL,
            name=settings.demo_user_name,
            # Random unusable credential; the demo principal never logs in.
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role=DEMO_ROLE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return org, user


async def seed_demo_case(db: Session, org: Organization, user: User) -> None:
    """Create the demo case + one fully-processed synthetic document if absent."""
    existing = db.scalar(select(func.count(Case.id)).where(Case.org_id == org.id))
    if existing:
        return

    from .case_service import new_display_code

    case = Case(
        org_id=org.id,
        display_code=new_display_code(db),
        title="Demo Factory Inspection",
        establishment_name="Ashok Industries (Synthetic Demo) Pvt. Ltd.",
        establishment_reference="SYN-000111",
        status="draft",
        created_by=user.id,
    )
    db.add(case)
    db.flush()

    from .malware import scan_upload

    pdf = build_synthetic_pdf()
    scan_result = await scan_upload(pdf, "synthetic-demo-payslip.pdf")
    if not scan_result.passed:
        logger.warning(
            "event=demo_seed_scan_blocked verdict=%s", scan_result.verdict.value
        )
        return

    key = get_store().save(pdf, ".pdf")
    document = Document(
        org_id=org.id,
        case_id=case.id,
        original_filename="synthetic-demo-payslip.pdf",
        storage_key=key,
        content_type="application/pdf",
        size_bytes=len(pdf),
        sha256=hashlib.sha256(pdf).hexdigest(),
        status="queued",
        scan_status=scan_result.verdict.value,
        scan_engine=scan_result.engine,
        scan_note=(scan_result.note or "")[:200] or None,
        created_by=user.id,
    )
    db.add(document)
    db.flush()
    from ..models import ProcessingJob

    job = ProcessingJob(org_id=org.id, document_id=document.id, status="queued")
    db.add(job)
    db.commit()
    logger.info("event=demo_case_seeded case=%s document=%s", case.id, document.id)

    from .pipeline import run_pipeline

    outcome = await run_pipeline(db, document.id, job.id)
    logger.info(
        "event=demo_document_processed status=%s findings=%d",
        outcome.document_status, outcome.rule_findings,
    )


async def seed_demo_workspace(db: Session) -> None:
    if settings.auth_mode != "demo":
        return
    org, user = ensure_demo_org(db)
    await seed_demo_case(db, org, user)
