"""Deterministic document-type classification.

Keyword-weighted scoring over the extracted text picks the document family
(payslip / attendance / unknown). The result decides which screening rules
apply, so a payslip is never flagged for missing attendance data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DocType = str  # "payslip" | "attendance" | "unknown"


@dataclass(frozen=True)
class Classification:
    doc_type: DocType
    confidence: int  # 0..100


_PAYSLIP_MARKERS = {
    "payslip": 3, "pay slip": 3, "salary slip": 3, "gross": 2, "net pay": 3,
    "net salary": 3, "deductions": 2, "basic": 1, "hra": 2, "allowance": 2,
    "wage slip": 3, "earnings": 2, "pay period": 2, "ctc": 1, "provident fund": 2,
    "provident": 1, "esi": 1, "professional tax": 2, "take home": 2,
}
_ATTENDANCE_MARKERS = {
    "attendance": 3, "present": 2, "absent": 2, "leave": 1, "shift": 2,
    "working hours": 3, "hours worked": 3, "overtime": 2, "muster roll": 3,
    "half day": 2, "attendance register": 3, "time in": 2, "time out": 2,
    "in-time": 2, "out-time": 2, "duty": 1,
}
_DATE_RE = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\b")
_MONEY_RE = re.compile(r"(?:₹|rs\.?|inr)\s?\d|\b\d{3,}(?:[.,]\d{2})\b", re.IGNORECASE)


def classify(text: str) -> Classification:
    normalized = re.sub(r"\s+", " ", text.lower())
    if not normalized.strip():
        return Classification(doc_type="unknown", confidence=0)

    payslip_score = sum(weight for marker, weight in _PAYSLIP_MARKERS.items() if marker in normalized)
    attendance_score = sum(weight for marker, weight in _ATTENDANCE_MARKERS.items() if marker in normalized)
    if _MONEY_RE.search(normalized):
        payslip_score += 2

    total = payslip_score + attendance_score
    if total == 0:
        return Classification(doc_type="unknown", confidence=10)

    if payslip_score > attendance_score and payslip_score >= 5:
        confidence = min(95, 45 + payslip_score * 4)
        return Classification(doc_type="payslip", confidence=confidence)
    if attendance_score > payslip_score and attendance_score >= 5:
        confidence = min(95, 45 + attendance_score * 4)
        return Classification(doc_type="attendance", confidence=confidence)
    if payslip_score > 0 and payslip_score == attendance_score:
        return Classification(doc_type="unknown", confidence=30)
    return Classification(doc_type="unknown", confidence=max(10, 30 - abs(payslip_score - attendance_score) *
                5))


def has_date_evidence(text: str) -> bool:
    return bool(_DATE_RE.search(text))
