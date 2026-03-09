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
    mutationFn: () => api.openSearchVerification(sessionId!),
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
          (item) =>
            item.type === event.type && item.timestamp === event.timestamp,
        )
      ) {
        return current;
      }

      return [...current, event];
    });
    queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
  });

  const topMatch = matchesQuery.data?.[0];
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
            <h1 className="mt-3 font-display text-5xl italic text-ink">
              先看流程，再决定要不要继续进入模块动作。
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

      {isBlocked ? (
        <section className="rounded-[32px] border border-ember/30 bg-ember/10 p-6 shadow-console">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-ember">
                <AlertTriangle size={16} />
                命中人工验证
              </p>
              <h2 className="mt-3 font-display text-3xl italic text-ink">
                先完成验证，再把这次任务继续跑完。
              </h2>
              <p className="mt-3 text-sm leading-7 text-slate">
                {sessionQuery.data?.blocked_reason ||
                  "系统已暂停当前搜索，避免在未验证状态下继续请求平台。"}
              </p>
              <p className="mt-3 text-sm leading-7 text-slate">
                点击“重新打开验证页”后，先在浏览器里完成验证，再点击“验证后重试”。
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
                {openVerificationMutation.isPending
                  ? "正在打开验证页..."
                  : "重新打开验证页"}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => retrySearchMutation.mutate()}
                disabled={retrySearchMutation.isPending || !sessionId}
              >
                <RefreshCw size={16} />
                {retrySearchMutation.isPending ? "正在重试..." : "验证后重试"}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-3">
        <MetricCard
          label="可见岗位数"
          value={String(matchesQuery.data?.length ?? 0)}
          hint="规则筛选会先出结果，模型说明再逐步补齐。"
        />
        <MetricCard
          label="当前平台"
          value={sessionQuery.data ? pillLabel(sessionQuery.data.platform) : "--"}
          hint="平台能力由模块声明，公共层只负责调度。"
        />
        <MetricCard
          label="最高分"
          value={topMatch ? String(Math.round(topMatch.final_score)) : "--"}
          hint="最终分数由规则过滤和模型分析共同构成。"
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
              {isRunning
                ? "规则筛选完成后，岗位卡片会先出现在这里；随后模型解释会继续补进详情。"
                : "当前还没有可展示的岗位卡片。若任务进入 blocked，请先完成验证后再重试。"}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
