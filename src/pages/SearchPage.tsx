import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  RotateCcw,
  Search as SearchIcon,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchFilterSidebar } from "../components/SearchFilterSidebar";
import { api } from "../lib/api";
import {
  buildProfileUpdateFromDraft,
  profileToSearchDraftFields,
  safeReadSearchDraft,
  SEARCH_DRAFT_VERSION,
  type SearchProfileDraftFields,
  type SearchProfileDraftState,
  writeSearchDraft,
} from "../lib/profile";
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
    body: "抓取、清洗并排序职位，不自动打开投递页面。",
  },
  {
    mode: "review_in_browser",
    title: "浏览器查看",
    body: "抓取完成后打开排序后的职位页面，方便继续查看上下文。",
    capabilityFlag: "review_open_supported",
  },
  {
    mode: "guided_apply",
    title: "引导投递",
    body: "从排序结果继续进入应用内的引导投递流程。",
    capabilityFlag: "guided_apply_supported",
  },
];

const emptyDraftFields: SearchProfileDraftFields = {
  jobTargets: "",
  cities: "",
  salaryFloor: "0",
  mustHaveKeywords: "",
  techStack: "",
  projectExperiences: "",
  awards: "",
};

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
  const [selectedVariants, setSelectedVariants] = useState<string[]>([]);
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([]);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [filtersCollapsed, setFiltersCollapsed] = useState(initialCollapsedState);
  const [draftFields, setDraftFields] =
    useState<SearchProfileDraftFields>(emptyDraftFields);
  const [draftMeta, setDraftMeta] = useState<{
    initialized: boolean;
    profileSignature: string;
    userEdited: boolean;
  }>({
    initialized: false,
    profileSignature: "",
    userEdited: false,
  });
  const [profileChangedNotice, setProfileChangedNotice] = useState(false);

  const platformsQuery = useQuery({
    queryKey: ["platforms"],
    queryFn: api.getPlatforms,
  });
  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: api.getProfile,
  });
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  useEffect(() => {
    window.localStorage.setItem(
      FILTER_COLLAPSED_STORAGE_KEY,
      filtersCollapsed ? "1" : "0",
    );
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

  useEffect(() => {
    if (!profileQuery.data) {
      return;
    }
    const nextSignature = profileQuery.data.profile_signature || "";
    if (!draftMeta.initialized) {
      const stored = safeReadSearchDraft();
      if (stored && stored.profileSignature === nextSignature) {
        setDraftFields(stored.fields);
        setDraftMeta({
          initialized: true,
          profileSignature: stored.profileSignature,
          userEdited: stored.userEdited,
        });
        setProfileChangedNotice(false);
        return;
      }
      if (stored && stored.userEdited) {
        setDraftFields(stored.fields);
        setDraftMeta({
          initialized: true,
          profileSignature: stored.profileSignature,
          userEdited: true,
        });
        setProfileChangedNotice(true);
        return;
      }
      setDraftFields(profileToSearchDraftFields(profileQuery.data));
      setDraftMeta({
        initialized: true,
        profileSignature: nextSignature,
        userEdited: false,
      });
      setProfileChangedNotice(false);
      return;
    }

    if (nextSignature === draftMeta.profileSignature) {
      setProfileChangedNotice(false);
      return;
    }
    if (draftMeta.userEdited) {
      setProfileChangedNotice(true);
      return;
    }
    setDraftFields(profileToSearchDraftFields(profileQuery.data));
    setDraftMeta((current) => ({
      ...current,
      profileSignature: nextSignature,
      userEdited: false,
    }));
    setProfileChangedNotice(false);
  }, [
    draftMeta.initialized,
    draftMeta.profileSignature,
    draftMeta.userEdited,
    profileQuery.data,
  ]);

  useEffect(() => {
    if (!draftMeta.initialized) {
      return;
    }
    const payload: SearchProfileDraftState = {
      version: SEARCH_DRAFT_VERSION,
      profileSignature: draftMeta.profileSignature,
      userEdited: draftMeta.userEdited,
      fields: draftFields,
    };
    writeSearchDraft(payload);
  }, [draftFields, draftMeta]);

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
  }, [mode, selectedPlatformCapabilities]);

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
      void queryClient.invalidateQueries({ queryKey: ["app-state"] });
    },
  });

  const updateDraftField = (key: keyof SearchProfileDraftFields, value: string) => {
    setDraftFields((current) => ({ ...current, [key]: value }));
    setDraftMeta((current) => ({ ...current, userEdited: true }));
  };

  const resetFromProfile = () => {
    if (!profileQuery.data) {
      return;
    }
    setDraftFields(profileToSearchDraftFields(profileQuery.data));
    setDraftMeta({
      initialized: true,
      profileSignature: profileQuery.data.profile_signature || "",
      userEdited: false,
    });
    setProfileChangedNotice(false);
  };

  const searchMutation = useMutation({
    mutationFn: async () => {
      const profile = profileQuery.data;
      if (profile) {
        const nextProfile = buildProfileUpdateFromDraft(profile, draftFields);
        const profileChanged =
          JSON.stringify(nextProfile.tech_stack) !==
            JSON.stringify(profile.tech_stack) ||
          JSON.stringify(nextProfile.project_experiences) !==
            JSON.stringify(profile.project_experiences) ||
          JSON.stringify(nextProfile.awards) !== JSON.stringify(profile.awards);
        if (profileChanged) {
          await api.updateProfile(nextProfile);
          await queryClient.invalidateQueries({ queryKey: ["profile"] });
          setDraftMeta((current) => ({
            ...current,
            profileSignature: nextProfile.profile_signature || current.profileSignature,
          }));
        }
      }

      return api.createSearchSession({
        platforms: selectedPlatforms,
        mode,
        job_targets: splitCommaValues(draftFields.jobTargets),
        cities: splitCommaValues(draftFields.cities),
        salary_floor: Number(draftFields.salaryFloor || 0),
        must_have_keywords: splitCommaValues(draftFields.mustHaveKeywords),
        source_variants: selectedVariants.length > 0 ? selectedVariants : undefined,
        source_companies: selectedCompanies.length > 0 ? selectedCompanies : undefined,
        force_refresh: forceRefresh,
      });
    },
    onSuccess: (session) => {
      void queryClient.invalidateQueries({ queryKey: ["search-sessions"] });
      navigate(`/results?session=${session.id}`);
    },
  });

  const searchErrorMessage =
    searchMutation.isError && searchMutation.error instanceof Error
      ? searchMutation.error.message
      : null;

  const searchDisabled =
    searchMutation.isPending ||
    (mode === "guided_apply" && !guidedApplyEnabled) ||
    !draftMeta.initialized;

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">搜索</p>
        <h1 className="mt-3 font-display text-5xl text-ink">
          用已保存的候选人画像驱动召回和排序，而不是从空白表单开始。
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          首次进入会从画像自动填充默认值。只要你改过草稿，搜索页就会保留你的修改，直到你主动从最新画像重置。
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

          <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate">
                  基础搜索条件
                </p>
                <p className="mt-2 text-sm text-slate">
                  目标职位仍然是主条件。技术栈和画像证据放在高级区，便于按画像增强并可随时重置。
                </p>
              </div>
              <label className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={forceRefresh}
                  onChange={(event) => setForceRefresh(event.target.checked)}
                />
                强制刷新
              </label>
            </div>

            <div className="mt-5 grid gap-5 lg:grid-cols-[1.2fr_1.2fr_0.7fr]">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">目标职位</span>
                <textarea
                  rows={4}
                  value={draftFields.jobTargets}
                  onChange={(event) => updateDraftField("jobTargets", event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">目标城市</span>
                <textarea
                  rows={4}
                  value={draftFields.cities}
                  onChange={(event) => updateDraftField("cities", event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  薪资下限
                </span>
                <input
                  value={draftFields.salaryFloor}
                  onChange={(event) => updateDraftField("salaryFloor", event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2 lg:col-span-3">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  必备关键词
                </span>
                <textarea
                  rows={3}
                  value={draftFields.mustHaveKeywords}
                  onChange={(event) =>
                    updateDraftField("mustHaveKeywords", event.target.value)
                  }
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              {mode === "guided_apply" && !guidedApplyEnabled ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => guidedConsentMutation.mutate()}
                  disabled={guidedConsentMutation.isPending}
                >
                  <ShieldAlert size={16} />
                  {guidedConsentMutation.isPending
                    ? "正在保存同意..."
                    : "启用引导投递"}
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
          </section>

          <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate">
                  画像增强
                </p>
                <p className="mt-2 text-sm text-slate">
                  查看并编辑技术栈、项目证据和奖项摘要，它们会参与搜索默认值、抓取关键词扩展和排序打分。
                </p>
              </div>
              <button
                type="button"
                onClick={resetFromProfile}
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-sm font-medium text-ink transition hover:border-ink/20"
                disabled={!profileQuery.data}
              >
                <RotateCcw size={16} />
                从画像重置
              </button>
            </div>

            {profileChangedNotice ? (
              <div className="mt-4 rounded-[24px] border border-signal/30 bg-signal/15 px-4 py-3 text-sm text-ink">
                你修改草稿后，已保存画像发生了变化。当前草稿已保留；如果想使用最新画像默认值，请执行重置。
              </div>
            ) : null}

            <div className="mt-5 grid gap-5">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">技术栈</span>
                <textarea
                  rows={3}
                  value={draftFields.techStack}
                  onChange={(event) => updateDraftField("techStack", event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
                <div className="flex flex-wrap gap-2">
                  {splitCommaValues(draftFields.techStack).map((item) => (
                    <span
                      key={item}
                      className="rounded-full border border-ink/10 bg-paper px-3 py-1 text-xs text-slate"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </label>

              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  项目经历
                </span>
                <textarea
                  rows={6}
                  value={draftFields.projectExperiences}
                  onChange={(event) =>
                    updateDraftField("projectExperiences", event.target.value)
                  }
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
                <p className="text-xs text-slate">
                  格式：<code>项目名 | 角色 | 摘要 | React/TypeScript</code>
                </p>
              </label>

              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">奖项</span>
                <textarea
                  rows={5}
                  value={draftFields.awards}
                  onChange={(event) => updateDraftField("awards", event.target.value)}
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
                <p className="text-xs text-slate">
                  格式：<code>奖项名 | 颁发方 | 2024 | 摘要</code>
                </p>
              </label>
            </div>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
              <p className="text-xs uppercase tracking-[0.24em] text-slate">当前限制</p>
              <div className="mt-5 grid grid-cols-2 gap-4">
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
                冷却截止：{riskStatusQuery.data?.cooldown_until || "无"}
              </p>
            </section>

            <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
              <p className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-slate">
                <AlertTriangle size={16} />
                已选平台能力
              </p>
              <div className="mt-5 space-y-4">
                {selectedPlatformCapabilities.map((platform) => (
                  <div
                    key={platform.platform}
                    className="rounded-[24px] bg-paper p-5 text-sm text-slate"
                  >
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
