from app.services.rules import run_rules

def test_missing_evidence_is_flagged():
    findings = run_rules("Employee list with names only")
    ids = {item.rule_id for item in findings}
    assert "ATT-001" in ids
    assert "WAGE-001" in ids

def test_present_evidence_has_no_missing_evidence_flags():
    findings = run_rules("Attendance present absent working hours; Wage salary gross net pay")
    assert all(item.rule_id == "BASE-001" for item in findings)
