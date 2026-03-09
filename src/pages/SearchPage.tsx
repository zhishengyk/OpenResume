import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Search as SearchIcon, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
    body: "只做官网搜索、清洗和排序，不打开页面，也不发起投递。",
  },
  {
    mode: "review_in_browser",
    title: "查看岗位",
    body: "打开清洗后的官网岗位详情，在本地逐条判断是否继续。",
    capabilityFlag: "review_open_supported",
  },
  {
    mode: "guided_apply",
    title: "引导投递",
    body: "进入官网投递流程，登录和验证码统一在应用内小窗处理。",
    capabilityFlag: "guided_apply_supported",
  },
];

function modeSupported(platforms: PlatformCapability[], mode: AutomationMode) {
  const card = modeCards.find((entry) => entry.mode === mode);
  const flag = card?.capabilityFlag;
  if (!flag) {
    return true;
  }
  return platforms.every((platform) => platform[flag]);
}

export function SearchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [mode, setMode] = useState<AutomationMode>("recommend_only");
  const [jobTargets, setJobTargets] = useState("前端工程师, 全栈工程师");
  const [cities, setCities] = useState("上海, 杭州");
  const [salaryFloor, setSalaryFloor] = useState("25000");
  const [mustHaveKeywords, setMustHaveKeywords] = useState(
    "React, TypeScript, 官网",
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
    const selectable = platformsQuery.data
      .filter((item) => item.selectable && item.search_supported)
      .map((item) => item.platform);
    setSelectedPlatforms((current) => {
      const valid = current.filter((item) => selectable.includes(item));
      if (valid.length) {
        return valid;
      }
      return selectable.slice(0, 1);
    });
  }, [platformsQuery.data]);

  const selectedPlatformCapabilities = useMemo(
    () =>
      (platformsQuery.data || []).filter((item) =>
        selectedPlatforms.includes(item.platform),
      ),
    [platformsQuery.data, selectedPlatforms],
  );
  const firstSelectedPlatform = selectedPlatformCapabilities[0]?.platform;

  useEffect(() => {
    if (
      !selectedPlatformCapabilities.length ||
      modeSupported(selectedPlatformCapabilities, mode)
    ) {
      return;
    }
    setMode("recommend_only");
  }, [selectedPlatformCapabilities, mode]);

  const riskStatusQuery = useQuery({
    queryKey: ["risk-status", firstSelectedPlatform],
    queryFn: () => api.getRiskStatus(firstSelectedPlatform!),
    enabled: Boolean(firstSelectedPlatform),
  });

  const guidedApplyEnabled =
    selectedPlatformCapabilities.length > 0 &&
    selectedPlatformCapabilities.every((platform) =>
      appStateQuery.data?.guided_apply_consents.includes(platform.platform),
    );

  const guidedConsentMutation = useMutation({
    mutationFn: async () => {
      await Promise.all(
        selectedPlatformCapabilities.map((platform) =>
          api.createGuidedApplyConsent(platform.platform),
        ),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-state"] });
    },
  });

  const searchMutation = useMutation({
    mutationFn: () =>
      api.createSearchSession({
        platforms: selectedPlatforms,
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

  const searchErrorMessage =
    searchMutation.isError && searchMutation.error instanceof Error
      ? searchMutation.error.message
      : null;

  const searchDisabled =
    selectedPlatformCapabilities.length === 0 ||
    !modeSupported(selectedPlatformCapabilities, mode) ||
    searchMutation.isPending ||
    (mode === "guided_apply" && !guidedApplyEnabled);

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">
          搜索工作台
        </p>
        <h1 className="mt-3 font-display text-5xl text-ink">
          多平台搜索从官网模块开始，未接入平台保留占位。
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          岗位会先从配置好的官网来源抓取，再经过代码清洗，最后进入模型排序阶段。尚未接入的平台会保留展示，但不可勾选。
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            {modeCards.map((entry) => {
              const available = modeSupported(selectedPlatformCapabilities, entry.mode);
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
                  <p className="font-display text-3xl">{entry.title}</p>
                  <p className="mt-3 text-sm leading-7 opacity-80">{entry.body}</p>
                </button>
              );
            })}
          </div>

          <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="grid gap-5 md:grid-cols-2">
              <div className="space-y-3">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  平台
                </span>
                <div className="space-y-3">
                  {platformsQuery.data?.map((platform) => {
                    const checked = selectedPlatforms.includes(platform.platform);
                    return (
                      <label
                        key={platform.platform}
                        className={`flex items-start gap-3 rounded-2xl border px-4 py-3 ${
                          platform.selectable
                            ? "border-ink/10 bg-paper"
                            : "border-ink/10 bg-paper/60 text-slate"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!platform.selectable}
                          onChange={(event) => {
                            if (!platform.selectable) {
                              return;
                            }
                            setSelectedPlatforms((current) =>
                              event.target.checked
                                ? [...current, platform.platform]
                                : current.filter((item) => item !== platform.platform),
                            );
                          }}
                          className="mt-1"
                        />
                        <div>
                          <p className="font-semibold text-ink">{platform.label}</p>
                          <p className="mt-1 text-sm leading-6 text-slate">
                            {platform.selectable
                              ? "已接入"
                              : platform.disabled_reason || "暂未接入"}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>

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
                必备关键词
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
                disabled={searchDisabled}
              >
                <SearchIcon size={16} />
                {searchMutation.isPending ? "正在启动..." : "开始搜索"}
              </button>
            </div>

            {!selectedPlatformCapabilities.length ? (
              <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
                请至少选择一个已接入的平台。未接入的平台会保留展示，但不能勾选。
              </p>
            ) : null}

            {mode === "guided_apply" && !guidedApplyEnabled ? (
              <p className="mt-4 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-ink">
                引导投递模式要求你先对当前选中的每个平台完成风险确认。
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
                  验证方式
                </p>
                <p className="mt-3 text-sm leading-7 text-slate">
                  官网搜索和投递过程中可能会遇到登录、验证码或二次校验。这些步骤统一在应用内小窗里完成，而不是跳到外部浏览器。
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
                  每小时剩余
                </p>
                <p className="mt-2 font-display text-4xl text-ink">
                  {riskStatusQuery.data?.remaining_hourly ?? "--"}
                </p>
              </div>
              <div className="rounded-[24px] bg-paper p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate">
                  每日剩余
                </p>
                <p className="mt-2 font-display text-4xl text-ink">
                  {riskStatusQuery.data?.remaining_daily ?? "--"}
                </p>
              </div>
            </div>
            <p className="mt-5 text-sm leading-7 text-slate">
              冷却到期：
              {riskStatusQuery.data?.cooldown_until
                ? new Date(riskStatusQuery.data.cooldown_until).toLocaleString()
                : "无"}
            </p>

            <div className="mt-5 rounded-[24px] border border-ink/10 bg-paper p-4">
              <div className="flex items-center gap-2 text-ink">
                <AlertTriangle size={16} />
                <p className="font-semibold">已选平台能力</p>
              </div>
              <div className="mt-3 space-y-3 text-sm leading-7 text-slate">
                {selectedPlatformCapabilities.map((platform) => (
                  <div key={platform.platform}>
                    <p className="font-semibold text-ink">{platform.label}</p>
                    <p>
                      搜索：{platform.search_supported ? "支持" : "不支持"} · 查看：
                      {platform.review_open_supported ? "支持" : "不支持"} · 引导投递：
                      {platform.guided_apply_supported ? "支持" : "不支持"}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
