"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { use } from "react";
import { api, errorMessage } from "@/lib/api";
import type { AuditListResponse, FindingListResponse, ReportResponse } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";
import { PageFade } from "@/components/motion";
import { UploadPanel } from "@/components/app/upload-panel";
import { ScoreRing } from "@/components/ui/score-ring";
import { InlineError, EmptyState } from "@/components/ui/feedback";
import { SeverityBadge, StatusBadge, OriginBadge } from "@/components/ui/badge";
import { AuditTimeline } from "@/components/app/audit-timeline";
import { formatDateTime } from "@/lib/format";
import { useCase } from "./layout";

export default function CaseOverviewPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const { data: caseData } = useCase(caseId);

  const findings = useQuery({
    queryKey: queryKeys.findings(caseId),
    queryFn: () => api.get<FindingListResponse>(`/cases/${caseId}/findings?limit=5&sort=-severity`),
  });

  const report = useQuery({
    queryKey: queryKeys.report(caseId),
    queryFn: () => api.get<ReportResponse>(`/cases/${caseId}/report`),
    retry: false,
  });

  const audit = useQuery({
    queryKey: queryKeys.audit(caseId),
    queryFn: () => api.get<AuditListResponse>(`/cases/${caseId}/audit?limit=6`),
  });

  const hasDocuments = (caseData?.document_count ?? 0) > 0;

  return (
    <PageFade>
      <div className="grid-main">
        <div className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Upload documents</h2>
                <p className="card-subtitle">
                  Files are validated, stored privately, then screened: extraction →
                  classification → deterministic rules → optional AI analysis.
                </p>
              </div>
            </div>
            <div className="card-body">
              <UploadPanel caseId={caseId} disabled={caseData?.status === "closed"} />
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Top findings</h2>
                <p className="card-subtitle">Highest-severity screening signals for this case</p>
              </div>
              <Link className="btn btn-secondary btn-sm" href={`/cases/${caseId}/findings`}>
                All findings
              </Link>
            </div>
            <div className="card-body">
              {findings.isError ? (
                <InlineError message={errorMessage(findings.error)} requestId={null} />
              ) : findings.isLoading ? (
                <p className="text-muted text-small">Loading findings…</p>
              ) : findings.data && findings.data.items.length === 0 ? (
                <EmptyState
                  title={hasDocuments ? "No findings yet" : "Nothing to screen yet"}
                  description={
                    hasDocuments
                      ? "Uploaded documents produced no screening signals so far."
                      : "Upload a labour document above — findings appear here with evidence and confidence."
                  }
                />
              ) : findings.data ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {findings.data.items.map((finding) => (
                    <div
                      key={finding.id}
                      style={{
                        border: "1px solid var(--ink-200)",
                        borderRadius: 10,
                        padding: "12px 14px",
                      }}
                    >
                      <div className="finding-badges" style={{ marginBottom: 8 }}>
                        <SeverityBadge severity={finding.severity} />
                        <StatusBadge status={finding.status} />
                        <OriginBadge origin={finding.origin} />
                      </div>
                      <p className="text-strong">{finding.title}</p>
                      <p className="text-small text-muted" style={{ marginTop: 3 }}>
                        {finding.rule_id} · {finding.explanation.slice(0, 90)}
                        {finding.explanation.length > 90 ? "…" : ""}
                      </p>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Screening score</h2>
                <p className="card-subtitle">Transparent prioritisation aid — not a legal score</p>
              </div>
            </div>
            <div className="card-body" style={{ display: "flex", gap: 18, alignItems: "center" }}>
              {report.data ? (
                <>
                  <ScoreRing score={report.data.score} label={report.data.risk_level} />
                  <div>
                    <p className="text-small text-muted">
                      Generated {formatDateTime(report.data.created_at)}
                    </p>
                    <p className="text-small text-muted" style={{ marginTop: 4 }}>
                      {report.data.payload.counts.needs_review} finding(s) still need review ·{" "}
                      {report.data.payload.counts.confirmed} confirmed
                    </p>
                    <Link
                      className="btn btn-secondary btn-sm"
                      style={{ marginTop: 12 }}
                      href={`/cases/${caseId}/report`}
                    >
                      View scorecard
                    </Link>
                  </div>
                </>
              ) : (
                <div style={{ padding: "8px 0" }}>
                  <p className="text-small text-muted">
                    No scorecard generated yet. Upload documents, complete reviews, then generate
                    a report from the Report tab.
                  </p>
                </div>
              )}
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Case details</h2>
              </div>
            </div>
            <div className="card-body" style={{ display: "grid", gap: 10 }}>
              <DetailRow label="Documents" value={String(caseData?.document_count ?? "—")} />
              <DetailRow label="Findings" value={String(caseData?.finding_count ?? "—")} />
              <DetailRow label="Created" value={formatDateTime(caseData?.created_at)} />
              <DetailRow label="Last updated" value={formatDateTime(caseData?.updated_at)} />
              <DetailRow label="Establishment ref" value={caseData?.establishment_reference ?? "—"} />
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Recent case activity</h2>
              </div>
              <Link className="btn btn-ghost btn-sm" href={`/cases/${caseId}/audit`}>
                Full trail
              </Link>
            </div>
            <div className="card-body">
              {audit.data && audit.data.items.length > 0 ? (
                <AuditTimeline events={audit.data.items} />
              ) : (
                <p className="text-small text-muted">No activity recorded yet.</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </PageFade>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
      <span className="text-muted">{label}</span>
      <span className="text-strong" style={{ textAlign: "right", wordBreak: "break-all" }}>
        {value}
      </span>
    </div>
  );
}
