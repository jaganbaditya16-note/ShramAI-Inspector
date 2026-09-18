"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage, errorCode } from "@/lib/api";
import type { DashboardSummaryResponse } from "@/lib/types";
import { PageHeader } from "@/components/app/page-header";
import { PageFade } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { InlineError, SkeletonCard, Skeleton } from "@/components/ui/feedback";
import { StatCard } from "@/components/app/stat-card";
import { AuditTimeline } from "@/components/app/audit-timeline";
import { queryKeys } from "@/lib/query-keys";
import { titleCase } from "@/lib/format";

export default function DashboardPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => api.get<DashboardSummaryResponse>("/dashboard/summary"),
  });

  return (
    <PageFade>
      <PageHeader
        kicker="Inspection overview"
        title="Dashboard"
        description="Organisation-wide screening activity: cases, documents, findings and recent audit events."
        actions={
          <>
            <Button variant="ghost" onClick={() => void refetch()} disabled={isFetching}>
              Refresh
            </Button>
            <Link className="btn btn-primary" href="/cases">
              Open cases
            </Link>
          </>
        }
      />

      {isError ? (
        <InlineError
          message={errorMessage(error)}
          requestId={errorCode(error) === "http_error" ? null : "Retry or check the API status."}
        />
      ) : isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="stat-grid">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="stat-card">
                <Skeleton style={{ width: "55%", height: 12 }} />
                <Skeleton style={{ width: "35%", height: 28, marginTop: 10 }} />
              </div>
            ))}
          </div>
          <SkeletonCard rows={5} />
        </div>
      ) : data ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="stat-grid">
            <StatCard
              label="Open cases"
              value={String((data.cases_by_status["draft"] ?? 0) + (data.cases_by_status["in_review"] ?? 0))}
              hint={`${data.cases_total} total`}
              href="/cases"
            />
            <StatCard
              label="Documents"
              value={String(data.documents_total)}
              hint={
                data.documents_failed > 0
                  ? `${data.documents_failed} failed processing`
                  : "All processed cleanly"
              }
            />
            <StatCard
              label="Findings awaiting review"
              value={String(data.findings_by_status["needs_review"] ?? 0)}
              hint={`${data.findings_total} total findings`}
            />
            <StatCard
              label="AI analyses run"
              value={String(data.ai_runs_total)}
              hint="Model runs recorded with provenance"
            />
          </div>

          <div className="grid-main">
            <div className="stack">
              <section className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Findings by status</h2>
                    <p className="card-subtitle">Deterministic and AI-assisted screening results</p>
                  </div>
                </div>
                <div className="card-body" style={{ display: "flex", gap: 26, flexWrap: "wrap" }}>
                  {(["needs_review", "confirmed", "dismissed"] as const).map((status) => (
                    <div key={status}>
                      <p className="stat-label">{titleCase(status)}</p>
                      <p className="stat-value" style={{ fontSize: 22 }}>
                        {data.findings_by_status[status] ?? 0}
                      </p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="card">
                <div className="card-header">
                  <div>
                    <h2 className="card-title">Findings by severity</h2>
                    <p className="card-subtitle">Unresolved findings (confirmed + needs review)</p>
                  </div>
                  <Link className="btn btn-secondary btn-sm" href="/cases">
                    Review findings
                  </Link>
                </div>
                <div className="card-body" style={{ display: "flex", gap: 26, flexWrap: "wrap" }}>
                  {(["high", "medium", "low"] as const).map((severity) => (
                    <div key={severity}>
                      <p className="stat-label">{titleCase(severity)}</p>
                      <p className="stat-value" style={{ fontSize: 22 }}>
                        {data.findings_by_severity[severity] ?? 0}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <section className="card">
              <div className="card-header">
                <div>
                  <h2 className="card-title">Recent activity</h2>
                  <p className="card-subtitle">Audit trail (latest events)</p>
                </div>
              </div>
              <div className="card-body">
                {data.recent_activity.length === 0 ? (
                  <p className="text-muted text-small">No activity recorded yet.</p>
                ) : (
                  <AuditTimeline events={data.recent_activity} />
                )}
              </div>
            </section>
          </div>
        </div>
      ) : null}
    </PageFade>
  );
}
