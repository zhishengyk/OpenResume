import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { modeLabel, pillLabel } from "../lib/utils";
import type { JobLocationOption, JobMatch } from "../types";
import { StatusPill } from "./StatusPill";

interface MatchCardProps {
  match: JobMatch;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (listingId: string) => void;
}

type PendingAction = "review" | "guided_apply" | "open_raw";

interface LocationPickerDialogProps {
  open: boolean;
  options: JobLocationOption[];
  selectedListingId: string;
  onSelect: (listingId: string) => void;
  onClose: () => void;
  onConfirm: () => void;
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

function openExternal(url: string) {
  if (window.openResumeDesktop?.openExternal) {
    window.openResumeDesktop.openExternal(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function buildExcerpt(match: JobMatch, maxLength: number = 120) {
  const text = match.requirements_text || match.description_text || "";
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}

function locationLabel(option: JobLocationOption) {
  return option.location_city || option.location_raw || "地点未知";
}

function normalizeLocationOptions(match: JobMatch): JobLocationOption[] {
  const source =
    Array.isArray(match.location_options) && match.location_options.length
      ? match.location_options
      : [
          {
            listing_id: match.listing_id,
            location_city: match.location_city,
            location_raw: match.location_raw,
            apply_url: match.apply_url,
          },
        ];

  const deduped: JobLocationOption[] = [];
  const seen = new Set<string>();
  for (const option of source) {
    const key = `${(locationLabel(option) || "").trim().toLowerCase()}|${(
      option.apply_url || ""
    ).trim().toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(option);
  }
  return deduped;
}

function buildLocationDisplay(match: JobMatch, options: JobLocationOption[]) {
  if (match.location_display?.trim()) {
    return match.location_display;
  }
  const labels = Array.from(
    new Set(options.map((option) => locationLabel(option)).filter(Boolean)),
  );
  if (labels.length) {
    return labels.join("/");
  }
  return match.location_city || match.location_raw || "地点未知";
}

function LocationPickerDialog({
  open,
  options,
  selectedListingId,
  onSelect,
  onClose,
  onConfirm,
}: LocationPickerDialogProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-ink/45 px-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-[32px] border border-ink/10 bg-shell p-6 shadow-console"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="选择地点"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate">多地点岗位</p>
            <h3 className="mt-2 font-display text-3xl text-ink">选择要打开的地点</h3>
            <p className="mt-2 text-sm leading-7 text-slate">
              该岗位在多个地点都有入口，确认一个地点后继续。
            </p>
          </div>
          <button
            type="button"
            className="rounded-full border border-ink/10 bg-paper p-2 text-ink transition hover:bg-shell"
            onClick={onClose}
            aria-label="关闭地点选择"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-5 space-y-2">
          {options.map((option) => {
            const checked = option.listing_id === selectedListingId;
            return (
              <button
                key={option.listing_id}
                type="button"
                className={`flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition ${
                  checked
                    ? "border-ink bg-ink text-shell"
                    : "border-ink/10 bg-paper text-ink hover:bg-shell"
                }`}
                onClick={() => onSelect(option.listing_id)}
              >
                <span className="text-sm font-semibold">{locationLabel(option)}</span>
                <span className="text-xs opacity-80">{checked ? "已选择" : "选择"}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            className="rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper"
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
            disabled={!selectedListingId}
            onClick={onConfirm}
          >
            确认并继续
          </button>
        </div>
      </div>
    </div>
  );
}

export function MatchCard({
  match,
  selectable = false,
  selected = false,
  onToggleSelect,
}: MatchCardProps) {
  const queryClient = useQueryClient();
  const [isExpanded, setIsExpanded] = useState(false);
  const [locationPickerOpen, setLocationPickerOpen] = useState(false);
  const [selectedListingId, setSelectedListingId] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

  const locationOptions = useMemo(() => normalizeLocationOptions(match), [match]);
  const locationDisplay = useMemo(
    () => buildLocationDisplay(match, locationOptions),
    [match, locationOptions],
  );
  const mergedCount = Math.max(
    match.merged_count || 0,
    match.is_merged ? locationOptions.length : 1,
  );
  const isMerged = mergedCount > 1 && locationOptions.length > 1;
  const canOpenLink = locationOptions.some((option) => Boolean(option.apply_url));

  const reviewMutation = useMutation({
    mutationFn: (listingId: string) => api.openReview(listingId),
  });

  const guidedApplyMutation = useMutation({
    mutationFn: async (listingId: string) => {
      const attempt = await api.guidedApply(listingId);
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

  const closeLocationPicker = () => {
    setLocationPickerOpen(false);
    setPendingAction(null);
    setSelectedListingId("");
  };

  const executeAction = (action: PendingAction, option: JobLocationOption) => {
    if (!option.listing_id) {
      return;
    }
    if (action === "review") {
      reviewMutation.mutate(option.listing_id);
      return;
    }
    if (action === "guided_apply") {
      guidedApplyMutation.mutate(option.listing_id);
      return;
    }
    if (option.apply_url) {
      openExternal(option.apply_url);
    }
  };

  const startAction = (action: PendingAction) => {
    if (!locationOptions.length) {
      return;
    }
    if (!isMerged) {
      executeAction(action, locationOptions[0]);
      return;
    }
    setPendingAction(action);
    setSelectedListingId(locationOptions[0].listing_id);
    setLocationPickerOpen(true);
  };

  const confirmLocationAction = () => {
    if (!pendingAction || !locationOptions.length) {
      closeLocationPicker();
      return;
    }
    const selected =
      locationOptions.find((option) => option.listing_id === selectedListingId) ||
      locationOptions[0];
    executeAction(pendingAction, selected);
    closeLocationPicker();
  };

  return (
    <>
      <article className="overflow-hidden rounded-[24px] border border-ink/10 bg-shell/90 shadow-console">
        <div
          className="cursor-pointer p-5 transition-colors hover:bg-paper/50"
          onClick={() => setIsExpanded((value) => !value)}
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {selectable ? (
                  <label
                    className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-ink"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => onToggleSelect?.(match.listing_id)}
                    />
                    {selected ? "已选中" : "加入批量"}
                  </label>
                ) : null}
                <StatusPill>{match.source_site}</StatusPill>
                {match.analysis_degraded ? <StatusPill>降级</StatusPill> : null}
                {isMerged ? <StatusPill>{`多地点 ${mergedCount}`}</StatusPill> : null}
              </div>
              <h3 className="mt-2 truncate font-display text-2xl text-ink">{match.title}</h3>
              <p className="mt-1 text-sm text-slate">
                {match.source_company} · {locationDisplay} ·{" "}
                {match.employment_type || "类型未知"}
              </p>
              {!isExpanded ? (
                <p className="mt-2 line-clamp-2 text-sm text-slate/70">
                  {excerpt || "暂无职位描述"}
                </p>
              ) : null}
            </div>

            <div className="flex items-center gap-4">
              <div className="text-center">
                <p className="text-xs uppercase tracking-[0.15em] text-slate">得分</p>
                <p className="font-display text-3xl text-ink">
                  {Math.round(match.final_score)}
                </p>
              </div>
              <button
                type="button"
                className="rounded-full p-2 transition-colors hover:bg-ink/5"
                onClick={(event) => {
                  event.stopPropagation();
                  setIsExpanded((value) => !value);
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

        {isExpanded ? (
          <div className="space-y-4 border-t border-ink/10 p-5">
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
                <p className="text-xs font-medium uppercase tracking-[0.15em] text-slate">
                  匹配摘要
                </p>
                <p className="mt-2 text-sm leading-6 text-ink">
                  {match.llm_summary || "当前展示的是规则排序结果，模型分析完成后会在这里补充摘要。"}
                </p>
              </div>

              <div className="space-y-3">
                <div className="rounded-xl border border-mint/30 bg-mint/10 p-3">
                  <p className="text-xs uppercase tracking-[0.15em] text-slate">匹配亮点</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {match.highlights.length ? (
                      match.highlights.slice(0, 5).map((item) => (
                        <span
                          key={item}
                          className="rounded-full bg-shell px-2.5 py-1 text-xs text-ink"
                        >
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
                      [...match.missing_keywords, ...match.risk_flags]
                        .slice(0, 4)
                        .map((item) => (
                          <span
                            key={item}
                            className="rounded-full bg-shell px-2.5 py-1 text-xs text-ink"
                          >
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
              <p className="text-xs font-medium uppercase tracking-[0.15em] text-slate">
                职位描述
              </p>
              <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-slate">
                {match.description_text || match.requirements_text || "暂无描述"}
              </pre>
            </div>

            <div className="flex flex-wrap gap-2 pt-2">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-ink px-4 py-2 text-sm font-medium text-shell transition hover:bg-ink/90"
                onClick={() => startAction("review")}
                disabled={reviewMutation.isPending || !canOpenLink}
              >
                <ArrowUpRight size={14} />
                {reviewMutation.isPending ? "正在打开..." : "打开职位页面"}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-medium text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => startAction("guided_apply")}
                disabled={guidedApplyMutation.isPending || !canOpenLink}
              >
                <Zap size={14} />
                {guidedApplyMutation.isPending ? "准备中..." : "引导投递"}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-full border border-ember/20 bg-ember/10 px-4 py-2 text-sm font-medium text-ink transition hover:bg-ember/15"
                onClick={() => startAction("open_raw")}
                disabled={!canOpenLink}
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
              平台：{pillLabel(match.platform)} · 模式：
              {modeLabel(match.apply_supported ? "guided_apply" : "review_in_browser")}
            </p>
          </div>
        ) : null}
      </article>

      <LocationPickerDialog
        open={locationPickerOpen}
        options={locationOptions}
        selectedListingId={selectedListingId}
        onSelect={setSelectedListingId}
        onClose={closeLocationPicker}
        onConfirm={confirmLocationAction}
      />
    </>
  );
}
