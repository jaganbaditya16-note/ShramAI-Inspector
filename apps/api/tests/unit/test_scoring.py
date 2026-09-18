"""Scoring unit tests: transparent, deterministic prioritisation."""

from __future__ import annotations

from app.services.scoring import ScoreInput, score_findings


def test_no_findings_is_full_score():
    result = score_findings([])
    assert result.score == 100
    assert result.risk_level == "Low"


def test_weights_and_review_halving():
    result = score_findings([
        ScoreInput("high", "confirmed"),     # -22
        ScoreInput("medium", "needs_review"),  # -6
        ScoreInput("low", "dismissed"),      # -0
    ])
    assert result.score == 100 - 28
    assert result.risk_level == "Moderate"


def test_risk_bands():
    assert score_findings([ScoreInput("high", "confirmed")]).risk_level == "Moderate"  # 78
    many_high = [ScoreInput("high", "confirmed")] * 3  # -66
    result = score_findings(many_high)
    assert result.score == 34
    assert result.risk_level == "High"


def test_score_never_below_zero():
    result = score_findings([ScoreInput("high", "confirmed")] * 10)
    assert result.score == 0


def test_unknown_severity_is_ignored_safely():
    result = score_findings([ScoreInput("catastrophic", "confirmed")])
    assert result.score == 100
