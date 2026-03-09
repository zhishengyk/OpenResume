import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { MetricCard } from "../components/MetricCard";
import { StatusPill } from "../components/StatusPill";
import { Timeline } from "../components/Timeline";
import { useEventStream } from "../hooks/useEventStream";
import { api } from "../lib/api";
import { pillLabel } from "../lib/utils";
import type { SearchEvent } from "../types";

async function openVerificationPopup(url: string, title: string) {
  if (window.openResumeDesktop?.openVerificationWindow) {
    await window.openResumeDesktop.openVerificationWindow(url, title);
    return;
  }
  if (window.openResumeDesktop?.openExternal) {
    window.openResumeDesktop.openExternal(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export function ResultsPage() {
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<SearchEvent[]>([]);
  const sessionId = params.get("session") || undefined;

  useEffect(() => {
    setEvents([]);
  }, [sessionId]);

  const sessionQuery = useQuery({
    queryKey: ["search-session", sessionId],
    queryFn: () => api.getSearchSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: sessionId ? 2000 : false,
  });

  const matchesQuery = useQuery({
    queryKey: ["search-matches", sessionId],
    queryFn: () => api.getSearchMatches(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: sessionId ? 2500 : false,
  });

  const openVerificationMutation = useMutation({
    mutationFn: async () => {
      const payload = await api.openSearchVerification(sessionId!);
      await openVerificationPopup(payload.url, payload.title);
      return payload;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    },
  });

  const retrySearchMutation = useMutation({
    mutationFn: () => api.retrySearchSession(sessionId!),
    onSuccess: () => {
      setEvents([]);
      queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
    },
  });

  useEventStream(sessionId, (event) => {
    setEvents((current) => {
      if (
        current.some(
          (item) => item.type === event.type && item.timestamp === event.timestamp,
        )
      ) {
        return current;
      }
      return [...current, event];
    });
    queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
  });

  const isBlocked = sessionQuery.data?.status === "blocked";
  const isRunning = sessionQuery.data?.status === "running";

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate">
              搜索任务
            </p>
            <h1 className="mt-3 font-display text-5xl text-ink">
              先做代码清洗，再做模型精排，最后进入官网流程。
            </h1>
          </div>
          {sessionQuery.data ? <StatusPill>{sessionQuery.data.status}</StatusPill> : null}
        </div>
        {sessionQuery.data?.summary ? (
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
            {sessionQuery.data.summary}
          </p>
        ) : null}
      </section>

      {sessionQuery.data?.analysis_degraded && sessionQuery.data.analysis_notice ? (
        <section className="rounded-[32px] border border-amber-500/30 bg-amber-500/10 p-6 shadow-console">
          <p className="text-sm leading-7 text-ink">
            {sessionQuery.data.analysis_notice}
          </p>
        </section>
      ) : null}

      {isBlocked ? (
        <section className="rounded-[32px] border border-ember/30 bg-ember/10 p-6 shadow-console">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-ember">
                <AlertTriangle size={16} />
                需要验证
              </p>
              <h2 className="mt-3 font-display text-3xl text-ink">
                先在小窗里完成验证，再继续当前搜索流程。
              </h2>
              <p className="mt-3 text-sm leading-7 text-slate">
                {sessionQuery.data?.blocked_reason || "当前搜索因为平台要求人工验证而暂停。"}
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => openVerificationMutation.mutate()}
                disabled={openVerificationMutation.isPending || !sessionId}
              >
                <ShieldCheck size={16} />
                {openVerificationMutation.isPending ? "正在打开小窗..." : "打开验证小窗"}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => retrySearchMutation.mutate()}
                disabled={retrySearchMutation.isPending || !sessionId}
              >
                <RefreshCw size={16} />
                {retrySearchMutation.isPending ? "正在重试..." : "验证后继续"}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-3">
        <MetricCard
          label="可见岗位"
          value={String(matchesQuery.data?.length ?? 0)}
          hint="只有通过代码清洗的岗位才会进入结果列表。"
        />
        <MetricCard
          label="搜索平台"
          value={
            sessionQuery.data?.requested_platforms
              ?.map((platform) => pillLabel(platform))
              .join("、") || "--"
          }
          hint="搜索任务会记录本次勾选的所有平台。"
        />
        <MetricCard
          label="分析来源"
          value={sessionQuery.data ? pillLabel(sessionQuery.data.analysis_provider) : "--"}
          hint="如果降级到规则模式，这里会明确提示。"
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Timeline events={events} />
        <div className="space-y-5">
          {matchesQuery.data?.length ? (
            matchesQuery.data.map((match) => (
              <MatchCard key={match.id} match={match} />
            ))
          ) : (
            <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-8 text-sm leading-7 text-slate shadow-console">
              {isRunning ? "代码清洗完成后，岗位会显示在这里。" : "当前任务还没有可展示的岗位。"}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
