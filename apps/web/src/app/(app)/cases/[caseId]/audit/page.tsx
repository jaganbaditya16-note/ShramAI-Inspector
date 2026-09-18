"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type { AuditListResponse } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";
import { PageFade } from "@/components/motion";
import { InlineError, EmptyState } from "@/components/ui/feedback";
import { AuditTimeline } from "@/components/app/audit-timeline";
import { Button } from "@/components/ui/button";

export default function AuditPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: queryKeys.audit(caseId),
    queryFn: () => api.get<AuditListResponse>(`/cases/${caseId}/audit?limit=100`),
  });

  return (
    <PageFade>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 17, fontWeight: 700 }}>Audit trail</h2>
          <p className="page-description" style={{ marginTop: 4 }}>
            Append-only record of every action on this case, with actor and request
            correlation. Document contents are never written to the audit log.
          </p>
        </div>
        <Button variant="ghost" onClick={() => void refetch()} disabled={isFetching}>
          Refresh
        </Button>
      </div>

      {isError ? (
        <InlineError message={errorMessage(error)} requestId={null} />
      ) : isLoading ? (
        <p className="text-muted text-small">Loading audit trail…</p>
      ) : data && data.items.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No audit events yet"
            description="Actions on this case (uploads, processing, review decisions, reports) will be recorded here automatically."
          />
        </div>
      ) : data ? (
        <div className="card">
          <div className="card-body">
            <AuditTimeline events={data.items} />
          </div>
        </div>
      ) : null}
    </PageFade>
  );
}
