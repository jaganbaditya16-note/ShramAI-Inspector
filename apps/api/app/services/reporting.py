"""Screening report (scorecard) generation and persistence.

The report is an immutable snapshot: findings, review decisions, versions,
provenance and the scoring formula at generation time. It is explicitly
labelled as a screening aid, never a legal determination.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import Principal
from ..models import Case, Document, Finding, ModelRun, Report
from .scoring import SCORE_EXPLANATION, ScoreInput, score_findings

_DISCLAIMER = (
    "This scorecard is an AI-assisted screening summary generated for "
    "authorised human review. It is not a legal compliance determination, "
    "penalty, or enforcement decision. Every substantive finding requires "
    "human verification against the underlying documents."
)


def _finding_payload(finding: Finding, document_filename: str) -> dict:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "rule_version": finding.rule_version,
        "origin": finding.origin,
        "title": finding.title,
        "severity": finding.severity,
        "status": finding.status,
        "explanation": finding.explanation,
        "evidence": {
            "kind": finding.evidence_kind,
            "quote": finding.evidence_quote or None,
            "page": finding.page,
            "char_start": finding.char_start,
            "char_end": finding.char_end,
        },
        "confidence": finding.confidence,
        "ai_metadata": finding.metadata_json,
        "review": {
            "reviewed_by": finding.reviewed_by,
            "reviewed_at": finding.reviewed_at.isoformat() if finding.reviewed_at else None,
            "note": finding.review_note,
        },
        "document": {"id": finding.document_id, "filename": document_filename},
        "created_at": finding.created_at.isoformat(),
    }


def generate_report(db: Session, principal: Principal, case: Case) -> Report:
    findings = list(
        db.scalars(
            select(Finding)
            .where(Finding.case_id == case.id)
            .order_by(Finding.created_at.asc())
        )
    )
    documents = {
        d.id: d.original_filename
        for d in db.scalars(select(Document).where(Document.case_id == case.id)).all()
    }
    model_runs = list(
        db.scalars(
            select(ModelRun)
            .join(Document, ModelRun.document_id == Document.id)
            .where(Document.case_id == case.id)
            .order_by(ModelRun.created_at.asc())
        )
    )
    score = score_findings([ScoreInput(f.severity, f.status) for f in findings])

    payload = {
        "case": {
            "id": case.id,
            "code": case.display_code,
            "title": case.title,
            "status": case.status,
            "establishment_name": case.establishment_name,
            "establishment_reference": case.establishment_reference,
        },
        "generated_at": None,  # stamped from report row
        "generated_by": principal.display_name,
        "screening_score": score.score,
        "risk_level": score.risk_level,
        "score_breakdown": score.breakdown,
        "score_explanation": SCORE_EXPLANATION,
        "disclaimer": _DISCLAIMER,
        "counts": {
            "documents": len(documents),
            "findings": len(findings),
            "confirmed": sum(1 for f in findings if f.status == "confirmed"),
            "dismissed": sum(1 for f in findings if f.status == "dismissed"),
            "needs_review": sum(1 for f in findings if f.status == "needs_review"),
        },
        "provenance": {
            "rule_versions": sorted({f.rule_version for f in findings if f.rule_version}),
            "ai_runs": [
                {
                    "provider": run.provider,
                    "model": run.model,
                    "status": run.status,
                    "prompt_version": run.prompt_version,
                    "findings_produced": run.findings_produced,
                    "findings_rejected_ungrounded": run.findings_rejected,
                }
                for run in model_runs
            ],
        },
        "findings": [
            _finding_payload(f, documents.get(f.document_id, "unknown")) for f in findings
        ],
    }
    report = Report(
        org_id=case.org_id,
        case_id=case.id,
        created_by=principal.user_id,
        score=score.score,
        risk_level=score.risk_level,
        payload=payload,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def latest_report(db: Session, case: Case) -> Report | None:
    return db.scalar(
        select(Report)
        .where(Report.case_id == case.id)
        .order_by(Report.created_at.desc())
        .limit(1)
    )


def report_payload(report: Report) -> dict:
    payload = dict(report.payload)
    payload["generated_at"] = report.created_at.isoformat()
    payload["report_id"] = report.id
    return payload
