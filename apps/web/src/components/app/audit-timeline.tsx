import type { AuditEvent } from "@/lib/types";
import { actionLabel, formatDateTime } from "@/lib/format";

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ul className="timeline">
      {events.map((event) => (
        <li key={event.id}>
          <div className="event-action">{actionLabel(event.action)}</div>
          <div className="event-meta">
            {event.actor_label} · {formatDateTime(event.created_at)}
          </div>
          {Object.keys(event.detail).length > 0 ? (
            <div className="event-detail">{JSON.stringify(event.detail)}</div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
