import re
from dataclasses import dataclass

@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    title: str
    severity: str
    explanation: str
    evidence: str
    confidence: int

RULE_VERSION = "demo-2026.09"


def run_rules(text: str) -> list[RuleResult]:
    normalized = text.lower()
    results: list[RuleResult] = []

    if not text.strip():
        results.append(RuleResult(
            "DOC-001", "Document text could not be extracted", "medium",
            "The uploaded file has no machine-readable text available to the demo extractor. OCR or manual verification is required.",
            "No extractable text", 60))
        return results

    if not re.search(r"attendance|present|absent|working hours", normalized):
        results.append(RuleResult(
            "ATT-001", "Attendance evidence not detected", "medium",
            "The document text does not contain recognizable attendance/working-hours evidence. This is a screening signal, not a legal determination.",
            "No attendance-related field detected in extracted text", 72))

    if not re.search(r"wage|salary|gross|net pay|pay slip", normalized):
        results.append(RuleResult(
            "WAGE-001", "Wage evidence not detected", "medium",
            "The document text does not contain recognizable wage/pay evidence. Review the relevant record manually.",
            "No wage-related field detected in extracted text", 70))

    if not results:
        results.append(RuleResult(
            "BASE-001", "No automated screening issue detected", "low",
            "Configured demo screening rules did not detect a missing evidence pattern. This does not establish legal compliance.",
            "Configured checks completed", 88))
    return results
