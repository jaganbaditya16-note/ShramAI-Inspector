import type { ReactNode } from "react";

export function Skeleton({ style }: { style?: React.CSSProperties }) {
  return <div className="skeleton" style={style} aria-hidden />;
}

export function SkeletonCard({ rows = 3 }: { rows?: number }) {
  return (
    <div className="card">
      <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Skeleton style={{ width: "35%", height: 18 }} />
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} style={{ width: `${88 - index * 9}%`, height: 13 }} />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
          <path d="M14 3v5h5" />
        </svg>
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function InlineError({ message, requestId }: { message: string; requestId?: string | null }) {
  return (
    <div className="inline-error" role="alert">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden style={{ flex: "none", marginTop: 1 }}>
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      </svg>
      <div>
        {message}
        {requestId ? <span className="request-id">Request ID: {requestId}</span> : null}
      </div>
    </div>
  );
}
