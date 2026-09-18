"""Concrete screening rules.

Wording discipline (AI governance): every explanation is phrased as a
screening signal for human review — never as a legal conclusion, citation,
penalty or determination.
"""

from __future__ import annotations

from .base import Rule, RuleContext, RuleViolation, find_quote, missing_evidence

ATTENDANCE_PATTERN = (
    r"attendance|present|absent|muster\s?roll|working hours|hours worked|"
    r"shift|time\s?(in|out)|in-time|out-time|overtime|half\s?day|leave"
)
WAGE_PATTERN = (
    r"\bwage(?:s)?\b|salary|gross|net\s?pay|net\s?salary|pay\s?slip|payslip|"
    r"earnings|deduction|take\s?home|basic(?:\s?pay)?|hra|allowance"
)
PAY_PERIOD_PATTERN = (
    r"pay\s?period|salary\s?(?:for\s+)?month|wage\s?(?:period|month)|"
    r"month\s?of\s?[a-z]+|billing\s?period|\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
)
EMPLOYEE_ID_PATTERN = r"emp(?:loyee)?\s?(?:id|code|no\.?|number)|worker\s?(?:id|code|no\.?)"
STATUTORY_ID_PATTERN = (
    r"\b(?:pf|p\.f\.|epf|provident\s?fund|uan|esi|e\.s\.i\.|esan|"
    r"professional\s?tax|pt(?:ax)?)\b"
)
NET_PAY_PATTERN = r"net\s?(?:pay|salary)|take\s?home|net\s?amount"
GROSS_PATTERN = r"gross(?:\s?(?:pay|salary|wage|earnings))?"
DATE_PATTERN = r"\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{2,4})?"


def _check_no_text(ctx: RuleContext) -> RuleViolation | None:
    if ctx.text.strip():
        return None
    return missing_evidence(
        "DOC-001",
        "No extractable document text",
        "medium",
        "The upload contained no machine-readable text. OCR was unavailable or "
        "produced nothing, so screening could not run. Manual review or a "
        "higher-quality scan is required.",
        95,
    )


def _check_attendance_missing(ctx: RuleContext) -> RuleViolation | None:
    if ctx.doc_type == "payslip":
        return None
    hit = find_quote(ctx, ATTENDANCE_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "ATT-001",
        "Attendance or working-hours evidence not detected",
        "medium",
        "The extracted text does not contain recognisable attendance or "
        "working-hours evidence. If this document is expected to evidence "
        "attendance, review it manually. This is a screening signal, not a "
        "legal determination.",
        72,
    )


def _check_wage_missing(ctx: RuleContext) -> RuleViolation | None:
    if ctx.doc_type == "payslip":
        return None
    hit = find_quote(ctx, WAGE_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "WAGE-001",
        "Wage or payment evidence not detected",
        "medium",
        "The extracted text does not contain recognisable wage or payment "
        "evidence. If wage records are expected, review them manually. "
        "Screening signal only.",
        70,
    )


def _check_payslip_net_gross(ctx: RuleContext) -> RuleViolation | None:
    has_gross = find_quote(ctx, GROSS_PATTERN)
    has_net = find_quote(ctx, NET_PAY_PATTERN)
    if has_gross and has_net:
        return None
    missing = []
    if not has_gross:
        missing.append("gross wages")
    if not has_net:
        missing.append("net pay")
    quote = (has_gross or has_net)
    if quote is not None:
        # Partial evidence found: anchor to the component that exists.
        return RuleViolation(
            rule_id="PAY-001",
            title="Payslip missing wage components",
            severity="medium",
            explanation=(
                f"The payslip shows wage components but does not clearly show: "
                f"{', '.join(missing)}. Incomplete pay component evidence should "
                "be verified against the full payroll record."
            ),
            evidence_kind="quote",
            evidence_quote=quote.evidence_quote,
            page=quote.page,
            char_start=quote.char_start,
            char_end=quote.char_end,
            confidence=78,
        )
    return None  # no wage markers at all -> classifier likely misfired; skip


def _check_payslip_period(ctx: RuleContext) -> RuleViolation | None:
    hit = find_quote(ctx, PAY_PERIOD_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "PAY-002",
        "Pay period not identified",
        "low",
        "No pay period or salary month could be identified in the payslip "
        "text. Without a period the record cannot be matched to a wage cycle. "
        "Verify manually.",
        68,
    )


