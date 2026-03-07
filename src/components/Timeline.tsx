import type { SearchEvent } from "../types";

function eventTypeLabel(type: string) {
  const mapping: Record<string, string> = {
    search_started: "\u4efb\u52a1\u521b\u5efa",
    fetching_jobs: "\u6293\u53d6\u804c\u4f4d",
    rule_ranked: "\u89c4\u5219\u7b5b\u9009",
    llm_enriched: "\u6a21\u578b\u8865\u5145",
    ready: "\u4efb\u52a1\u5b8c\u6210",
  };

  return mapping[type] || type;
}

interface TimelineProps {
  events: SearchEvent[];
}

export function Timeline({ events }: TimelineProps) {
  return (
    <div className="rounded-[28px] border border-ink/10 bg-shell/90 p-5 shadow-console">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.22em] text-slate">
          {"\u641c\u7d22\u65f6\u95f4\u7ebf"}
        </p>
        <p className="text-xs text-slate">
          {events.length} {"\u6761\u4e8b\u4ef6"}
        </p>
      </div>
      <div className="mt-5 space-y-4">
        {events.length === 0 ? (
          <p className="text-sm text-slate">
            {
              "\u6682\u65e0\u4e8b\u4ef6\u6d41\u3002\u4efb\u52a1\u542f\u52a8\u540e\uff0c\u641c\u7d22\u6d41\u6c34\u7ebf\u7684\u8fdb\u5ea6\u4f1a\u5b9e\u65f6\u663e\u793a\u5728\u8fd9\u91cc\u3002"
            }
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
                {eventTypeLabel(event.type)} ·{" "}
                {new Date(event.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

