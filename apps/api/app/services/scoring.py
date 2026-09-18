"""Transparent, deterministic screening score.

The score is a prioritisation aid derived only from configured findings and
their review state. It is NOT a legal compliance score. The formula is public
and included in report payloads so any reviewer can reproduce it.

Weights per severity: high=22, medium=12, low=5.
Deduction: confirmed = full weight, needs_review = half weight (min 1),
dismissed = 0. Score = 100 - total deductions, clamped to [0, 100].
Risk bands: >=80 Low, >=60 Moderate, else High.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_WEIGHTS = {"high": 22, "medium": 12, "low": 5}


@dataclass(frozen=True)
class ScoreInput:
    severity: str
    status: str  # needs_review | confirmed | dismissed


@dataclass(frozen=True)
class ScoreResult:
    score: int
    risk_level: str
    total_deduction: int
    breakdown: dict[str, int] = field(default_factory=dict)


def score_findings(inputs: list[ScoreInput]) -> ScoreResult:
    breakdown: dict[str, int] = {"confirmed_high": 0, "confirmed_medium": 0, "confirmed_low": 0,
                                 "pending_high": 0, "pending_medium": 0, "pending_low": 0}
    total = 0
    for item in inputs:
        weight = SEVERITY_WEIGHTS.get(item.severity)
        if weight is None or item.status == "dismissed":
            continue
        if item.status == "confirmed":
            total += weight
            breakdown[f"confirmed_{item.severity}"] += weight
        elif item.status == "needs_review":
            deduction = max(1, weight // 2)
            total += deduction
            breakdown[f"pending_{item.severity}"] += deduction
    score = max(0, min(100, 100 - total))
    risk = "Low" if score >= 80 else "Moderate" if score >= 60 else "High"
    return ScoreResult(score=score, risk_level=risk, total_deduction=total, breakdown=breakdown)


SCORE_EXPLANATION = (
    "Screening score = 100 minus weighted deductions (high=22, medium=12, "
    "low=5; confirmed findings deduct fully, unresolved findings deduct half). "
    "It is a transparent prioritisation aid for reviewers, not a legal "
    "compliance score or enforcement decision."
)
