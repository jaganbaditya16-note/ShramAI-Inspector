# AI Governance

ShramAI Inspector is an **assistive screening system**. It is never a legal
authority, never generates legal conclusions, citations, penalties or deadlines,
and never takes enforcement action.

## Enforced properties

| Property | Mechanism |
|---|---|
| Explainability | every finding carries explanation + evidence quote or explicit absence note + page/char anchors |
| Traceability | `model_runs` records provider, model, prompt version, latency, grounding stats; findings carry rule id + rule version; reports snapshot all of it |
| Grounding | AI findings must quote verbatim document evidence; ungrounded quotes are rejected automatically and counted (`findings_rejected_ungrounded`) |
| Human oversight | findings start at `needs_review`; only humans confirm/dismiss; decisions are attributed and audited |
| Reproducibility | deterministic rules are pure + versioned (`RULE_VERSION`); reprocessing preserves decisions; reports are immutable snapshots |
| Untrusted inputs | document text is delimited data; instructions inside documents cannot alter behaviour (tested) |
| Uncertainty | confidence is displayed as a labelled signal; low confidence never hardens into a conclusion |
| Non-discrimination | no protected-characteristic features are used anywhere in scoring; scoring uses only severity + review state |
| Data minimisation | AI receives only extracted text (bounded) and approved reference snippets; no enrichment from external sources |

## Prompt governance

- System prompt is versioned in code (`PROMPT_VERSION`) and asserts the assistant's
  non-authority, the untrusted-data status of document text, and the verbatim-quote
  requirement.
- Retrieval is restricted to the approved corpus in `data/knowledge/` (versioned
  markdown with source metadata). The repository ships only clearly-synthetic
  sample material — no fabricated legal citations.
- Model temperature is 0 and output format is forced JSON; schema violations are
  recorded as `error` model runs, never partially trusted.

## UI terminology

"Finding", "screening signal", "needs review", "AI-assisted" — never "violation",
"penalty", "compliant". The scorecard states explicitly that it is a prioritisation
aid, not a legal compliance score.
