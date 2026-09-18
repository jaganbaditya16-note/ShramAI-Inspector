"use client";

import { use, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type { FindingListResponse, FindingSeverity, FindingStatus, FindingOrigin } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";
import { PageFade, RevealList } from "@/components/motion";
import { FindingCard } from "@/components/app/finding-card";
import { InlineError, EmptyState, SkeletonCard } from "@/components/ui/feedback";
import { useSession } from "@/hooks/use-session";

type SeverityFilter = "" | FindingSeverity;
type StatusFilter = "" | FindingStatus;

export default function FindingsPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const { user } = useSession();
  const [severity, setSeverity] = useState<SeverityFilter>("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [origin, setOrigin] = useState<FindingOrigin | "">("");

  const filters = {
    severity: severity || undefined,
    status: status || undefined,
    origin: origin || undefined,
  };
  const searchParams = new URLSearchParams({ limit: "100", sort: "-severity" });
  if (filters.severity) searchParams.set("severity", filters.severity);
  if (filters.status) searchParams.set("status", filters.status);
  if (filters.origin) searchParams.set("origin", filters.origin);

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: queryKeys.findings(caseId, filters),
    queryFn: () => api.get<FindingListResponse>(`/cases/${caseId}/findings?${searchParams.toString()}`),
  });

  const readOnly = user?.role === "viewer";

  return (
    <PageFade>
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div className="segmented" role="group" aria-label="Filter by severity">
          {(["", "high", "medium", "low"] as const).map((value) => (
            <button
              key={value || "all-sev"}
              type="button"
              data-active={severity === value || undefined}
              aria-pressed={severity === value}
              onClick={() => setSeverity(value)}
            >
              {value ? SeverityLabel[value] : "All severities"}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Filter by review status">
          {(["", "needs_review", "confirmed", "dismissed"] as const).map((value) => (
            <button
              key={value || "all-status"}
              type="button"
              data-active={status === value || undefined}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {value ? StatusLabel[value] : "All states"}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="Filter by origin">
          {(["", "rule", "ai"] as const).map((value) => (
            <button
              key={value || "all-origin"}
              type="button"
              data-active={origin === value || undefined}
              aria-pressed={origin === value}
              onClick={() => setOrigin(value)}
            >
              {value === "" ? "All origins" : value === "rule" ? "Rule checks" : "AI-assisted"}
            </button>
          ))}
        </div>
      </div>

      {isError ? (
        <InlineError message={errorMessage(error)} requestId={null} />
      ) : isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No findings match these filters"
            description="Upload documents in the Overview tab, or relax the filters above. Findings appear here with evidence, confidence and provenance."
            action={
              <button className="btn btn-secondary" onClick={() => { setSeverity(""); setStatus(""); setOrigin(""); }}>
                Clear filters
              </button>
            }
          />
        </div>
      ) : data ? (
        <>
          <p className="text-small text-muted" style={{ marginBottom: 12 }} aria-live="polite">
            {data.meta.total} finding{data.meta.total === 1 ? "" : "s"}
            {isFetching ? " · refreshing…" : ""}
            {" · "}
            <button className="btn btn-ghost btn-sm" onClick={() => void refetch()}>
              Refresh
            </button>
          </p>
          <RevealList>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {data.items.map((finding) => (
                <FindingCard key={finding.id} finding={finding} readOnly={readOnly} />
              ))}
            </div>
          </RevealList>
        </>
      ) : null}
    </PageFade>
  );
}

const SeverityLabel: Record<FindingSeverity, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const StatusLabel: Record<FindingStatus, string> = {
  needs_review: "Needs review",
  confirmed: "Confirmed",
  dismissed: "Dismissed",
};
