/** API contract types mirroring the FastAPI response models. */

export type Role = "admin" | "inspector" | "viewer";

export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  org_id: string;
  is_demo: boolean;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  version: string;
  app_env: string;
  auth_mode: "demo" | "required";
  ai: { provider: string; configured: boolean };
}

export interface ListMeta {
  total: number;
  limit: number;
  offset: number;
}

export type CaseStatus = "draft" | "in_review" | "closed";

export interface Case {
  id: string;
  display_code: string;
  title: string;
  establishment_name: string;
  establishment_reference: string | null;
  status: CaseStatus;
  notes: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  document_count: number;
  finding_count: number;
}

export interface CaseListResponse {
  items: Case[];
  meta: ListMeta;
}

export interface JobSummary {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  error: string | null;
  detail: {
    rule_findings?: number;
    ai_findings?: number;
    ai_status?: string;
    ai_findings_rejected_ungrounded?: number;
    warnings?: string[];
    timings_ms?: Record<string, number>;
  } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export type DocumentStatus = "queued" | "processing" | "processed" | "failed";

export interface InspectorDocument {
  id: string;
  case_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  text_chars: number;
  extraction_method: string;
  doc_type: string;
  doc_type_confidence: number;
  created_at: string;
  processed_at: string | null;
  job: JobSummary | null;
}

export interface DocumentListResponse {
  items: InspectorDocument[];
  meta: ListMeta;
}

export type FindingOrigin = "rule" | "ai";
export type FindingSeverity = "low" | "medium" | "high";
export type FindingStatus = "needs_review" | "confirmed" | "dismissed";

export interface Finding {
  id: string;
  document_id: string;
  rule_id: string;
  rule_version: string;
  origin: FindingOrigin;
  title: string;
  severity: FindingSeverity;
  status: FindingStatus;
  explanation: string;
  evidence_kind: "quote" | "absence";
  evidence_quote: string;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
  confidence: number;
  ai_metadata?: {
    provider?: string;
    model?: string;
    prompt_version?: string;
    grounding?: string;
  } | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
}

export interface FindingListResponse {
  items: Finding[];
  meta: ListMeta;
}

export interface AuditEvent {
  id: number;
  action: string;
  actor_label: string;
  case_id: string | null;
  detail: Record<string, unknown>;
  request_id: string;
  created_at: string;
}

export interface AuditListResponse {
  items: AuditEvent[];
  meta: ListMeta;
}

export interface ReportPayload {
  case: {
    id: string;
    code: string;
    title: string;
    status: string;
    establishment_name: string;
    establishment_reference: string | null;
  };
  generated_at: string;
  generated_by: string;
  screening_score: number;
  risk_level: string;
  score_breakdown: Record<string, number>;
  score_explanation: string;
  disclaimer: string;
  counts: {
    documents: number;
    findings: number;
    confirmed: number;
    dismissed: number;
    needs_review: number;
  };
  provenance: {
    rule_versions: string[];
    ai_runs: Array<{
      provider: string;
      model: string;
      status: string;
      prompt_version: string;
      findings_produced: number;
      findings_rejected_ungrounded: number;
    }>;
  };
  findings: Array<{
    id: string;
    rule_id: string;
    rule_version: string;
    origin: FindingOrigin;
    title: string;
    severity: FindingSeverity;
    status: FindingStatus;
    explanation: string;
    evidence: {
      kind: string;
      quote: string | null;
      page: number | null;
      char_start: number | null;
      char_end: number | null;
    };
    confidence: number;
    review: {
      reviewed_by: string | null;
      reviewed_at: string | null;
      note: string | null;
    };
    document: { id: string; filename: string };
    created_at: string;
  }>;
}

export interface ReportResponse {
  id: string;
  case_id: string;
  score: number;
  risk_level: string;
  created_at: string;
  payload: ReportPayload;
}

export interface DashboardSummaryResponse {
  cases_total: number;
  cases_by_status: Record<string, number>;
  documents_total: number;
  documents_failed: number;
  findings_total: number;
  findings_by_status: Record<string, number>;
  findings_by_severity: Record<string, number>;
  ai_runs_total: number;
  recent_activity: AuditEvent[];
}

export interface UploadAccepted {
  document: InspectorDocument;
  job: JobSummary;
  message: string;
}
