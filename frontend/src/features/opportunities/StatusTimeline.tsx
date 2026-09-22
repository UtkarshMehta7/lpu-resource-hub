import type { Application } from "./api";
import { APPLICATION_STATUS_LABEL } from "./labels";

export function StatusTimeline({ events }: { events: Application["events"] }) {
  return (
    <ol className="mt-2 space-y-2 border-l border-line pl-4">
      {events.map((event, index) => (
        <li key={`${event.status}-${index}`} className="text-sm">
          <span className="font-medium">{APPLICATION_STATUS_LABEL[event.status]}</span>
          <span className="text-xs text-ink-muted">
            {" "}
            · {new Date(event.created_at).toLocaleString()}
          </span>
          {event.note ? <p className="text-xs text-ink-muted">“{event.note}”</p> : null}
        </li>
      ))}
    </ol>
  );
}
