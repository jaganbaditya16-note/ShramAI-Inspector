# AI Governance

ShramAI Inspector is an assistive decision-support system.

## Required properties

- Explainability: each finding states evidence and check used.
- Traceability: model version, rule version, source document and timestamps are recorded.
- Human oversight: reviewer accepts, rejects or leaves a finding as needs review.
- Reproducibility: document plus versioned configuration can be reprocessed.
- No fabricated legal citations: legal sources are curated/approved and retrieved with provenance.
- Uncertainty is explicit; low confidence is not a definitive violation.
- Do not use protected or sensitive personal characteristics for risk scoring.
- Process only information required for the inspection workflow.

## UI terminology

Use Finding, Check, Potential issue and Needs review instead of presenting model output as a final legal determination.
