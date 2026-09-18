"use client";

import Link from "next/link";
import { use } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage, errorCode } from "@/lib/api";
import type { Case } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";
import { CaseStatusBadge } from "@/components/ui/badge";
import { InlineError, Skeleton } from "@/components/ui/feedback";
import { IconDocType, IconFile, IconFlag, IconClock, IconShield } from "@/components/ui/icon";

const TABS = [
  { segment: "", label: "Overview", icon: IconDocType },
  { segment: "findings", label: "Findings", icon: IconFlag },
  { segment: "documents", label: "Documents", icon: IconFile },
  { segment: "report", label: "Report", icon: IconShield },
  { segment: "audit", label: "Audit trail", icon: IconClock },
];

export function CaseTabs({ caseId }: { caseId: string }) {
  const pathname = usePathname();
  const base = `/cases/${caseId}`;
  const currentSegment = pathname === base ? "" : (pathname.replace(`${base}/`, "").split("/")[0] ?? "");

  return (
    <nav className="tabs" aria-label="Case sections">
      {TABS.map((tab) => {
        const href = tab.segment ? `${base}/${tab.segment}` : base;
        const active = currentSegment === tab.segment;
        return (
          <Link
            key={tab.segment || "overview"}
            href={href}
            className="tab"
            data-active={active || undefined}
            aria-current={active ? "page" : undefined}
          >
            <tab.icon size={15} />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: queryKeys.case(caseId),
    queryFn: () => api.get<Case>(`/cases/${caseId}`),
  });
}

export default function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = use(params);
  const { data: caseData, isLoading, isError, error } = useCase(caseId);

  return (
    <div>
      {isError ? (
        <InlineError
          message={
            errorCode(error) === "not_found"
              ? "This case does not exist or you do not have access to it."
              : errorMessage(error)
          }
          requestId={null}
        />
      ) : null}
      {isLoading ? (
        <div style={{ marginBottom: 20 }}>
          <Skeleton style={{ width: "45%", height: 24 }} />
          <Skeleton style={{ width: "70%", height: 14, marginTop: 8 }} />
        </div>
      ) : caseData ? (
        <div className="page-header" style={{ marginBottom: 14 }}>
          <div>
            <p className="kicker">Case {caseData.display_code}</p>
            <h1 style={{ fontSize: 21 }}>{caseData.title}</h1>
            <p className="page-description">
              {caseData.establishment_name || "No establishment recorded"}
              {caseData.establishment_reference ? ` · Ref ${caseData.establishment_reference}` : ""}
            </p>
          </div>
          <div className="page-actions">
            <CaseStatusBadge status={caseData.status} />
            <Link className="btn btn-secondary btn-sm" href="/cases">
              All cases
            </Link>
          </div>
        </div>
      ) : null}
      <CaseTabs caseId={caseId} />
      <div style={{ marginTop: 20 }}>{children}</div>
    </div>
  );
}
