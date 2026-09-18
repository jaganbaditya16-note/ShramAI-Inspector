"""AI grounding unit tests — hallucinated evidence must be detectable."""

from __future__ import annotations

from app.services.ai import AIFindingSchema, AIResponseSchema, ground_evidence

DOC = (
    "SYNTHETIC DEMO PAYSLIP\n"
    "Establishment: Ashok Industries (Synthetic Demo) Pvt. Ltd.\n"
    "Employee Id: EMP-20014\n"
    "Gross earnings: Rs. 24,100.00\n"
    "Basic pay: Rs. 18,000.00"
)


def test_exact_quote_grounded():
    grounded, offset = ground_evidence("Gross earnings: Rs. 24,100.00", DOC)
    assert grounded
    assert offset is not None and offset >= 0


def test_whitespace_and_case_insensitive_grounding():
    grounded, _ = ground_evidence("gross   EARNINGS: rs. 24,100.00", DOC)
    assert grounded


def test_hallucinated_quote_rejected():
    grounded, _ = ground_evidence("Net pay: Rs. 99,999.00", DOC)
    assert not grounded


def test_prefix_fallback_grounded():
    grounded, _ = ground_evidence("Establishment: Ashok Industries (Synthetic Demo) Pvt. Ltd. plus trailing text", DOC)
    assert grounded


def test_schema_rejects_extra_fields():
    raw = {
        "findings": [{
            "rule_id": "AI-001", "title": "Missing net pay", "severity": "high",
            "explanation": "Net pay line absent from the payslip evidence.",
            "evidence": "Gross earnings: Rs. 24,100.00", "confidence": 70,
            "citation": "Section 9 (invented)",
        }]
    }
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AIResponseSchema.model_validate(raw)


def test_schema_rejects_bad_severity():
    with __import__("pytest").raises(__import__("pydantic").ValidationError):
        AIFindingSchema(
            rule_id="AI-001", title="Something odd here", severity="critical",
            explanation="This severity is not allowed by the schema.",
            evidence="Gross earnings: Rs. 24,100.00", confidence=50,
        )
