import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, ChevronDown, ChevronUp, ShieldAlert, Zap } from "lucide-react";
import { useMemo, useState } from "react";
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

function buildExcerpt(match: JobMatch, maxLength: number = 120) {
  const text = match.requirements_text || match.description_text || "";
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}

export function MatchCard({ match }: MatchCardProps) {
  const queryClient = useQueryClient();
  const [isExpanded, setIsExpanded] = useState(false);

  const reviewMutation = useMutation({
    mutationFn: () => api.openReview(match.listing_id),
  });

  const guidedApplyMutation = useMutation({
    mutationFn: async () => {
      const attempt = await api.guidedApply(match.listing_id);
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

  const excerpt = useMemo(() => buildExcerpt(match), [match]);

  return (
    <article className="rounded-[24px] border border-ink/10 bg-shell/90 shadow-console overflow-hidden">
      <div
        className="p-5 cursor-pointer hover:bg-paper/50 transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill>{match.source_site}</StatusPill>
              {match.analysis_degraded ? (
                <StatusPill>降级</StatusPill>
              ) : null}
            </div>
            <h3 className="mt-2 font-display text-2xl text-ink truncate">{match.title}</h3>
            <p className="mt-1 text-sm text-slate">
              {match.source_company} · {match.location_city || match.location_raw || "地点未知"} · {match.employment_type || "类型未知"}
            </p>
            {!isExpanded && (
              <p className="mt-2 text-sm text-slate/70 line-clamp-2">{excerpt || "暂无职位描述"}</p>
            )}
          </div>

          <div className="flex items-center gap-4">
            <div className="text-center">
              <p className="text-xs uppercase tracking-[0.15em] text-slate">得分</p>
              <p className="font-display text-3xl text-ink">{Math.round(match.final_score)}</p>
            </div>
            <button
              type="button"
              className="p-2 rounded-full hover:bg-ink/5 transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                setIsExpanded((v) => !v);
              }}
            >
              {isExpanded ? (
                <ChevronUp size={20} className="text-slate" />
              ) : (
                <ChevronDown size={20} className="text-slate" />
              )}
            </button>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t border-ink/10 p-5 space-y-4">
          {match.analysis_degraded && match.analysis_notice ? (
            <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
              {match.analysis_notice}
            </p>
          ) : null}

          {match.department ? (
            <p className="text-sm text-slate">部门：{match.department}</p>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl bg-paper p-4">
              <p className="text-xs uppercase tracking-[0.15em] text-slate font-medium">匹配摘要</p>
              <p className="mt-2 text-sm leading-6 text-ink">
                {match.llm_summary || "这条职位已通过代码清洗和规则排序。"}
              </p>
            </div>

            <div className="space-y-3">
              <div className="rounded-xl border border-mint/30 bg-mint/10 p-3">
                <p className="text-xs uppercase tracking-[0.15em] text-slate">匹配亮点</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {match.highlights.length ? (
                    match.highlights.slice(0, 5).map((item) => (
                      <span key={item} className="rounded-full bg-shell px-2.5 py-1 text-xs text-ink">
                        {item}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-slate">暂无</span>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-ember/20 bg-ember/10 p-3">
                <p className="text-xs uppercase tracking-[0.15em] text-slate">风险提示</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[...match.missing_keywords, ...match.risk_flags].length ? (
                    [...match.missing_keywords, ...match.risk_flags].slice(0, 4).map((item) => (
                      <span key={item} className="rounded-full bg-shell px-2.5 py-1 text-xs text-ink">
                        {item}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-slate">暂无</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-ink/10 bg-paper p-4">
            <p className="text-xs uppercase tracking-[0.15em] text-slate font-medium">职位描述</p>
            <pre className="mt-2 text-sm leading-6 text-slate whitespace-pre-wrap max-h-48 overflow-y-auto">
              {match.description_text || match.requirements_text || "暂无描述"}
            </pre>
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-4 py-2 text-sm font-medium text-shell transition hover:bg-ink/90"
              onClick={() => reviewMutation.mutate()}
              disabled={reviewMutation.isPending || !match.apply_supported}
            >
              <ArrowUpRight size={14} />
              {reviewMutation.isPending ? "打开中..." : "打开职位页面"}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-medium text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => guidedApplyMutation.mutate()}
              disabled={guidedApplyMutation.isPending || !match.apply_supported}
            >
              <Zap size={14} />
              {guidedApplyMutation.isPending ? "准备中..." : "引导投递"}
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full border border-ember/20 bg-ember/10 px-4 py-2 text-sm font-medium text-ink transition hover:bg-ember/15"
              onClick={() =>
                window.openResumeDesktop?.openExternal
                  ? window.openResumeDesktop.openExternal(match.apply_url)
                  : window.open(match.apply_url, "_blank")
              }
              disabled={!match.apply_supported}
            >
              <ShieldAlert size={14} />
              原始链接
            </button>
          </div>

          {actionErrorMessage ? (
            <p className="rounded-xl border border-ember/30 bg-ember/10 px-4 py-2 text-sm text-ink">
              {actionErrorMessage}
            </p>
          ) : null}

          <p className="text-xs text-slate/70">
            平台：{pillLabel(match.platform)} · 模式：{modeLabel(match.apply_supported ? "guided_apply" : "review_in_browser")}
          </p>
        </div>
      )}
    </article>
  );
}
