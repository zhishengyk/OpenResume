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
    title: "Recommend only",
    body: "Search and rank roles with no action taken on the platform.",
  },
  {
    mode: "review_in_browser",
    title: "Review in browser",
    body: "Open the role in a dedicated browser session so the user controls the page.",
  },
  {
    mode: "guided_apply",
    title: "Guided apply",
    body: "Prepare reusable details in the flow, then stop before any final submit action.",
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
  const [mustHaveKeywords, setMustHaveKeywords] = useState("React, TypeScript, Node.js");

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

  const guidedApplyEnabled = appStateQuery.data?.guided_apply_consents.includes(platform);

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">
          Search control
        </p>
        <h1 className="mt-3 font-display text-5xl italic text-ink">
          Search first. Move carefully.
        </h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
          The workflow is deliberately conservative. Risk gates sit in front of
          any guided action, and the final application submit remains user-held.
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
                  Platform
                </span>
                <select
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                >
                  <option value="boss">Boss 直聘</option>
                  <option value="liepin">猎聘 (coming next)</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  Salary floor
                </span>
                <input
                  value={salaryFloor}
                  onChange={(event) => setSalaryFloor(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  Job targets
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
                  Cities
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
                Must-have keywords
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
                    ? "Recording consent..."
                    : "Acknowledge guided-apply risk"}
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
                {searchMutation.isPending ? "Starting search..." : "Start search session"}
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-1 text-ember" size={18} />
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-ember">
                  Risk posture
                </p>
                <p className="mt-3 text-sm leading-7 text-slate">
                  This build only supports conservative timing, rate limiting,
                  and human takeover. It does not provide stealth, spoofing, or
                  anti-detection behavior.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <p className="text-xs uppercase tracking-[0.24em] text-slate">
              Current limits
            </p>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-[24px] bg-paper p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate">
                  Hourly remaining
                </p>
                <p className="mt-2 font-display text-4xl italic text-ink">
                  {riskStatusQuery.data?.remaining_hourly ?? "--"}
                </p>
              </div>
              <div className="rounded-[24px] bg-paper p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate">
                  Daily remaining
                </p>
                <p className="mt-2 font-display text-4xl italic text-ink">
                  {riskStatusQuery.data?.remaining_daily ?? "--"}
                </p>
              </div>
            </div>
            <p className="mt-5 text-sm leading-7 text-slate">
              Cooldown:{" "}
              {riskStatusQuery.data?.cooldown_until
                ? new Date(riskStatusQuery.data.cooldown_until).toLocaleString()
                : "clear"}
            </p>
            {mode === "guided_apply" ? (
              <div className="mt-5 rounded-[24px] border border-ink/10 bg-paper p-4">
                <div className="flex items-center gap-2 text-ink">
                  <AlertTriangle size={16} />
                  <p className="font-semibold">
                    Guided apply still requires final user confirmation.
                  </p>
                </div>
                <p className="mt-3 text-sm leading-7 text-slate">
                  The flow may pre-stage reusable data and open the dedicated
                  session page, but it stops before any final platform submit.
                </p>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}

