"""Deterministic rule engine unit tests."""

from __future__ import annotations

from app.services.classification import classify
from app.services.rules import REGISTRY, RULE_VERSION, RuleContext, run_rules


def _ctx(text: str, doc_type: str | None = None) -> RuleContext:
    resolved = doc_type or classify(text).doc_type
    from app.services.extraction import PageText

    pages = [PageText(page=1, text=text, start=0, end=len(text))]
    return RuleContext(
        text=text, normalized_text=" ".join(text.lower().split()),
        pages=pages, doc_type=resolved, doc_type_confidence=80,
    )


def test_registry_ids_are_unique_and_versioned():
    ids = [rule.rule_id for rule in REGISTRY]
    assert len(ids) == len(set(ids))
    assert RULE_VERSION.count(".") == 2  # semantic-ish version string


def test_empty_text_flags_doc_001():
    violations = run_rules(_ctx(""))
    assert violations[0].rule_id == "DOC-001"
    assert violations[0].evidence_kind == "absence"


def test_unrelated_text_flags_attendance_and_wage():
    violations = run_rules(_ctx("Employee list with names only EMP-1 EMP-2"))
    ids = {v.rule_id for v in violations}
    assert "ATT-001" in ids
    assert "WAGE-001" in ids


def test_payslip_classification_runs_payslip_rules_only():
    text = (
        "SYNTHETIC DEMO PAYSLIP Establishment: Ashok Industries Employee Id: EMP-20014 "
        "Pay period: 08/2026 Basic pay: Rs. 18,000.00 HRA allowance: Rs. 4,500.00 "
        "Gross earnings: Rs. 24,100.00 PF provident fund contribution: Rs. 1,800.00"
    )
    assert classify(text).doc_type == "payslip"
    violations = run_rules(_ctx(text))
    ids = {v.rule_id for v in violations}
    # Missing net pay must fire; attendance/wage checks must not apply to payslips.
    assert "PAY-001" in ids
    assert "ATT-001" not in ids
    assert "WAGE-001" not in ids


def test_complete_payslip_is_clean():
    text = (
        "SYNTHETIC DEMO PAYSLIP Employee Id: EMP-20014 Pay period: 08/2026 "
        "Basic pay Rs. 18,000 Gross earnings: Rs. 24,100.00 Net pay: Rs. 22,100.00 "
        "PF UAN provided"
    )
    violations = run_rules(_ctx(text))
    assert all(v.rule_id == "BASE-001" for v in violations)


def test_quote_anchoring_returns_page_and_offsets():
    text = (
        "Payslip Employee Id: EMP-20014 Pay period: 08/2026 "
        "Gross earnings: Rs. 24,100.00 PF contribution Rs. 1,800.00"
    )
    violations = run_rules(_ctx(text, doc_type="payslip"))
    quotable = [v for v in violations if v.evidence_kind == "quote"]
    assert quotable, "expected PAY-001 partial-evidence quote"
    for violation in quotable:
        assert violation.rule_id == "PAY-001"
        assert violation.page == 1
        assert violation.char_start is not None
        assert violation.char_end > violation.char_start
        assert violation.evidence_quote.lower().startswith("gross")


def test_short_text_flags_quality():
    violations = run_rules(_ctx("attendance wage", doc_type="attendance"))
    ids = {v.rule_id for v in violations}
    assert "DOC-003" in ids
