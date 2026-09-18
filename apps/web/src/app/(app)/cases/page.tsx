"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, ApiError } from "@/lib/api";
import type { Case, CaseListResponse } from "@/lib/types";
import { PageHeader } from "@/components/app/page-header";
import { PageFade, RevealItem, RevealList } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { CaseStatusBadge } from "@/components/ui/badge";
import { EmptyState, InlineError, Skeleton } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { queryKeys } from "@/lib/query-keys";
import { formatDateTime } from "@/lib/format";

export default function CasesPage() {
  const [statusFilter, setStatusFilter] = useState<"" | "draft" | "in_review" | "closed">("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: queryKeys.cases({ status: statusFilter || undefined, search: search || undefined }),
    queryFn: () =>
      api.get<CaseListResponse>(
        `/cases?limit=50${statusFilter ? `&status=${statusFilter}` : ""}${
          search ? `&search=${encodeURIComponent(search)}` : ""
        }`,
      ),
  });

  return (
    <PageFade>
      <PageHeader
        kicker="Inspection cases"
        title="Cases"
        description="Each case bundles the documents, findings and review decisions for one inspection."
        actions={
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New case
          </Button>
        }
      />

      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div className="segmented" role="group" aria-label="Filter cases by status">
          {(["", "draft", "in_review", "closed"] as const).map((value) => (
            <button
              key={value || "all"}
              type="button"
              data-active={statusFilter === value || undefined}
              aria-pressed={statusFilter === value}
              onClick={() => setStatusFilter(value)}
            >
              {value ? titleCaseFilter(value) : "All"}
            </button>
          ))}
        </div>
        <div style={{ position: "relative", flex: 1, maxWidth: 320 }}>
          <input
            className="input"
            style={{ paddingLeft: 34 }}
            placeholder="Search case titles…"
            aria-label="Search case titles"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--ink-400)"
            strokeWidth="2"
            strokeLinecap="round"
            style={{ position: "absolute", left: 11, top: 11 }}
            aria-hidden
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
        </div>
      </div>

      {isError ? (
        <InlineError message={errorMessage(error)} requestId={null} />
      ) : isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="card" style={{ padding: 18 }}>
              <Skeleton style={{ width: "40%", height: 16 }} />
              <Skeleton style={{ width: "70%", height: 12, marginTop: 10 }} />
            </div>
          ))}
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="card">
          <EmptyState
            title="No inspection cases yet"
            description="Create your first case to start uploading labour documents and screening them for evidence gaps."
            action={
              <Button variant="primary" onClick={() => setCreateOpen(true)}>
                Create a case
              </Button>
            }
          />
        </div>
      ) : data ? (
        <>
          <p className="text-small text-muted" style={{ marginBottom: 10 }} aria-live="polite">
            {data.meta.total} case{data.meta.total === 1 ? "" : "s"}
            {isFetching ? " · refreshing…" : ""}
          </p>
          <RevealList>
            <div className="case-list">
              {data.items.map((item) => (
                <RevealItem key={item.id}>
                  <Link className="case-card" href={`/cases/${item.id}`}>
                    <div className="case-card-top">
                      <div>
                        <h3>{item.title}</h3>
                        <p className="code">{item.display_code}</p>
                      </div>
                      <CaseStatusBadge status={item.status} />
                    </div>
                    <div className="case-card-meta">
                      <span>
                        Documents <strong>{item.document_count}</strong>
                      </span>
                      <span>
                        Findings <strong>{item.finding_count}</strong>
                      </span>
                      <span>
                        Created <strong>{formatDateTime(item.created_at)}</strong>
                      </span>
                      {item.establishment_name ? <span>{item.establishment_name}</span> : null}
                    </div>
                  </Link>
                </RevealItem>
              ))}
            </div>
          </RevealList>
        </>
      ) : null}

      <CreateCaseDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </PageFade>
  );
}

function titleCaseFilter(value: "draft" | "in_review" | "closed"): string {
  return { draft: "Draft", in_review: "In review", closed: "Closed" }[value];
}

function CreateCaseDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [establishment, setEstablishment] = useState("");
  const [reference, setReference] = useState("");
  const [validation, setValidation] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: { title: string; establishment_name: string; establishment_reference: string }) =>
      api.post<Case>("/cases", payload),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["cases"] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      toast.showToast(`Case ${created.display_code} created.`, "success");
      setTitle("");
      setEstablishment("");
      setReference("");
      onClose();
    },
    onError: (mutationError) => {
      if (mutationError instanceof ApiError && mutationError.status === 422) {
        setValidation("Title must be at least 3 characters.");
      } else {
        toast.showToast(errorMessage(mutationError), "error");
      }
    },
  });

  function submit() {
    setValidation(null);
    if (title.trim().length < 3) {
      setValidation("Enter a case title with at least 3 characters.");
      return;
    }
    mutation.mutate({
      title: title.trim(),
      establishment_name: establishment.trim(),
      establishment_reference: reference.trim(),
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create inspection case"
      description="Cases group documents and findings for one establishment inspection."
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <label className="field-label" htmlFor="case-title">
            Case title
          </label>
          <input
            id="case-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Site B wage register review"
            maxLength={200}
          />
          {validation ? (
            <p className="field-error" role="alert">
              {validation}
            </p>
          ) : null}
        </div>
        <div>
          <label className="field-label" htmlFor="case-establishment">
            Establishment name (optional)
          </label>
          <input
            id="case-establishment"
            className="input"
            value={establishment}
            onChange={(event) => setEstablishment(event.target.value)}
            placeholder="e.g. Ashok Industries Pvt. Ltd."
            maxLength={200}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="case-reference">
            Establishment reference (optional)
          </label>
          <input
            id="case-reference"
            className="input"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder="e.g. SYN-000111"
            maxLength={120}
          />
        </div>
      </div>
      <div className="dialog-actions">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" loading={mutation.isPending} onClick={submit}>
          Create case
        </Button>
      </div>
    </Dialog>
  );
}
