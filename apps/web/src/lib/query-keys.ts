/** Centralised react-query keys. */

import type { FindingStatus, FindingSeverity, FindingOrigin } from "./types";

export const queryKeys = {
  session: ["session"] as const,
  health: ["health"] as const,
  dashboard: ["dashboard"] as const,
  cases: (params?: { status?: string; search?: string }) => ["cases", params ?? {}] as const,
  case: (caseId: string) => ["case", caseId] as const,
  findings: (
    caseId: string,
    filters?: { status?: FindingStatus; severity?: FindingSeverity; origin?: FindingOrigin },
  ) => ["findings", caseId, filters ?? {}] as const,
  documents: (caseId: string) => ["documents", caseId] as const,
  document: (documentId: string) => ["document", documentId] as const,
  report: (caseId: string) => ["report", caseId] as const,
  audit: (caseId: string) => ["audit", caseId] as const,
};
