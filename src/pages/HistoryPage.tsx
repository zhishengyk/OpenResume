import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, ExternalLink, RotateCcw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { StatusPill } from "../components/StatusPill";
import { api } from "../lib/api";
import { formatDateTime, modeLabel, pillLabel } from "../lib/utils";

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

function openExternal(url: string) {
  if (window.openResumeDesktop?.openExternal) {
    window.openResumeDesktop.openExternal(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export function HistoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: ["search-sessions"],
    queryFn: api.listSearchSessions,
  });
  const attemptsQuery = useQuery({
    queryKey: ["attempts"],
    queryFn: api.listAttempts,
  });
  const batchesQuery = useQuery({
    queryKey: ["apply-batches"],
    queryFn: () => api.listApplyBatches(),
    refetchInterval: (query) => {
      const data = query.state.data || [];
      return data.some((item) => item.status === "queued" || item.status === "running")
        ? 2000
        : false;
    },
  });
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  const emergencyStopMutation = useMutation({
    mutationFn: () => api.setEmergencyStop(!appStateQuery.data?.emergency_stop_active),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app-state"] });
      void queryClient.invalidateQueries({ queryKey: ["risk-status"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (attemptId: string) => api.cancelAttempt(attemptId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attempts"] });
    },
  });

  const continueMutation = useMutation({
    mutationFn: async (attemptId: string) => {
      const verification = await api.openAttemptVerificationWindow(attemptId);
      await openVerificationPopup(verification.url, verification.title);
      return api.continueAttempt(attemptId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attempts"] });
    },
  });

  const continueBatchMutation = useMutation({
    mutationFn: (batchId: string) => api.continueApplyBatch(batchId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["apply-batches"] });
    },
  });

  const cancelBatchMutation = useMutation({
    mutationFn: (batchId: string) => api.cancelApplyBatch(batchId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["apply-batches"] });
    },
  });

  const errorMessage =
    (continueBatchMutation.error instanceof Error && continueBatchMutation.error.message) ||
    (cancelBatchMutation.error instanceof Error && cancelBatchMutation.error.message) ||
    (continueMutation.error instanceof Error && continueMutation.error.message) ||
    (cancelMutation.error instanceof Error && cancelMutation.error.message) ||
    null;

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <div className="flex items-start gap-3">
            <AlertOctagon className="mt-1 text-ember" size={20} />
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ember">紧急停止</p>
              <p className="mt-3 font-display text-4xl text-ink">立刻暂停所有引导动作</p>
              <p className="mt-4 text-sm leading-7 text-slate">
                如果官网页面出现异常，或者你不希望系统继续推进任何引导投递，可以在这里直接拉起紧急停止。
              </p>
              <button
                type="button"
                className="mt-6 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
                onClick={() => emergencyStopMutation.mutate()}
              >
                {appStateQuery.data?.emergency_stop_active ? "解除紧急停止" : "启用紧急停止"}
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">搜索历史</p>
          <div className="mt-5 space-y-3">
            {sessionsQuery.data?.map((session) => (
              <div
                key={session.id}
                className="rounded-[24px] border border-ink/10 bg-paper px-4 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-ink">{session.job_targets.join(" / ")}</p>
                    <p className="mt-1 text-sm text-slate">
                      {session.requested_platforms.map((platform) => pillLabel(platform)).join(" | ")}{" "}
                      | {modeLabel(session.mode)} | {formatDateTime(session.created_at)}
                    </p>
                    {session.analysis_notice ? (
                      <p className="mt-2 text-sm leading-6 text-slate">
                        {session.analysis_notice}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusPill>{session.status}</StatusPill>
                    <button
                      type="button"
                      className="rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-semibold text-ink transition hover:bg-paper"
                      onClick={() => navigate(`/results?session=${session.id}`)}
                    >
                      查看结果
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate">批量投递批次</p>
            <p className="mt-2 text-sm text-slate">
              这里记录批量投递的状态流转、验证阻塞和逐岗位明细。
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
            onClick={() => void queryClient.invalidateQueries({ queryKey: ["apply-batches"] })}
          >
            <RotateCcw size={14} />
            刷新批次
          </button>
        </div>

        <div className="mt-5 space-y-4">
          {batchesQuery.data?.map((batch) => (
            <article
              key={batch.id}
              className="rounded-[28px] border border-ink/10 bg-paper px-4 py-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-ink">
                      批次 {batch.id.slice(0, 8)} | {modeLabel(batch.execution_mode)}
                    </p>
                    <StatusPill>{batch.status}</StatusPill>
                  </div>
                  <p className="mt-2 text-sm text-slate">
                    {new Date(batch.created_at).toLocaleString()} | {batch.completed_items}/
                    {batch.total_items} 完成 | 自动提交 {batch.submitted_items} 个
                  </p>
                  <p className="mt-2 text-sm leading-7 text-slate">{batch.message}</p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {batch.status === "needs_verification" || batch.status === "failed" ? (
                    <button
                      type="button"
                      className="rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-semibold text-ink transition hover:bg-paper disabled:opacity-50"
                      disabled={continueBatchMutation.isPending}
                      onClick={() => continueBatchMutation.mutate(batch.id)}
                    >
                      继续批次
                    </button>
                  ) : null}
                  {batch.status === "queued" ||
                  batch.status === "running" ||
                  batch.status === "needs_verification" ? (
                    <button
                      type="button"
                      className="rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-semibold text-ink transition hover:bg-paper disabled:opacity-50"
                      disabled={cancelBatchMutation.isPending}
                      onClick={() => cancelBatchMutation.mutate(batch.id)}
                    >
                      取消批次
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {batch.items.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-[22px] border border-ink/10 bg-shell px-4 py-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-semibold text-ink">
                            {(item.context.job_title as string | undefined) ||
                              (item.context.job_id as string | undefined) ||
                              item.listing_id}
                          </p>
                          <StatusPill>{item.company_key}</StatusPill>
                          <StatusPill>{item.status}</StatusPill>
                        </div>
                        <p className="mt-2 text-sm text-slate">
                          {modeLabel(item.execution_mode)} |{" "}
                          {(item.context.account_display_name as string | undefined) || "--"} |{" "}
                          {(item.context.resume_label as string | undefined) || "--"}
                        </p>
                        <p className="mt-2 text-sm leading-7 text-slate">{item.message}</p>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {item.verification_url ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                            onClick={() =>
                              openVerificationPopup(item.verification_url!, `${item.company_key} 验证`)
                            }
                          >
                            <ExternalLink size={14} />
                            打开验证
                          </button>
                        ) : null}
                        {item.launch_url ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                            onClick={() => openExternal(item.launch_url!)}
                          >
                            <ExternalLink size={14} />
                            打开页面
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}

          {!batchesQuery.data?.length ? (
            <div className="rounded-[24px] border border-dashed border-ink/15 bg-paper px-4 py-5 text-sm leading-7 text-slate">
              还没有批量投递批次。先去结果页选中职位并创建投递批次。
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">单条投递记录</p>
        <div className="mt-5 space-y-3">
          {attemptsQuery.data?.map((attempt) => (
            <div
              key={attempt.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-[24px] border border-ink/10 bg-paper px-4 py-4"
            >
              <div>
                <p className="font-semibold text-ink">
                  {(attempt.context.job_title as string | undefined) ||
                    (attempt.context.job_id as string | undefined) ||
                    attempt.listing_id}
                </p>
                <p className="mt-1 text-sm text-slate">
                  {pillLabel(attempt.platform)} | {modeLabel(attempt.mode)} |{" "}
                  {new Date(attempt.created_at).toLocaleString()}
                </p>
                <p className="mt-2 text-sm leading-7 text-slate">{attempt.message}</p>
              </div>
              <div className="flex items-center gap-3">
                <StatusPill>{attempt.status}</StatusPill>
                {attempt.status === "needs_verification" ? (
                  <button
                    type="button"
                    className="rounded-full border border-ink/10 px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                    onClick={() => continueMutation.mutate(attempt.id)}
                    disabled={continueMutation.isPending}
                  >
                    打开弹窗并继续
                  </button>
                ) : null}
                <button
                  type="button"
                  className="rounded-full border border-ink/10 px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                  onClick={() => cancelMutation.mutate(attempt.id)}
                  disabled={cancelMutation.isPending}
                >
                  取消
                </button>
              </div>
            </div>
          ))}

          {!attemptsQuery.data?.length ? (
            <div className="rounded-[24px] border border-dashed border-ink/15 bg-paper px-4 py-5 text-sm leading-7 text-slate">
              还没有单条引导投递记录。
            </div>
          ) : null}
        </div>
      </section>

      {errorMessage ? (
        <section className="rounded-[28px] border border-ember/30 bg-ember/10 px-5 py-4 text-sm text-ink">
          {errorMessage}
        </section>
      ) : null}
    </div>
  );
}
