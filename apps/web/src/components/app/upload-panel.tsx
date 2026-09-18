"use client";

import { useCallback, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { UploadAccepted } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { queryKeys } from "@/lib/query-keys";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";
const MAX_MB = 25;

async function pollUntilDone(documentId: string): Promise<UploadAccepted["document"]> {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const document = await api.get<UploadAccepted["document"]>(`/documents/${documentId}`);
    if (document.status === "processed" || document.status === "failed") {
      return document;
    }
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  throw new ApiError(0, "timeout", "Processing is taking longer than expected. Check back shortly.", "-");
}

export function UploadPanel({ caseId, disabled }: { caseId: string; disabled?: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState<"idle" | "uploading" | "processing">("idle");

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      setPhase("uploading");
      const form = new FormData();
      form.append("file", file);
      const accepted = await api.post<UploadAccepted>(`/cases/${caseId}/documents`, form);
      setPhase("processing");
      const finalDocument = await pollUntilDone(accepted.document.id);
      return finalDocument;
    },
    onSuccess: async (document) => {
      setPhase("idle");
      if (inputRef.current) inputRef.current.value = "";
      if (document.status === "failed") {
        toast.showToast(`Processing failed for ${document.original_filename}: ${document.error ?? "unknown error"}`, "error");
      } else {
        toast.showToast(
          `${document.original_filename} processed (${document.doc_type}, ${document.text_chars.toLocaleString()} characters extracted).`,
          "success",
        );
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.findings(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.case(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.audit(caseId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
    onError: (error) => {
      setPhase("idle");
      if (inputRef.current) inputRef.current.value = "";
      toast.showToast(errorMessage(error), "error");
    },
  });

  const validateAndUpload = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      const okType = /\.(pdf|png|jpe?g)$/i.test(file.name);
      if (!okType) {
        toast.showToast("Unsupported file type. Upload a PDF, PNG or JPEG document.", "error");
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        toast.showToast(`File exceeds the ${MAX_MB} MB limit.`, "error");
        return;
      }
      mutation.mutate(file);
    },
    [mutation, toast],
  );

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    validateAndUpload(event.dataTransfer.files?.[0]);
  };

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    validateAndUpload(event.target.files?.[0]);
  };

  const busy = phase !== "idle";

  return (
    <div>
      <label
        className="dropzone"
        data-dragging={dragging || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          disabled={disabled || busy}
          onChange={onChange}
        />
        {phase === "uploading" ? (
          <strong>Uploading document…</strong>
        ) : phase === "processing" ? (
          <strong>Extracting text and screening…</strong>
        ) : (
          <>
            <strong>Drop a labour document here, or click to browse</strong>
            <small>PDF, PNG or JPEG · up to {MAX_MB} MB · validated and screened server-side</small>
          </>
        )}
      </label>
      {busy ? (
        <div className="upload-progress" aria-live="polite">
          <div className="bar">
            <div className="fill" style={{ width: phase === "uploading" ? "35%" : "85%" }} />
          </div>
          <p>
            {phase === "uploading"
              ? "Validating and uploading…"
              : "Extraction → classification → deterministic rules → AI screening…"}
          </p>
        </div>
      ) : (
        <p className="text-small text-muted" style={{ marginTop: 10 }}>
          Only synthetic or authorised documents should be uploaded. Every file is validated
          (type, signature, size) before processing.
        </p>
      )}
      {busy ? (
        <Button variant="ghost" size="sm" onClick={() => mutation.reset()} disabled>
          <span className="spinner" aria-hidden />
          Working…
        </Button>
      ) : null}
    </div>
  );
}
