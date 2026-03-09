import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, ShieldAlert, Sparkles, Zap } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { modeLabel, pillLabel } from "../lib/utils";
import type { JobMatch } from "../types";
import { StatusPill } from "./StatusPill";

interface MatchCardProps {
  match: JobMatch;
}

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

export function MatchCard({ match }: MatchCardProps) {
  const queryClient = useQueryClient();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const reviewMutation = useMutation({
    mutationFn: () => api.openReview(match.job_id),
  });

  const guidedApplyMutation = useMutation({
    mutationFn: async () => {
      const attempt = await api.guidedApply(match.job_id);
      if (attempt.status === "needs_verification" && attempt.verification_url) {
        const verification = await api.openAttemptVerificationWindow(attempt.id);
        await openVerificationPopup(verification.url, verification.title);
        return api.continueAttempt(attempt.id);
      }
      return attempt;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attempts"] });
    },
  });

  const actionErrorMessage =
    reviewMutation.isError && reviewMutation.error instanceof Error
      ? reviewMutation.error.message
      : guidedApplyMutation.isError && guidedApplyMutation.error instanceof Error
        ? guidedApplyMutation.error.message
        : null;

  return (
    <article className="rounded-[30px] border border-ink/10 bg-shell/90 p-6 shadow-console">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill>{match.platform}</StatusPill>
            <StatusPill>{match.analysis_provider}</StatusPill>
            <StatusPill>{match.cached_llm ? "cached" : "fresh"}</StatusPill>
          </div>
          <h3 className="mt-4 font-display text-3xl text-ink">
            {match.title}
          </h3>
          <p className="mt-2 text-base text-slate">
            {match.company_name} · {match.city} · {match.salary_text || "薪资未标注"}
          </p>
        </div>

        <div className="rounded-[24px] border border-ink/10 bg-paper px-5 py-4 text-right">
          <p className="text-xs uppercase tracking-[0.2em] text-slate">
            最终分数
          </p>
          <p className="font-display text-5xl text-ink">
            {Math.round(match.final_score)}
          </p>
        </div>
      </div>

      {match.analysis_degraded && match.analysis_notice ? (
        <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
          {match.analysis_notice}
        </p>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[24px] bg-paper p-5">
          <p className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate">
            <Sparkles size={14} />
            匹配原因
          </p>
          <p className="mt-3 text-sm leading-7 text-ink">
            {match.llm_summary || "这个岗位已经通过代码清洗，排序说明正在补充中。"}
          </p>
          <button
            type="button"
            className="mt-4 text-sm font-semibold text-ink underline decoration-ink/20 underline-offset-4"
            onClick={() => setDetailsOpen((current) => !current)}
          >
            {detailsOpen ? "收起完整 JD" : "展开完整 JD"}
          </button>
          {detailsOpen ? (
            <pre className="mt-4 whitespace-pre-wrap rounded-[20px] border border-ink/10 bg-shell p-4 text-sm leading-7 text-slate">
              {match.jd_text}
            </pre>
          ) : (
            <>
              <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate">
                JD 摘要
              </p>
              <p className="mt-2 text-sm leading-7 text-slate">{match.jd_excerpt}</p>
            </>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-[24px] border border-mint/30 bg-mint/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">匹配亮点</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {match.highlights.length ? (
                match.highlights.map((item) => (
                  <span
                    key={item}
                    className="rounded-full bg-shell px-3 py-1.5 text-sm text-ink"
                  >
                    {item}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate">暂时还没有明显亮点。</span>
              )}
            </div>
          </div>

          <div className="rounded-[24px] border border-ember/20 bg-ember/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">
              缺口与风险
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {[...match.missing_keywords, ...match.risk_flags].length ? (
                [...match.missing_keywords, ...match.risk_flags].map((item) => (
                  <span
                    key={item}
                    className="rounded-full bg-shell px-3 py-1.5 text-sm text-ink"
                  >
                    {item}
                  </span>
                ))
              ) : (
                <span className="text-sm text-slate">暂未发现明显阻塞项。</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
          onClick={() => reviewMutation.mutate()}
          disabled={reviewMutation.isPending}
        >
          <ArrowUpRight size={16} />
          {reviewMutation.isPending ? "正在打开..." : "打开详情页"}
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => guidedApplyMutation.mutate()}
          disabled={guidedApplyMutation.isPending || !match.apply_supported}
        >
          <Zap size={16} />
          {guidedApplyMutation.isPending ? "正在准备..." : "一键投递"}
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-ember/20 bg-ember/10 px-5 py-3 text-sm font-semibold text-ink transition hover:bg-ember/15"
          onClick={() =>
            window.openResumeDesktop?.openExternal
              ? window.openResumeDesktop.openExternal(match.url)
              : window.open(match.url, "_blank")
          }
        >
          <ShieldAlert size={16} />
          打开原始链接
        </button>
      </div>

      {actionErrorMessage ? (
        <p className="mt-4 rounded-2xl border border-ember/30 bg-ember/10 px-4 py-3 text-sm leading-6 text-ink">
          {actionErrorMessage}
        </p>
      ) : null}

      <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate">
        建议模式：{modeLabel(match.apply_supported ? "guided_apply" : "review_in_browser")} · {pillLabel(match.platform)}
      </p>
    </article>
  );
}
