"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Client-side error boundary: surface in console for diagnostics only.
    console.error(error);
  }, [error]);

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div style={{ textAlign: "center", maxWidth: 440 }}>
        <h1 style={{ fontSize: 20, letterSpacing: "-0.02em" }}>Something went wrong</h1>
        <p style={{ color: "var(--ink-500)", fontSize: 13, marginTop: 8, lineHeight: 1.6 }}>
          An unexpected error occurred while rendering this page. Your data is safe — retry the
          action or return to the dashboard.
        </p>
        {error.digest ? (
          <p className="mono text-muted" style={{ marginTop: 8 }}>
            Error reference: {error.digest}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 18 }}>
          <button className="btn btn-primary" onClick={reset}>
            Try again
          </button>
          <a className="btn btn-secondary" href="/dashboard">
            Go to dashboard
          </a>
        </div>
      </div>
    </main>
  );
}