def _check_payslip_employee_id(ctx: RuleContext) -> RuleViolation | None:
    hit = find_quote(ctx, EMPLOYEE_ID_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "PAY-003",
        "Employee identifier not detected",
        "low",
        "No employee/worker identifier field was detected. An identifier is "
        "needed to attribute this record to a worker. Verify the document "
        "against the establishment's records.",
        65,
    )


def _check_statutory_ids(ctx: RuleContext) -> RuleViolation | None:
    hit = find_quote(ctx, STATUTORY_ID_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "STAT-001",
        "Statutory deduction references not detected",
        "low",
        "No provident-fund/ESI-style deduction references were detected in the "
        "payslip text. This may mean the document is a summary rather than a "
        "statutory payslip. Screening signal for manual verification only — "
        "this does not assert non-compliance.",
        55,
    )


def _check_dates(ctx: RuleContext) -> RuleViolation | None:
    hit = find_quote(ctx, DATE_PATTERN)
    if hit:
        return None
    return missing_evidence(
        "DOC-002",
        "No dates detected in document",
        "low",
        "No recognisable dates were found in the extracted text, so the "
        "document period cannot be established. Verify the record's time "
        "coverage manually.",
        60,
    )


def _check_document_quality(ctx: RuleContext) -> RuleViolation | None:
    """Very short text after extraction suggests a poor scan or partial page."""
    if ctx.doc_type == "payslip" and ctx.text.strip():
        return None
    if len(ctx.normalized_text) >= 120:
        return None
    return missing_evidence(
        "DOC-003",
        "Very little text extracted",
        "low",
        "Only a small amount of text could be extracted, which may indicate a "
        "poor-quality scan or a partial document. Treat screening results for "
        "this document with caution.",
        62,
    )


REGISTRY: tuple[Rule, ...] = (
    Rule("DOC-001", "No extractable document text",
         "Nothing could be extracted from the file.", "medium", ("*",), _check_no_text),
    Rule("DOC-002", "No dates detected in document",
         "Dates are needed to anchor records in time.", "low", ("*",), _check_dates),
    Rule("DOC-003", "Very little text extracted",
         "Poor extraction quality weakens screening reliability.", "low", ("*",), _check_document_quality),
    Rule("ATT-001", "Attendance or working-hours evidence not detected",
         "Attendance evidence presence check.", "medium",
         ("attendance", "unknown"), _check_attendance_missing),
    Rule("WAGE-001", "Wage or payment evidence not detected",
         "Wage evidence presence check.", "medium", ("attendance", "unknown"), _check_wage_missing),
    Rule("PAY-001", "Payslip missing wage components",
         "Gross and net components presence check for payslips.", "medium",
         ("payslip",), _check_payslip_net_gross),
    Rule("PAY-002", "Pay period not identified",
         "Pay period presence check for payslips.", "low", ("payslip",), _check_payslip_period),
    Rule("PAY-003", "Employee identifier not detected",
         "Employee identifier presence check for payslips.", "low", ("payslip",), _check_payslip_employee_id),
    Rule("STAT-001", "Statutory deduction references not detected",
         "Statutory deduction reference presence check for payslips.", "low",
         ("payslip",), _check_statutory_ids),
)

_BY_ID = {rule.rule_id: rule for rule in REGISTRY}


def get_rule(rule_id: str) -> Rule | None:
    return _BY_ID.get(rule_id)


def run_rules(ctx: RuleContext) -> list[RuleViolation]:
    """Run all applicable rules; attach ids/titles/severities from the registry.
    Returns violations in stable registry order. If nothing fires, an
    informational BASE-001 result communicates that checks ran."""
    violations: list[RuleViolation] = []
    for rule in REGISTRY:
        violation = rule.run(ctx)
        if violation is None:
            continue
        violations.append(
            RuleViolation(
                rule_id=rule.rule_id,
                title=rule.title,
                severity=violation.severity or rule.default_severity,
                explanation=violation.explanation,
                evidence_kind=violation.evidence_kind,
                evidence_quote=violation.evidence_quote,
                page=violation.page,
                char_start=violation.char_start,
                char_end=violation.char_end,
                confidence=violation.confidence,
            )
        )
    if not violations:
        violations.append(
            RuleViolation(
                rule_id="BASE-001",
                title="No automated screening issues detected",
                severity="low",
                explanation=(
                    "All applicable deterministic screening checks completed "
                    "without a signal. This does not establish legal compliance; "
                    "it only means no configured check produced a signal."
                ),
                evidence_kind="absence",
                confidence=88,
            )
        )
    return violations
