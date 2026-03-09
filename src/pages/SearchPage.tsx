import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Search as SearchIcon, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { splitCommaValues } from "../lib/utils";
import type { AutomationMode, PlatformCapability } from "../types";

const modeCards: Array<{
  mode: AutomationMode;
  title: string;
  body: string;
  capabilityFlag?: "review_open_supported" | "guided_apply_supported";
}> = [
  {
    mode: "recommend_only",
    title: "仅推荐",
    body: "只负责搜索、筛选和排序岗位，不在平台上执行任何动作。",
  },
  {
    mode: "review_in_browser",
    title: "浏览职位",
    body: "打开职位详情页，由你自己判断是否继续。",
    capabilityFlag: "review_open_supported",
  },
  {
    mode: "guided_apply",
    title: "引导投递",
    body: "允许模块帮你推进流程，但仍会在最终提交前停止。",
    capabilityFlag: "guided_apply_supported",
  },
];

function supportsMode(capability: PlatformCapability | null, mode: AutomationMode) {
  const card = modeCards.find((entry) => entry.mode === mode);
  if (!card || !card.capabilityFlag) {
    return true;
  }

  return Boolean(capability?.[card.capabilityFlag]);
}

export function SearchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [platform, setPlatform] = useState("");
  const [mode, setMode] = useState<AutomationMode>("recommend_only");
  const [jobTargets, setJobTargets] = useState("前端工程师, 全栈工程师");
  const [cities, setCities] = useState("上海, 杭州");
  const [salaryFloor, setSalaryFloor] = useState("25000");
  const [mustHaveKeywords, setMustHaveKeywords] = useState(
    "React, TypeScript, Node.js",
  );

  const platformsQuery = useQuery({
    queryKey: ["platforms"],
    queryFn: api.getPlatforms,
  });
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  useEffect(() => {
    if (!platformsQuery.data?.length) {
      return;
    }
    if (platform && platformsQuery.data.some((item) => item.platform === platform)) {
      return;
    }

    const preferredPlatform =
      platformsQuery.data.find((item) => item.search_supported) ||
      platformsQuery.data[0];
    setPlatform(preferredPlatform.platform);
  }, [platformsQuery.data, platform]);

  const selectedPlatform =
    platformsQuery.data?.find((item) => item.platform === platform) || null;

  useEffect(() => {
    if (!selectedPlatform || supportsMode(selectedPlatform, mode)) {
      return;
    }
    setMode("recommend_only");
  }, [selectedPlatform, mode]);

  const riskStatusQuery = useQuery({
    queryKey: ["risk-status", platform],
    queryFn: () => api.getRiskStatus(platform),
    enabled: Boolean(platform),
  });
  const sessionQuery = useQuery({
    queryKey: ["platform-session", platform],
    queryFn: () => api.getPlatformSession(platform),
    enabled: Boolean(platform && selectedPlatform?.session_supported),
    refetchInterval:
      platform && selectedPlatform?.session_supported ? 4000 : false,
  });

  const sessionStartMutation = useMutation({
    mutationFn: () => api.startPlatformSession(platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-session", platform] });
    },
  });

  const sessionReadyMutation = useMutation({
    mutationFn: () => api.checkPlatformSessionReady(platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-session", platform] });
    },
  });

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

  const guidedApplyEnabled = Boolean(
    platform && appStateQuery.data?.guided_apply_consents.includes(platform),
  );
  const sessionActive = Boolean(sessionQuery.data?.active);
  const sessionReady = Boolean(sessionQuery.data?.search_ready);
  const needsSessionStart = Boolean(
    selectedPlatform?.session_required && !sessionActive,
  );
  const needsSessionReady = Boolean(
    selectedPlatform?.session_required && sessionActive && !sessionReady,
  );

  const searchErrorMessage =
    searchMutation.isError && searchMutation.error instanceof Error
      ? searchMutation.error.message
      : null;
  const sessionErrorMessage =
    sessionReadyMutation.isError && sessionReadyMutation.error instanceof Error
      ? sessionReadyMutation.error.message
      : null;

  const searchDisabled =
    !selectedPlatform ||
    !selectedPlatform.search_supported ||
    searchMutation.isPending ||
    sessionStartMutation.isPending ||
    sessionReadyMutation.isPending ||
    needsSessionStart ||
    needsSessionReady ||
    (mode === "guided_apply" && !guidedApplyEnabled);

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">
          搜索控制台
        </p>
        <h1 className="mt-3 font-display text-5xl italic text-ink">
          公共层只调度模块，平台细节留在模块内部。
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          你现在选择的是一个平台注册入口，主分支不会再把某个平台的登录流程、
          浏览器策略和风控逻辑硬编码进公共页面。
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            {modeCards.map((entry) => {
              const available = supportsMode(selectedPlatform, entry.mode);
              return (
                <button
                  type="button"
                  key={entry.mode}
                  onClick={() => {
                    if (available) {
                      setMode(entry.mode);
                    }
                  }}
                  className={`rounded-[28px] border p-5 text-left shadow-console transition ${
                    mode === entry.mode
                      ? "border-ink bg-ink text-shell"
                      : available
                        ? "border-ink/10 bg-shell/90 text-ink hover:border-ink/20"
                        : "cursor-not-allowed border-ink/10 bg-shell/60 text-slate"
                  }`}
                >
                  <p className="font-display text-3xl italic">{entry.title}</p>
                  <p className="mt-3 text-sm leading-7 opacity-80">{entry.body}</p>
                </button>
              );
            })}
          </div>

          <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="grid gap-5 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  平台模块
                </span>
                <select
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                >
                  {platformsQuery.data?.map((item) => (
                    <option key={item.platform} value={item.platform}>
                      {item.label}
                    </option>
                  ))}
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
              {selectedPlatform?.session_supported ? (
                <button
                  type="button"
                  className="rounded-full border border-ink/10 bg-shell px-6 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => sessionStartMutation.mutate()}
                  disabled={sessionStartMutation.isPending}
                >
                  {sessionStartMutation.isPending
                    ? "正在打开平台会话..."
                    : "启动 / 重新打开平台会话"}
                </button>
              ) : null}

              {selectedPlatform?.session_supported ? (
                <button
                  type="button"
                  className="rounded-full border border-ink/10 bg-shell px-6 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => sessionReadyMutation.mutate()}
                  disabled={
                    sessionReadyMutation.isPending || sessionStartMutation.isPending
                  }
                >
                  {sessionReadyMutation.isPending
                    ? "正在检查会话状态..."
                    : "刷新会话状态"}
                </button>
              ) : null}

              {mode === "guided_apply" &&
              selectedPlatform?.guided_apply_supported &&
              !guidedApplyEnabled ? (
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
                disabled={searchDisabled}
              >
                <SearchIcon size={16} />
                {searchMutation.isPending ? "正在启动任务..." : "开始搜索任务"}
              </button>
            </div>

            {selectedPlatform && !selectedPlatform.search_supported ? (
              <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
                当前模块还没有接入真实搜索能力。你可以继续保留它作为占位模块，
                等后续按同样边界补齐实现。
              </p>
            ) : null}

            {needsSessionStart ? (
              <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
                当前模块要求独立会话。请先启动平台会话并完成登录。
              </p>
            ) : null}

            {needsSessionReady ? (
              <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
                当前模块会话已激活，但还没有通过就绪检查。先完成验证，再开始搜索。
              </p>
            ) : null}

            {sessionErrorMessage ? (
              <p className="mt-4 rounded-2xl border border-ember/30 bg-ember/10 px-4 py-3 text-sm leading-6 text-ink">
                {sessionErrorMessage}
              </p>
            ) : null}

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
                  模块可以声明自己的能力边界，但公共层不会帮任何模块默认获取高权限动作。
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

            <div className="mt-5 rounded-[24px] border border-ink/10 bg-paper p-4">
              <div className="flex items-center gap-2 text-ink">
                <AlertTriangle size={16} />
                <p className="font-semibold">
                  {selectedPlatform?.label || "当前模块"} 能力摘要
                </p>
              </div>
              <p className="mt-3 text-sm leading-7 text-slate">
                搜索：{selectedPlatform?.search_supported ? "支持" : "未启用"} ·
                浏览：{selectedPlatform?.review_open_supported ? "支持" : "未启用"} ·
                引导投递：
                {selectedPlatform?.guided_apply_supported ? "支持" : "未启用"} ·
                独立会话：
                {selectedPlatform?.session_required
                  ? "必需"
                  : selectedPlatform?.session_supported
                    ? "可选"
                    : "无"}
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
