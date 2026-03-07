import type { SearchEvent } from "../types";

interface TimelineProps {
  events: SearchEvent[];
}

export function Timeline({ events }: TimelineProps) {
  return (
    <div className="rounded-[28px] border border-ink/10 bg-shell/90 p-5 shadow-console">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.22em] text-slate">
          Search timeline
        </p>
        <p className="text-xs text-slate">{events.length} events</p>
      </div>
      <div className="mt-5 space-y-4">
        {events.length === 0 ? (
          <p className="text-sm text-slate">
            No stream yet. Once a session starts, pipeline events land here.
          </p>
        ) : null}
        {events.map((event) => (
          <div
            key={`${event.type}-${event.timestamp}`}
            className="flex gap-4 border-l border-ink/10 pl-4"
          >
            <div className="mt-1 h-2.5 w-2.5 rounded-full bg-ember" />
            <div>
              <p className="text-sm font-semibold text-ink">{event.message}</p>
              <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate">
                {event.type} · {new Date(event.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

