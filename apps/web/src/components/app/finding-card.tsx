"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type { Finding, FindingStatus } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { OriginBadge, SeverityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { RevealItem } from "@/components/motion";

function ConfidenceBar({ value }: { value: number }) {
  return (
    <span className="confidence-bar">
      <span className="track" aria-hidden>
        <span className="fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
      {value}% confidence
    </span>
  );
}

export function FindingCard({ finding, readOnly }: { finding: Finding; readOnly: boolean }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState(finding.review_note ?? "");

  const reviewMutation = useMutation({
    mutationFn: (payload: { status: FindingStatus; note?: string }) =>
      api.patch<Finding>(`/findings/${finding.id}`, payload),
    onSuccess: async (_data, variables) => {
      toast.showToast(
        variables.status === "confirmed"
          ? "Finding confirmed and recorded."
          : variables.status === "dismissed"
            ? "Finding dismissed and recorded."
            : "Finding returned to needs review.",
        "success",
      );
      await queryClient.invalidateQueries({ queryKey: ["findings"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      await queryClient.invalidateQueries({ queryKey: ["report"] });
      setNoteOpen(false);
    },
    onError: (error) => {
      toast.showToast(errorMessage(error), "error");
    },
  });

  const pending = reviewMutation.isPending;

  return (
    <RevealItem>
      <article className="finding-card" data-status={finding.status}>
        <div className="finding-top">
          <div className="finding-badges">
            <SeverityBadge severity={finding.severity} />
            <StatusBadge status={finding.status} />
            <OriginBadge origin={finding.origin} />
          </div>
          <span className="mono text-muted">
            {finding.rule_id} · {finding.rule_version}
          </span>
        </div>

        <h3>{finding.title}</h3>
        <p className="explanation">{finding.explanation}</p>

        <div className="evidence-box">
          <div className="evidence-label">Evidence</div>
          {finding.evidence_kind === "quote" && finding.evidence_quote ? (
            <blockquote>&ldquo;{finding.evidence_quote}&rdquo;</blockquote>
          ) : (
            <span className="evidence-absent">
              Absence signal — the check looked for evidence and did not find it in the
              extracted text.
            </span>
          )}
          <div className="evidence-meta">
            {finding.page !== null ? <span>Page {finding.page}</span> : null}
            {finding.char_start !== null ? (
              <span className="mono">
                chars {finding.char_start}–{finding.char_end ?? "?"}
              </span>
            ) : null}
            <ConfidenceBar value={finding.confidence} />
            {finding.origin === "ai" && finding.ai_metadata?.model ? (
              <span className="mono">
                {finding.ai_metadata.provider}/{finding.ai_metadata.model}
              </span>
            ) : null}
          </div>
        </div>

        <div className="finding-footer">
          <div>
            {finding.reviewed_at ? (
              <p className="review-note">
                {titleCaseStatus(finding.status)} {formatDateTime(finding.reviewed_at)}
                {finding.review_note ? ` — “${finding.review_note}”` : ""}
              </p>
            ) : (
              <p className="review-note">Awaiting human review</p>
            )}
          </div>
          {!readOnly ? (
            <div className="review-actions">
              {noteOpen ? (
                <span style={{ display: "inline-flex", gap: 6 }}>
                  <input
                    className="input"
                    style={{ width: 210, padding: "6px 10px", fontSize: 12 }}
                    placeholder="Review note (optional)"
                    aria-label="Review note"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        reviewMutation.mutate({ status: "confirmed", note: note || undefined });
                      }
                    }}
                  />
                  <Button
                    size="sm"
                    variant="primary"
                    loading={pending}
                    onClick={() => reviewMutation.mutate({ status: "confirmed", note: note || undefined })}
                  >
                    Confirm
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setNoteOpen(false)}>
                    Cancel
                  </Button>
                </span>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="primary"
                    loading={pending}
                    disabled={finding.status === "confirmed"}
                    onClick={() => reviewMutation.mutate({ status: "confirmed" })}
                  >
                    Confirm
                  </Button>
                  <Button
                    size="sm"
                    variant="danger-secondary"
                    loading={pending}
                    disabled={finding.status === "dismissed"}
                    onClick={() => reviewMutation.mutate({ status: "dismissed", note: note || undefined })}
                  >
                    Dismiss
                  </Button>
                  {finding.status !== "needs_review" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={pending}
                      onClick={() => reviewMutation.mutate({ status: "needs_review" })}
                    >
                      Reopen
                    </Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => setNoteOpen(true)}>
                      Add note
                    </Button>
                  )}
                </>
              )}
            </div>
          ) : null}
        </div>
      </article>
    </RevealItem>
  );
}

function titleCaseStatus(status: FindingStatus): string {
  if (status === "confirmed") return "Confirmed";
  if (status === "dismissed") return "Dismissed";
  return "Reopened";
}
