import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Search as SearchIcon, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchFilterSidebar } from "../components/SearchFilterSidebar";
import { api } from "../lib/api";
import { splitCommaValues } from "../lib/utils";
import type { AutomationMode, PlatformCapability } from "../types";

const FILTER_COLLAPSED_STORAGE_KEY = "openresume.search.filters.collapsed";

const modeCards: Array<{
  mode: AutomationMode;
  title: string;
  body: string;
  capabilityFlag?: "review_open_supported" | "guided_apply_supported";
}> = [
  {
    mode: "recommend_only",
    title: "仅推荐",
    body: "只抓取、清洗并排序职位，不自动打开职位页面。",
  },
  {
    mode: "review_in_browser",
    title: "打开职位页",
    body: "在本地浏览器中打开排序后的职位页面继续查看。",
    capabilityFlag: "review_open_supported",
  },
  {
    mode: "guided_apply",
    title: "引导投递",
    body: "排序完成后，在应用内继续走引导投递流程。",
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

function initialCollapsedState() {
  if (typeof window === "undefined") {
    return false;
  }
  const stored = window.localStorage.getItem(FILTER_COLLAPSED_STORAGE_KEY);
  if (stored === "1" || stored === "0") {
    return stored === "1";
  }
  return window.matchMedia("(max-width: 1279px)").matches;
}

export function SearchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [mode, setMode] = useState<AutomationMode>("recommend_only");
  const [jobTargets, setJobTargets] = useState("前端工程师");
  const [cities, setCities] = useState("");
  const [salaryFloor, setSalaryFloor] = useState("0");
  const [mustHaveKeywords, setMustHaveKeywords] = useState("");
  const [selectedVariants, setSelectedVariants] = useState<string[]>([]);
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([]);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [filtersCollapsed, setFiltersCollapsed] = useState(initialCollapsedState);

  const platformsQuery = useQuery({
    queryKey: ["platforms"],
    queryFn: api.getPlatforms,
  });
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  useEffect(() => {
    window.localStorage.setItem(FILTER_COLLAPSED_STORAGE_KEY, filtersCollapsed ? "1" : "0");
  }, [filtersCollapsed]);

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
        source_variants: selectedVariants.length > 0 ? selectedVariants : undefined,
        source_companies: selectedCompanies.length > 0 ? selectedCompanies : undefined,
        force_refresh: forceRefresh,
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
    searchMutation.isPending ||
    (mode === "guided_apply" && !guidedApplyEnabled);

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">搜索职位</p>
        <h1 className="mt-3 font-display text-5xl text-ink">
          当前官网搜索接入字节跳动，并并发抓取社招、校招与实习。
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          搜索时会从代码清单并发抓取职位，并在本地完成清洗和排序。筛选栏仅控制来源范围，
          岗位相关性通过排序体现，不会再因为硬过滤直接丢失候选职位。
        </p>
      </section>

      <section className="flex flex-col gap-6 xl:flex-row">
        <div
          className={`shrink-0 transition-all duration-300 ${
            filtersCollapsed ? "xl:w-[96px]" : "xl:w-[320px]"
          }`}
        >
          <SearchFilterSidebar
            selectedVariants={selectedVariants}
            selectedCompanies={selectedCompanies}
            onVariantsChange={setSelectedVariants}
            onCompaniesChange={setSelectedCompanies}
            collapsed={filtersCollapsed}
            onCollapsedChange={setFiltersCollapsed}
          />
        </div>

        <div className="min-w-0 flex-1 space-y-6">
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
              <div className="space-y-3 md:col-span-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">平台</span>
                <div className="grid gap-3 md:grid-cols-2">
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
                              : platform.disabled_reason || "不可用"}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>

              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">薪资下限</span>
                <input
                  value={salaryFloor}
                  onChange={(event) => setSalaryFloor(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">目标城市</span>
                <textarea
                  rows={4}
                  value={cities}
                  onChange={(event) => setCities(event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">目标职位</span>
                <textarea
                  rows={4}
                  value={jobTargets}
                  onChange={(event) => setJobTargets(event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2 md:col-span-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">必备关键词</span>
                <textarea
                  rows={4}
                  value={mustHaveKeywords}
                  onChange={(event) => setMustHaveKeywords(event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <label className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(event) => setForceRefresh(event.target.checked)}
                />
                强制刷新（跳过缓存）
              </label>
              {mode === "guided_apply" && !guidedApplyEnabled ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => guidedConsentMutation.mutate()}
                  disabled={guidedConsentMutation.isPending}
                >
                  <ShieldAlert size={16} />
                  {guidedConsentMutation.isPending ? "正在保存同意..." : "启用引导投递"}
                </button>
              ) : null}
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
                onClick={() => searchMutation.mutate()}
                disabled={searchDisabled}
              >
                <SearchIcon size={16} />
                {searchMutation.isPending ? "搜索中..." : "开始搜索"}
              </button>
            </div>

            {searchErrorMessage ? (
              <div className="mt-5 rounded-[24px] border border-ember/20 bg-ember/10 px-4 py-3 text-sm leading-7 text-ink">
                {searchErrorMessage}
              </div>
            ) : null}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
              <p className="text-xs uppercase tracking-[0.24em] text-slate">当前限制</p>
              <div className="mt-5 grid gap-4 grid-cols-2">
                <div className="rounded-[24px] bg-paper p-5">
                  <p className="text-sm text-slate">每小时剩余</p>
                  <p className="mt-2 font-display text-5xl text-ink">
                    {riskStatusQuery.data?.remaining_hourly ?? "--"}
                  </p>
                </div>
                <div className="rounded-[24px] bg-paper p-5">
                  <p className="text-sm text-slate">每日剩余</p>
                  <p className="mt-2 font-display text-5xl text-ink">
                    {riskStatusQuery.data?.remaining_daily ?? "--"}
                  </p>
                </div>
              </div>
              <p className="mt-5 text-sm text-slate">
                冷却到期：{riskStatusQuery.data?.cooldown_until || "无"}
              </p>
            </section>

            <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
              <p className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-slate">
                <AlertTriangle size={16} />
                已选平台能力
              </p>
              <div className="mt-5 space-y-4">
                {selectedPlatformCapabilities.map((platform) => (
                  <div key={platform.platform} className="rounded-[24px] bg-paper p-5 text-sm text-slate">
                    <p className="font-semibold text-ink">{platform.label}</p>
                    <p className="mt-2">
                      搜索：{platform.search_supported ? "支持" : "不支持"} | 查看：
                      {platform.review_open_supported ? "支持" : "不支持"} | 引导投递：
                      {platform.guided_apply_supported ? "支持" : "不支持"}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </section>
    </div>
  );
}
