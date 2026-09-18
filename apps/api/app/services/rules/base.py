"""Deterministic screening rule engine.

Rules are pure, versioned functions over an immutable inspection context.
Every produced violation carries either a verbatim evidence quote (with page
and character anchors) or an explicit ``absence`` evidence kind when the check
is about missing evidence. The engine never mutates state and never calls the
network, so results are reproducible for a given text + rule version.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

RULE_VERSION = "2026.09.0"

SEVERITIES = ("low", "medium", "high")


@dataclass(frozen=True)
class RuleContext:
    text: str
    normalized_text: str  # lowercased, whitespace-collapsed
    pages: list  # list[extraction.PageText]
    doc_type: str  # payslip | attendance | unknown
    doc_type_confidence: int


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str
    title: str
    severity: str
    explanation: str
    evidence_kind: str  # quote | absence
    evidence_quote: str = ""
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    confidence: int = 80


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    description: str
    default_severity: str
    applies_to: tuple[str, ...]  # doc types the rule runs for; ("*",) = all
    check: Callable[[RuleContext], RuleViolation | None]

    def run(self, ctx: RuleContext) -> RuleViolation | None:
        if self.applies_to != ("*",) and ctx.doc_type not in self.applies_to:
            return None
        return self.check(ctx)


def evidence_hash(quote: str) -> str:
    normalized = re.sub(r"\s+", " ", quote.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def find_quote(ctx: RuleContext, pattern: str, *, window: int = 160) -> RuleViolation | None:
    """Locate a regex match in the original text and anchor it to a page."""
    match = re.search(pattern, ctx.text, re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start())
    end = min(len(ctx.text), match.end())
    quote = ctx.text[start: min(len(ctx.text), end + window)]
    quote = re.sub(r"\s+", " ", quote).strip()
    if len(quote) > window:
        quote = quote[:window].rstrip() + "…"
    page = next((p.page for p in ctx.pages if p.start <= start < p.end), None)
    return RuleViolation(
        rule_id="", title="", severity="low", explanation="", evidence_kind="quote",
        evidence_quote=quote, page=page, char_start=start, char_end=end,
    )


def missing_evidence(rule_id: str, title: str, severity: str, explanation: str,
                     confidence: int) -> RuleViolation:
    return RuleViolation(
        rule_id=rule_id, title=title, severity=severity, explanation=explanation,
        evidence_kind="absence", confidence=confidence,
    )
