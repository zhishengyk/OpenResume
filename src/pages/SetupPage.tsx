import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, UploadCloud } from "lucide-react";
import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { splitCommaValues } from "../lib/utils";

export function SetupPage() {
  const queryClient = useQueryClient();
  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: api.getProfile,
  });
  const platformsQuery = useQuery({
    queryKey: ["platforms"],
    queryFn: api.getPlatforms,
  });
  const bossSessionQuery = useQuery({
    queryKey: ["platform-session", "boss"],
    queryFn: () => api.getPlatformSession("boss"),
  });

  const [draft, setDraft] = useState(() => ({
    full_name: "",
    headline: "",
    summary: "",
    target_roles: "",
    preferred_cities: "",
    salary_floor: "0",
    years_experience: "0",
    degree: "",
    skills: "",
    must_have_keywords: "",
    source_language: "zh-CN",
  }));

  const activeProfile = useMemo(() => {
    if (!profileQuery.data) {
      return null;
    }

    return {
      ...profileQuery.data,
      target_roles: profileQuery.data.target_roles.join(", "),
      preferred_cities: profileQuery.data.preferred_cities.join(", "),
      salary_floor: String(profileQuery.data.salary_floor || 0),
      years_experience: String(profileQuery.data.years_experience || 0),
      skills: profileQuery.data.skills.join(", "),
      must_have_keywords: profileQuery.data.must_have_keywords.join(", "),
    };
  }, [profileQuery.data]);

  useEffect(() => {
    if (!activeProfile) {
      return;
    }

    setDraft({
      full_name: activeProfile.full_name,
      headline: activeProfile.headline,
      summary: activeProfile.summary,
      target_roles: activeProfile.target_roles,
      preferred_cities: activeProfile.preferred_cities,
      salary_floor: activeProfile.salary_floor,
      years_experience: activeProfile.years_experience,
      degree: activeProfile.degree,
      skills: activeProfile.skills,
      must_have_keywords: activeProfile.must_have_keywords,
      source_language: activeProfile.source_language,
    });
  }, [activeProfile]);

  const uploadMutation = useMutation({
    mutationFn: api.uploadResume,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateProfile({
        id: profileQuery.data?.id ?? 1,
        full_name: draft.full_name || profileQuery.data?.full_name || "",
        headline: draft.headline || profileQuery.data?.headline || "",
        summary: draft.summary || profileQuery.data?.summary || "",
        target_roles: splitCommaValues(
          draft.target_roles || profileQuery.data?.target_roles.join(", ") || "",
        ),
        preferred_cities: splitCommaValues(
          draft.preferred_cities ||
            profileQuery.data?.preferred_cities.join(", ") ||
            "",
        ),
        salary_floor: Number(
          draft.salary_floor || profileQuery.data?.salary_floor || 0,
        ),
        years_experience: Number(
          draft.years_experience || profileQuery.data?.years_experience || 0,
        ),
        degree: draft.degree || profileQuery.data?.degree || "",
        skills: splitCommaValues(
          draft.skills || profileQuery.data?.skills.join(", ") || "",
        ),
        must_have_keywords: splitCommaValues(
          draft.must_have_keywords ||
            profileQuery.data?.must_have_keywords.join(", ") ||
            "",
        ),
        source_filename: profileQuery.data?.source_filename,
        source_language:
          draft.source_language || profileQuery.data?.source_language || "zh-CN",
        updated_at: profileQuery.data?.updated_at,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const sessionMutation = useMutation({
    mutationFn: () => api.startPlatformSession("boss"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform-session", "boss"] });
    },
  });

  const handleUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    uploadMutation.mutate(file);
  };

  return (
    <div className="space-y-6">
      <header className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            Candidate profile
          </p>
          <h1 className="mt-3 font-display text-5xl italic text-ink">
            Build the profile once, then drive every search from it.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate">
            Upload a single PDF or DOCX resume, review the extracted intent, and
            keep the structured profile tighter than the raw document.
          </p>
        </section>

        <section className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-ember">
            Session hygiene
          </p>
          <p className="mt-3 font-display text-4xl italic text-ink">
            Dedicated browser state only
          </p>
          <p className="mt-4 text-sm leading-7 text-slate">
            The app keeps a separate local session directory. It does not read
            your normal browser profile or store your platform password.
          </p>
          <button
            type="button"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
            onClick={() => sessionMutation.mutate()}
          >
            <ShieldCheck size={16} />
            {sessionMutation.isPending ? "Opening session..." : "Start Boss session"}
          </button>
          {bossSessionQuery.data ? (
            <p className="mt-3 text-sm text-ink/80">
              Session status:{" "}
              <span className="font-semibold">
                {bossSessionQuery.data.active ? "active" : "inactive"}
              </span>
            </p>
          ) : null}
        </section>
      </header>

      <section className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            Resume intake
          </p>
          <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-ink/20 bg-paper px-6 py-12 text-center transition hover:border-ink/40">
            <UploadCloud size={34} className="text-ink" />
            <p className="mt-4 font-medium text-ink">
              Upload PDF or DOCX resume
            </p>
            <p className="mt-2 text-sm text-slate">
              Extraction is local-first. You can adjust every structured field afterwards.
            </p>
            <input
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={handleUpload}
            />
          </label>
          {uploadMutation.isPending ? (
            <p className="mt-4 text-sm text-slate">Parsing resume...</p>
          ) : null}
          {profileQuery.data?.source_filename ? (
            <p className="mt-4 text-sm text-slate">
              Loaded from: {profileQuery.data.source_filename}
            </p>
          ) : null}

          <div className="mt-6 rounded-[24px] border border-ink/10 bg-paper p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">
              Connected platforms
            </p>
            <div className="mt-3 space-y-3">
              {platformsQuery.data?.map((platform) => (
                <div
                  key={platform.platform}
                  className="rounded-2xl border border-ink/10 bg-shell px-4 py-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-ink">{platform.label}</p>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate">
                      rules {platform.rule_pack_version}
                    </p>
                  </div>
                  <p className="mt-2 text-sm text-slate">
                    Search: {String(platform.search_supported)} · Review:{" "}
                    {String(platform.review_open_supported)} · Guided apply:{" "}
                    {String(platform.guided_apply_supported)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <div className="grid gap-5 md:grid-cols-2">
            {[
              ["Full name", "full_name"],
              ["Headline", "headline"],
              ["Target roles", "target_roles"],
              ["Preferred cities", "preferred_cities"],
              ["Salary floor", "salary_floor"],
              ["Years of experience", "years_experience"],
              ["Degree", "degree"],
              ["Skills", "skills"],
              ["Must-have keywords", "must_have_keywords"],
              ["Source language", "source_language"],
            ].map(([label, key]) => (
              <label key={key} className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  {label}
                </span>
                <input
                  value={String(draft[key as keyof typeof draft] ?? "")}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      [key]: event.target.value,
                    }))
                  }
                  className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                />
              </label>
            ))}
          </div>
          <label className="mt-5 block space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate">
              Summary
            </span>
            <textarea
              value={draft.summary}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  summary: event.target.value,
                }))
              }
              rows={6}
              className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
            />
          </label>
          <button
            type="button"
            className="mt-5 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? "Saving profile..." : "Save profile"}
          </button>
        </div>
      </section>
    </div>
  );
}
