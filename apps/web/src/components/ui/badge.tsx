import type { FindingOrigin, FindingSeverity, FindingStatus, CaseStatus } from "@/lib/types";
import { titleCase } from "@/lib/format";

export function SeverityBadge({ severity }: { severity: FindingSeverity }) {
  const cls =
    severity === "high" ? "badge-danger" : severity === "medium" ? "badge-warning" : "badge-neutral";
  return (
    <span className={`badge ${cls}`}>
      <span className="severity-dot" aria-hidden />
      {titleCase(severity)}
    </span>
  );
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const map: Record<FindingStatus, string> = {
    needs_review: "badge-warning",
    confirmed: "badge-danger",
    dismissed: "badge-neutral",
  };
  return <span className={`badge ${map[status]}`}>{titleCase(status)}</span>;
}

export function OriginBadge({ origin }: { origin: FindingOrigin }) {
  return (
    <span className={`badge ${origin === "ai" ? "badge-purple" : "badge-accent"}`}>
      {origin === "ai" ? "AI-assisted" : "Rule check"}
    </span>
  );
}

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  const map: Record<CaseStatus, string> = {
    draft: "badge-neutral",
    in_review: "badge-accent",
    closed: "badge-success",
  };
  return <span className={`badge ${map[status]}`}>{titleCase(status)}</span>;
}

const documentStatusMap: Record<string, { cls: string; label: string }> = {
  queued: { cls: "badge-neutral", label: "Queued" },
  processing: { cls: "badge-accent", label: "Processing" },
  processed: { cls: "badge-success", label: "Processed" },
  failed: { cls: "badge-danger", label: "Failed" },
};

export function DocumentStatusBadge({ status }: { status: string }) {
  const entry = documentStatusMap[status] ?? { cls: "badge-neutral", label: status };
  return <span className={`badge ${entry.cls}`}>{entry.label}</span>;
}

export function JobStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: "badge-neutral",
    running: "badge-accent",
    succeeded: "badge-success",
    failed: "badge-danger",
  };
  return <span className={`badge ${map[status] ?? "badge-neutral"}`}>{titleCase(status)}</span>;
}
