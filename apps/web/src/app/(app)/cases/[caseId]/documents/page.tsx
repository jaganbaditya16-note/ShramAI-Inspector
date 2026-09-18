"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type { DocumentListResponse, InspectorDocument } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";
import { PageFade } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { DocumentStatusBadge, JobStatusBadge } from "@/components/ui/badge";
import { EmptyState, InlineError, Skeleton } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { formatBytes, formatDateTime, titleCase } from "@/lib/format";

export default function DocumentsPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [reprocessTarget, setReprocessTarget] = useState<InspectorDocument | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InspectorDocument | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.documents(caseId),
    queryFn: () => api.get<DocumentListResponse>(`/cases/${caseId}/documents?limit=100`),
    refetchInterval: (query) => {
      const statuses = query.state.data?.items.map((item) => item.status) ?? [];
      return statuses.some((status) => status === "queued" || status === "processing") ? 2000 : false;
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: (documentId: string) => api.post(`/documents/${documentId}/reprocess`),
    onSuccess: async () => {
      toast.showToast("Reprocessing started.", "success");
      setReprocessTarget(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.findings(caseId) });
    },
    onError: (mutationError) => toast.showToast(errorMessage(mutationError), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => api.delete<void>(`/documents/${documentId}`),
    onSuccess: async () => {
      // The stored file is removed server-side first; the row, findings and
      // model runs go with it. Audit events are preserved.
      toast.showToast("Document deleted.", "success");
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.findings(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.case(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.audit(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
    onError: (mutationError) => toast.showToast(errorMessage(mutationError), "error"),
  });

  return (
    <PageFade>
      {isError ? (
        <InlineError message={errorMessage(error)} requestId={null} />
      ) : isLoading ? (
        <div className="card">
          <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} style={{ height: 40, width: "100%" }} />
            ))}
          </div>
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No documents uploaded"
            description="Upload PDF, PNG or JPEG labour documents from the Overview tab. Every upload is validated and screened automatically."
          />
        </div>
      ) : data ? (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="table">
            <caption className="visually-hidden">Documents in this case</caption>
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">Type</th>
                <th scope="col">Status</th>
                <th scope="col">Job</th>
                <th scope="col">Uploaded</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((document) => (
                <tr key={document.id}>
                  <td>
                    <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
                      <span className="doc-icon" aria-hidden>
                        {document.content_type.includes("pdf")
                          ? "PDF"
                          : document.content_type.includes("png")
                            ? "PNG"
                            : "JPG"}
                      </span>
                      <div>
                        <p className="doc-name">{document.original_filename}</p>
                        <p className="doc-sub">
                          {formatBytes(document.size_bytes)}
                          {document.page_count ? ` · ${document.page_count} pages` : ""}
                          {document.text_chars
                            ? ` · ${document.text_chars.toLocaleString()} chars (${document.extraction_method})`
                            : ""}
                          {" · "}
                          <a href={`/api/v1/documents/${document.id}/download`} className="text-small">
                            download
                          </a>
                        </p>
                      </div>
                    </div>
                  </td>
                  <td>
                    {titleCase(document.doc_type)}
                    <span className="doc-sub" style={{ display: "block" }}>
                      {document.doc_type_confidence}% confidence
                    </span>
                  </td>
                  <td>
                    <DocumentStatusBadge status={document.status} />
                    {document.error ? (
                      <p className="doc-sub" style={{ color: "var(--danger-700)", maxWidth: 220 }}>
                        {document.error}
                      </p>
                    ) : null}
                  </td>
                  <td>
                    {document.job ? (
                      <>
                        <JobStatusBadge status={document.job.status} />
                        {document.job.detail?.ai_status ? (
                          <p className="doc-sub">AI: {document.job.detail.ai_status}</p>
                        ) : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="text-small text-muted">{formatDateTime(document.created_at)}</td>
                  <td>
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={document.status === "queued" || document.status === "processing"}
                        onClick={() => setReprocessTarget(document)}
                      >
                        Reprocess
                      </Button>
                      <Button
                        size="sm"
                        variant="danger-secondary"
                        disabled={document.status === "queued" || document.status === "processing"}
                        onClick={() => setDeleteTarget(document)}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <Dialog
        open={reprocessTarget !== null}
        onClose={() => setReprocessTarget(null)}
        title="Reprocess document"
        description="Extraction, classification and screening run again. Existing review decisions on matching evidence are preserved."
      >
        <p className="text-small text-muted">
          {reprocessTarget?.original_filename}
        </p>
        <div className="dialog-actions">
          <Button variant="ghost" onClick={() => setReprocessTarget(null)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={reprocessMutation.isPending}
            onClick={() => reprocessTarget && reprocessMutation.mutate(reprocessTarget.id)}
          >
            Start reprocessing
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete document"
        description="The stored file, extracted text, findings and model runs are permanently removed. Audit events are kept. This cannot be undone."
      >
        <p className="text-small text-muted">
          {deleteTarget?.original_filename}
        </p>
        <div className="dialog-actions">
          <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
            Cancel
          </Button>
          <Button
            variant="danger-secondary"
            loading={deleteMutation.isPending}
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
          >
            Delete document
          </Button>
        </div>
      </Dialog>
    </PageFade>
  );
}
