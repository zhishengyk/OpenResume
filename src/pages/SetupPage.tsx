import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers3, UploadCloud } from "lucide-react";
import { type ChangeEvent, useEffect, useState } from "react";
import { api } from "../lib/api";
import {
  parseAwards,
  parseProjectExperiences,
  serializeAwards,
  serializeProjectExperiences,
} from "../lib/profile";
import { splitCommaValues } from "../lib/utils";

const emptyDraft = {
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
  tech_stack: "",
  project_experiences: "",
  awards: "",
  source_language: "zh-CN",
  raw_text: "",
};

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

  const [draft, setDraft] = useState(emptyDraft);

  useEffect(() => {
    if (!profileQuery.data) {
      return;
    }

    setDraft({
      full_name: profileQuery.data.full_name,
      headline: profileQuery.data.headline,
      summary: profileQuery.data.summary,
      target_roles: profileQuery.data.target_roles.join(", "),
      preferred_cities: profileQuery.data.preferred_cities.join(", "),
      salary_floor: String(profileQuery.data.salary_floor || 0),
      years_experience: String(profileQuery.data.years_experience || 0),
      degree: profileQuery.data.degree,
      skills: profileQuery.data.skills.join(", "),
      must_have_keywords: profileQuery.data.must_have_keywords.join(", "),
      tech_stack: profileQuery.data.tech_stack.join(", "),
      project_experiences: serializeProjectExperiences(
        profileQuery.data.project_experiences,
      ),
      awards: serializeAwards(profileQuery.data.awards),
      source_language: profileQuery.data.source_language,
      raw_text: profileQuery.data.raw_text,
    });
  }, [profileQuery.data]);

  const uploadMutation = useMutation({
    mutationFn: api.uploadResume,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateProfile({
        id: profileQuery.data?.id ?? 1,
        full_name: draft.full_name,
        headline: draft.headline,
        summary: draft.summary,
        target_roles: splitCommaValues(draft.target_roles),
        preferred_cities: splitCommaValues(draft.preferred_cities),
        salary_floor: Number(draft.salary_floor || 0),
        years_experience: Number(draft.years_experience || 0),
        degree: draft.degree,
        skills: splitCommaValues(draft.skills),
        must_have_keywords: splitCommaValues(draft.must_have_keywords),
        tech_stack: splitCommaValues(draft.tech_stack),
        project_experiences: parseProjectExperiences(draft.project_experiences),
        awards: parseAwards(draft.awards),
        source_filename: profileQuery.data?.source_filename,
        source_language: draft.source_language || "zh-CN",
        raw_text: draft.raw_text,
        profile_signature: profileQuery.data?.profile_signature,
        updated_at: profileQuery.data?.updated_at,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
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
      <header className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            候选人画像
          </p>
          <h1 className="mt-3 font-display text-5xl text-ink">
            简历解析现在会持久化更丰富的画像，用于搜索默认值和排序打分。
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate">
            简历上传一次后，在这里维护清晰的画像数据。搜索和排序会复用同一套技术栈、项目和奖项字段。
          </p>
        </section>

        <section className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-shell p-3 text-ember">
              <Layers3 size={20} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ember">模块边界</p>
              <p className="mt-3 font-display text-4xl text-ink">
                搜索页只读取已保存的画像。
              </p>
              <p className="mt-4 text-sm leading-7 text-slate">
                搜索页可以临时修改画像增强内容，但只有保存画像或提交搜索时同步后，才会成为新的真实数据。
              </p>
            </div>
          </div>
        </section>
      </header>

      <section className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">简历上传</p>
          <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-ink/20 bg-paper px-6 py-12 text-center transition hover:border-ink/40">
            <UploadCloud size={34} className="text-ink" />
            <p className="mt-4 font-medium text-ink">上传 PDF 或 DOCX 简历</p>
            <p className="mt-2 text-sm text-slate">
              解析过程在本地执行。下方所有保存字段都可以继续手动修正。
            </p>
            <input
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={handleUpload}
            />
          </label>

          {uploadMutation.isPending ? (
            <p className="mt-4 text-sm text-slate">正在解析简历...</p>
          ) : null}
          {profileQuery.data?.source_filename ? (
            <p className="mt-4 text-sm text-slate">
              当前简历：{profileQuery.data.source_filename}
            </p>
          ) : null}

          <div className="mt-6 rounded-[24px] border border-ink/10 bg-paper p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">平台模块</p>
            <div className="mt-3 space-y-3">
              {platformsQuery.data?.map((platform) => (
                <div
                  key={platform.platform}
                  className={`rounded-2xl border px-4 py-3 ${
                    platform.selectable
                      ? "border-ink/10 bg-shell"
                      : "border-ink/10 bg-shell/60"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-ink">{platform.label}</p>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate">
                      规则包 {platform.rule_pack_version}
                    </p>
                  </div>
                  <p className="mt-2 text-sm text-slate">
                    搜索：{platform.search_supported ? "已启用" : "未启用"} | 查看：
                    {platform.review_open_supported ? "已启用" : "未启用"} | 引导投递：
                    {platform.guided_apply_supported ? "已启用" : "未启用"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="grid gap-5 md:grid-cols-2">
              {[
                ["姓名", "full_name"],
                ["职位标题", "headline"],
                ["目标职位", "target_roles"],
                ["期望城市", "preferred_cities"],
                ["薪资下限", "salary_floor"],
                ["工作年限", "years_experience"],
                ["学历", "degree"],
                ["技能", "skills"],
                ["必备关键词", "must_have_keywords"],
                ["简历语言", "source_language"],
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
              <span className="text-xs uppercase tracking-[0.2em] text-slate">个人摘要</span>
              <textarea
                value={draft.summary}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    summary: event.target.value,
                  }))
                }
                rows={5}
                className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
              />
            </label>
          </section>

          <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate">
                  画像增强
                </p>
                <p className="mt-2 text-sm text-slate">
                  保持轻量格式：每个项目或奖项占一行，字段之间用 <code>|</code> 分隔。
                </p>
              </div>
              <div className="text-xs text-slate">
                已保存原始简历文本：{draft.raw_text.length} 字
              </div>
            </div>

            <div className="mt-5 grid gap-5">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">技术栈</span>
                <textarea
                  rows={3}
                  value={draft.tech_stack}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      tech_stack: event.target.value,
                    }))
                  }
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
              </label>

              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.2em] text-slate">
                  项目经历
                </span>
                <textarea
                  rows={6}
                  value={draft.project_experiences}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      project_experiences: event.target.value,
                    }))
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
                  value={draft.awards}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      awards: event.target.value,
                    }))
                  }
                  className="w-full rounded-[24px] border border-ink/10 bg-paper px-4 py-3 text-sm leading-7 text-ink outline-none transition focus:border-ink/30"
                />
                <p className="text-xs text-slate">
                  格式：<code>奖项名 | 颁发方 | 2024 | 摘要</code>
                </p>
              </label>
            </div>

            <button
              type="button"
              className="mt-5 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? "保存中..." : "保存画像"}
            </button>
          </section>
        </div>
      </section>
    </div>
  );
}
