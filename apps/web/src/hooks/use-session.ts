"use client";

import { useQuery } from "@tanstack/react-query";
import { api, errorCode } from "@/lib/api";
import type { HealthStatus, SessionUser } from "@/lib/types";
import { queryKeys } from "@/lib/query-keys";

export function useSession() {
  const query = useQuery({
    queryKey: queryKeys.session,
    queryFn: () => api.get<SessionUser>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });

  return {
    user: query.data ?? null,
    isLoading: query.isLoading,
    /** True when the API demands login and no session exists. */
    needsLogin: query.isError && errorCode(query.error) === "unauthorized",
    isError: query.isError,
    error: query.error,
  };
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.get<HealthStatus>("/health"),
    staleTime: 15_000,
    retry: 1,
  });
}
