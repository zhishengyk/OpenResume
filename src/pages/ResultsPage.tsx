import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Rocket,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { MetricCard } from "../components/MetricCard";
import { StatusPill } from "../components/StatusPill";
import { Timeline } from "../components/Timeline";
import { useEventStream } from "../hooks/useEventStream";
import { api } from "../lib/api";
import { modeLabel, pillLabel } from "../lib/utils";
import type { ApplyExecutionMode, SearchEvent, SearchSession } from "../types";

const PAGE_SIZE = 20;

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

function sessionRefetchInterval(
  sessionId: string | undefined,
  session: SearchSession | undefined,
) {
  if (!sessionId) {
    return false;
  }
  if (!session) {
    return 2000;
  }
  if (session.status === "running") {
    return 2000;
  }
  if (
    session.status === "ready" &&
    (session.analysis_status === "pending" || session.analysis_status === "running")
  ) {
    return 2000;
  }
  return false;
}

export function ResultsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<SearchEvent[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedListingIds, setSelectedListingIds] = useState<string[]>([]);
  const [executionMode, setExecutionMode] = useState<ApplyExecutionMode>("semi_auto");
  const sessionIdFromUrl = params.get("session") || undefined;

  const sessionsListQuery = useQuery({
    queryKey: ["search-sessions"],
    queryFn: api.listSearchSessions,
    enabled: !sessionIdFromUrl,
  });
  const sessionId = sessionIdFromUrl || sessionsListQuery.data?.[0]?.id;

  useEffect(() => {
    if (!sessionIdFromUrl && sessionId) {
      setParams({ session: sessionId }, { replace: true });
    }
  }, [sessionIdFromUrl, sessionId, setParams]);

  useEffect(() => {
    setEvents([]);
    setCurrentPage(1);
    setSelectedListingIds([]);
    setExecutionMode("semi_auto");
  }, [sessionId]);

  const sessionQuery = useQuery({
    queryKey: ["search-session", sessionId],
    queryFn: () => api.getSearchSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: (query) =>
      sessionRefetchInterval(sessionId, query.state.data as SearchSession | undefined),
  });

  const matchesQuery = useQuery({
    queryKey: ["search-matches", sessionId],
    queryFn: () => api.getSearchMatches(sessionId!),
    enabled: Boolean(
      sessionId && sessionQuery.data?.status && sessionQuery.data.status !== "running",
    ),
    refetchInterval: false,
  });

  const openVerificationMutation = useMutation({
    mutationFn: async () => {
      const payload = await api.openSearchVerification(sessionId!);
      await openVerificationPopup(payload.url, payload.title);
      return payload;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    },
  });

  const retrySearchMutation = useMutation({
    mutationFn: () => api.retrySearchSession(sessionId!),
    onSuccess: () => {
      setEvents([]);
      setCurrentPage(1);
      setSelectedListingIds([]);
      void queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
      void queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
    },
  });

  const createBatchMutation = useMutation({
    mutationFn: () =>
      api.createApplyBatch({
        listing_ids: selectedListingIds,
        execution_mode: executionMode,
        session_id: sessionId,
        confirm_auto_submit: executionMode === "auto_submit",
      }),
    onSuccess: () => {
      setSelectedListingIds([]);
      void queryClient.invalidateQueries({ queryKey: ["apply-batches"] });
      navigate("/history");
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
    void queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    void queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
  });

  useEffect(() => {
    if (!sessionId || sessionQuery.data?.status !== "ready") {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
  }, [
    queryClient,
    sessionId,
    sessionQuery.data?.status,
    sessionQuery.data?.analysis_status,
    sessionQuery.data?.updated_at,
  ]);

  const matches = matchesQuery.data || [];
  const isBlocked = sessionQuery.data?.status === "blocked";
  const isRunning = sessionQuery.data?.status === "running";
  const analysisStatus = sessionQuery.data?.analysis_status;
  const analysisInProgress =
    sessionQuery.data?.status === "ready" &&
    (analysisStatus === "pending" || analysisStatus === "running");
  const analysisFailed = sessionQuery.data?.status === "ready" && analysisStatus === "failed";
  const analysisReady = sessionQuery.data?.status === "ready" && analysisStatus === "ready";

  const paginatedMatches = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return matches.slice(start, start + PAGE_SIZE);
  }, [matches, currentPage]);

  const totalPages = useMemo(() => {
    return Math.ceil(matches.length / PAGE_SIZE);
  }, [matches.length]);

  const currentPageIds = useMemo(
    () => paginatedMatches.map((match) => match.listing_id),
    [paginatedMatches],
  );
  const allListingIds = useMemo(() => matches.map((match) => match.listing_id), [matches]);

  const analysisProviderLabel = useMemo(() => {
    if (analysisInProgress) {
      return "处理中";
    }
    if (analysisFailed) {
      return "失败";
    }
    if (analysisReady && sessionQuery.data) {
      return pillLabel(sessionQuery.data.analysis_provider);
    }
    return "--";
  }, [analysisFailed, analysisInProgress, analysisReady, sessionQuery.data]);

  const analysisHint = analysisInProgress
    ? "规则排序结果已经可看，模型分析完成后会自动刷新并重新排序。"
    : analysisFailed
      ? "模型分析未完成，当前仍显示规则排序结果。"
      : "模型分析完成后，这里会显示当前实际生效的分析来源。";

  const batchErrorMessage =
    createBatchMutation.isError && createBatchMutation.error instanceof Error
      ? createBatchMutation.error.message
      : null;

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const toggleListingSelection = (listingId: string) => {
    setSelectedListingIds((current) =>
      current.includes(listingId)
        ? current.filter((item) => item !== listingId)
        : [...current, listingId],
    );
  };

  const selectCurrentPage = () => {
    setSelectedListingIds((current) =>
      Array.from(new Set([...current, ...currentPageIds])),
    );
  };

  const selectAllResults = () => {
    setSelectedListingIds(allListingIds);
  };

  const clearSelection = () => {
    setSelectedListingIds([]);
  };

  const createBatch = () => {
    if (!selectedListingIds.length) {
      return;
    }
    if (
      executionMode === "auto_submit" &&
      !window.confirm("全自动提交会在可识别时直接点击最终提交。确认继续吗？")
    ) {
      return;
    }
    createBatchMutation.mutate();
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate">搜索任务</p>
            <h1 className="mt-3 font-display text-5xl text-ink">
              先清洗，再排序，最后补模型分析和投递动作。
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

      {analysisInProgress ? (
        <section className="rounded-[32px] border border-signal/30 bg-signal/10 p-6 shadow-console">
          <p className="text-sm leading-7 text-ink">
            模型分析正在后台进行。当前列表先按规则分数展示，分析完成后会自动刷新，并按最终分重新排序。
          </p>
        </section>
      ) : null}

      {(analysisFailed ||
        (analysisReady && sessionQuery.data?.analysis_degraded && sessionQuery.data.analysis_notice)) ? (
        <section className="rounded-[32px] border border-amber-500/30 bg-amber-500/10 p-6 shadow-console">
          <p className="text-sm leading-7 text-ink">
            {sessionQuery.data?.analysis_notice || "模型分析未完成，当前展示的是规则排序结果。"}
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
                先完成验证，再继续这次搜索。
              </h2>
              <p className="mt-3 text-sm leading-7 text-slate">
                {sessionQuery.data?.blocked_reason || "平台要求先完成人工验证。"}
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
                {openVerificationMutation.isPending ? "打开中..." : "打开验证弹窗"}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => retrySearchMutation.mutate()}
                disabled={retrySearchMutation.isPending || !sessionId}
              >
                <RefreshCw size={16} />
                {retrySearchMutation.isPending ? "重试中..." : "重试搜索"}
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-3">
        <MetricCard
          label="可见职位"
          value={String(matches.length)}
          hint="这里只显示抓取并清洗后保留下来的职位。"
        />
        <MetricCard
          label="已选平台"
          value={
            sessionQuery.data?.requested_platforms
              ?.map((platform) => pillLabel(platform))
              .join(", ") || "--"
          }
          hint="搜索任务会记录本次选中的全部平台。"
        />
        <MetricCard
          label="分析状态"
          value={analysisProviderLabel}
          hint={analysisHint}
        />
      </section>

      {matches.length ? (
        <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate">批量投递</p>
              <h2 className="mt-2 font-display text-3xl text-ink">
                已选 {selectedListingIds.length} 个职位
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate">
                系统会按公司分组，套用默认账号和默认简历。缺少资产的公司会在创建批次时直接阻塞。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                onClick={selectCurrentPage}
              >
                选中当前页
              </button>
              <button
                type="button"
                className="rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                onClick={selectAllResults}
              >
                选中全部结果
              </button>
              <button
                type="button"
                className="rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                onClick={clearSelection}
              >
                清空选择
              </button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                executionMode === "semi_auto"
                  ? "bg-ink text-shell"
                  : "border border-ink/10 bg-paper text-ink hover:bg-shell"
              }`}
              onClick={() => setExecutionMode("semi_auto")}
            >
              {modeLabel("semi_auto")}
            </button>
            <button
              type="button"
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                executionMode === "auto_submit"
                  ? "bg-ember text-shell"
                  : "border border-ink/10 bg-paper text-ink hover:bg-shell"
              }`}
              onClick={() => setExecutionMode("auto_submit")}
            >
              {modeLabel("auto_submit")}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
              disabled={!selectedListingIds.length || createBatchMutation.isPending}
              onClick={createBatch}
            >
              <Rocket size={16} />
              {createBatchMutation.isPending ? "创建批次中..." : "创建投递批次"}
            </button>
          </div>

          {executionMode === "auto_submit" ? (
            <p className="mt-4 rounded-2xl border border-ember/30 bg-ember/10 px-4 py-3 text-sm leading-7 text-ink">
              全自动模式只在页面结构可识别且没有验证码时继续点击最终提交。默认仍推荐半自动模式。
            </p>
          ) : (
            <p className="mt-4 rounded-2xl border border-mint/30 bg-mint/10 px-4 py-3 text-sm leading-7 text-ink">
              半自动模式会自动登录、上传简历并填写公共字段，然后停在最终提交前。
            </p>
          )}

          {batchErrorMessage ? (
            <p className="mt-4 rounded-2xl border border-ember/30 bg-ember/10 px-4 py-3 text-sm text-ink">
              {batchErrorMessage}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Timeline events={events} />
        <div className="space-y-5">
          {paginatedMatches.length ? (
            <>
              {paginatedMatches.map((match) => (
                <MatchCard
                  key={match.id}
                  match={match}
                  selectable
                  selected={selectedListingIds.includes(match.listing_id)}
                  onToggleSelect={toggleListingSelection}
                />
              ))}
              {totalPages > 1 ? (
                <div className="flex items-center justify-center gap-2 pt-4">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-medium text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage <= 1}
                  >
                    <ChevronLeft size={16} />
                    上一页
                  </button>
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      let page: number;
                      if (totalPages <= 5) {
                        page = i + 1;
                      } else if (currentPage <= 3) {
                        page = i + 1;
                      } else if (currentPage >= totalPages - 2) {
                        page = totalPages - 4 + i;
                      } else {
                        page = currentPage - 2 + i;
                      }
                      return (
                        <button
                          key={page}
                          type="button"
                          className={`h-9 w-9 rounded-full text-sm font-medium transition ${
                            page === currentPage
                              ? "bg-ink text-shell"
                              : "border border-ink/10 bg-shell text-ink hover:bg-paper"
                          }`}
                          onClick={() => handlePageChange(page)}
                        >
                          {page}
                        </button>
                      );
                    })}
                  </div>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-medium text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage >= totalPages}
                  >
                    下一页
                    <ChevronRight size={16} />
                  </button>
                </div>
              ) : null}
              {totalPages > 1 ? (
                <p className="text-center text-sm text-slate">
                  第 {currentPage} 页，共 {totalPages} 页，合计 {matches.length} 个职位
                </p>
              ) : null}
            </>
          ) : (
            <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-8 text-sm leading-7 text-slate shadow-console">
              {isRunning
                ? "职位抓取和规则排序完成后会显示在这里。"
                : "当前搜索任务还没有可展示的职位。"}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
