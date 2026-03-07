import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, ShieldAlert, Sparkles, Zap } from "lucide-react";
import { api } from "../lib/api";
import { modeLabel } from "../lib/utils";
import type { JobMatch } from "../types";
import { StatusPill } from "./StatusPill";

interface MatchCardProps {
  match: JobMatch;
}

export function MatchCard({ match }: MatchCardProps) {
  const queryClient = useQueryClient();

  const reviewMutation = useMutation({
    mutationFn: () => api.openReview(match.job_id),
  });

  const guidedApplyMutation = useMutation({
    mutationFn: () => api.guidedApply(match.job_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attempts"] });
    },
  });

  return (
    <article className="rounded-[30px] border border-ink/10 bg-shell/90 p-6 shadow-console">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <StatusPill>{match.platform}</StatusPill>
            <StatusPill>{match.cached_llm ? "cached" : "fresh"}</StatusPill>
          </div>
          <h3 className="mt-4 font-display text-3xl italic text-ink">
            {match.title}
          </h3>
          <p className="mt-2 text-base text-slate">
            {match.company_name} · {match.city} · {match.salary_text}
          </p>
        </div>

        <div className="rounded-[24px] border border-ink/10 bg-paper px-5 py-4 text-right">
          <p className="text-xs uppercase tracking-[0.2em] text-slate">
            最终匹配分
          </p>
          <p className="font-display text-5xl italic text-ink">
            {Math.round(match.final_score)}
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="rounded-[24px] bg-paper p-5">
          <p className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate">
            <Sparkles size={14} />
            匹配理由
          </p>
          <p className="mt-3 text-sm leading-7 text-ink">
            {match.llm_summary || "规则引擎已经完成初筛，正在等待模型补充更细的匹配说明。"}
          </p>
          <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate">
            JD 摘要
          </p>
          <p className="mt-2 text-sm leading-7 text-slate">{match.jd_excerpt}</p>
        </div>

        <div className="space-y-4">
          <div className="rounded-[24px] border border-mint/30 bg-mint/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">匹配亮点</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {match.highlights.map((item) => (
                <span
                  key={item}
                  className="rounded-full bg-shell px-3 py-1.5 text-sm text-ink"
                >
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-[24px] border border-ember/20 bg-ember/10 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">
              缺口与风险
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {[...match.missing_keywords, ...match.risk_flags].map((item) => (
                <span
                  key={item}
                  className="rounded-full bg-shell px-3 py-1.5 text-sm text-ink"
                >
                  {item}
                </span>
              ))}
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
          {reviewMutation.isPending ? "正在打开..." : "打开职位页"}
        </button>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper"
          onClick={() => guidedApplyMutation.mutate()}
          disabled={guidedApplyMutation.isPending}
        >
          <Zap size={16} />
          {guidedApplyMutation.isPending ? "正在准备..." : "引导投递"}
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

      <p className="mt-4 text-xs uppercase tracking-[0.18em] text-slate">
        建议模式：{modeLabel(match.llm_score ? "guided_apply" : "review_in_browser")}
      </p>
    </article>
  );
}
