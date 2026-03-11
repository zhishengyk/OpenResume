import type { SearchEvent } from "../types";

function eventTypeLabel(type: string) {
  const mapping: Record<string, string> = {
    search_started: "任务创建",
    search_restarted: "重新搜索",
    fetching_jobs: "抓取职位",
    fetch_force_refresh: "实时抓取",
    fetch_cache_hit: "缓存命中",
    code_cleaned: "职位清洗",
    rule_ranked: "规则排序",
    llm_started: "模型分析开始",
    llm_enriched: "模型分析完成",
    llm_failed: "模型分析失败",
    verification_opened: "打开验证",
    blocked: "平台阻塞",
    failed: "任务失败",
    ready: "结果可用",
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
        <p className="text-xs uppercase tracking-[0.22em] text-slate">搜索时间线</p>
        <p className="text-xs text-slate">{events.length} 条事件</p>
      </div>
      <div className="mt-5 space-y-4">
        {events.length === 0 ? (
          <p className="text-sm text-slate">
            暂无事件流。任务启动后，搜索流水线进度会实时显示在这里。
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
                {eventTypeLabel(event.type)} | {new Date(event.timestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
