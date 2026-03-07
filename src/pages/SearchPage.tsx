import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Search as SearchIcon, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { splitCommaValues } from "../lib/utils";
import type { AutomationMode } from "../types";

const modeCards: Array<{
  mode: AutomationMode;
  title: string;
  body: string;
}> = [
  {
    mode: "recommend_only",
    title: "仅推荐",
    body: "只负责搜索、筛选和排序岗位，不在平台上执行任何动作。",
  },
  {
    mode: "review_in_browser",
    title: "浏览职位",
    body: "在专用浏览器会话中打开职位页面，由你自己掌控浏览和判断过程。",
  },
  {
    mode: "guided_apply",
    title: "引导投递",
    body: "自动推进到投递流程并尽量复用资料，但会在最终提交前停止。",
  },
];

export function SearchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });
  const riskStatusQuery = useQuery({
    queryKey: ["risk-status", "boss"],
    queryFn: () => api.getRiskStatus("boss"),
  });

  const [platform, setPlatform] = useState("boss");
  const [mode, setMode] = useState<AutomationMode>("recommend_only");
  const [jobTargets, setJobTargets] = useState("前端工程师, 全栈工程师");
  const [cities, setCities] = useState("上海, 杭州");
  const [salaryFloor, setSalaryFloor] = useState("25000");
  const [mustHaveKeywords, setMustHaveKeywords] = useState(
    "React, TypeScript, Node.js",
  );

  const guidedConsentMutation = useMutation({
    mutationFn: () => api.createGuidedApplyConsent(platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-state"] });
    },
  });

  const searchMutation = useMutation({
    mutationFn: () =>
      api.createSearchSession({
        platform,
        mode,
        job_targets: splitCommaValues(jobTargets),
        cities: splitCommaValues(cities),
        salary_floor: Number(salaryFloor),
        must_have_keywords: splitCommaValues(mustHaveKeywords),
      }),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["search-sessions"] });
      navigate(`/results?session=${session.id}`);
    },
  });

  const guidedApplyEnabled =
    appStateQuery.data?.guided_apply_consents.includes(platform);
  const searchErrorMessage =
    searchMutation.isError && searchMutation.error instanceof Error
      ? searchMutation.error.message
      : null;

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">
          搜索控制台
        </p>
        <h1 className="mt-3 font-display text-5xl italic text-ink">
          先找，再看，再谨慎推进。
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          当前流程刻意保持保守。任何引导动作前都有风险门禁，最终提交动作永远由用户亲自完成。
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            {modeCards.map((entry) => (
              <button
                type="button"
                key={entry.mode}
                onClick={() => setMode(entry.mode)}
                className={`rounded-[28px] border p-5 text-left shadow-console transition ${
                  mode === entry.mode
                    ? "border-ink bg-ink text-shell"
                    : "border-ink/10 bg-shell/90 text-ink hover:border-ink/20"
                }`}
              >
                <p className="font-display text-3xl italic">{entry.title}</p>
                <p className="mt-3 text-sm leading-7 opacity-80">{entry.body}</p>
              </button>
            ))}
          </div>

          <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="grid gap-5 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  平台
                </span>
                <select
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                >
                  <option value="boss">Boss 直聘</option>
                  <option value="liepin">猎聘（后续接入）</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  薪资下限
                </span>
                <input
                  value={salaryFloor}
                  onChange={(event) => setSalaryFloor(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  目标岗位
                </span>
                <textarea
                  rows={4}
                  value={jobTargets}
                  onChange={(event) => setJobTargets(event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  目标城市
                </span>
                <textarea
                  rows={4}
                  value={cities}
                  onChange={(event) => setCities(event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
            </div>
            <label className="mt-5 block space-y-2">
              <span className="text-xs uppercase tracking-[0.2em] text-slate">
                必须命中关键词
              </span>
              <textarea
                rows={4}
                value={mustHaveKeywords}
                onChange={(event) => setMustHaveKeywords(event.target.value)}
                className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
              />
            </label>

            <div className="mt-6 flex flex-wrap gap-3">
              {mode === "guided_apply" && !guidedApplyEnabled ? (
                <button
                  type="button"
                  className="rounded-full bg-ember px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ember/90"
                  onClick={() => guidedConsentMutation.mutate()}
                  disabled={guidedConsentMutation.isPending}
                >
                  {guidedConsentMutation.isPending
                    ? "正在记录确认..."
                    : "确认引导投递风险"}
                </button>
              ) : null}
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
                onClick={() => searchMutation.mutate()}
                disabled={
                  searchMutation.isPending ||
                  (mode === "guided_apply" && !guidedApplyEnabled)
                }
              >
                <SearchIcon size={16} />
                {searchMutation.isPending ? "正在启动任务..." : "开始搜索任务"}
              </button>
            </div>
            {searchErrorMessage ? (
              <p className="mt-4 rounded-2xl border border-ember/30 bg-ember/10 px-4 py-3 text-sm leading-6 text-ink">
                {searchErrorMessage}
              </p>
            ) : null}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-1 text-ember" size={18} />
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-ember">
                  风险姿态
                </p>
                <p className="mt-3 text-sm leading-7 text-slate">
                  当前版本只支持保守节流、限频和人工接管，不提供隐身伪装、指纹欺骗或反检测能力。
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <p className="text-xs uppercase tracking-[0.24em] text-slate">
              当前限制
            </p>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-[24px] bg-paper p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate">
                  每小时剩余次数
                </p>
                <p className="mt-2 font-display text-4xl italic text-ink">
                  {riskStatusQuery.data?.remaining_hourly ?? "--"}
                </p>
              </div>
              <div className="rounded-[24px] bg-paper p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate">
                  每日剩余次数
                </p>
                <p className="mt-2 font-display text-4xl italic text-ink">
                  {riskStatusQuery.data?.remaining_daily ?? "--"}
                </p>
              </div>
            </div>
            <p className="mt-5 text-sm leading-7 text-slate">
              冷却时间：
              {riskStatusQuery.data?.cooldown_until
                ? new Date(riskStatusQuery.data.cooldown_until).toLocaleString()
                : "无"}
            </p>
            {mode === "guided_apply" ? (
              <div className="mt-5 rounded-[24px] border border-ink/10 bg-paper p-4">
                <div className="flex items-center gap-2 text-ink">
                  <AlertTriangle size={16} />
                  <p className="font-semibold">
                    引导投递仍然需要你亲自完成最后确认。
                  </p>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate">
                  系统可以帮你打开流程、预填一部分通用信息，但会在平台最终提交前停止。
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}
