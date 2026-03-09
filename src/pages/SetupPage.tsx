import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers3, UploadCloud } from "lucide-react";
import { type ChangeEvent, useEffect, useState } from "react";
import { api } from "../lib/api";
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
  source_language: "zh-CN",
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
      source_language: profileQuery.data.source_language,
    });
  }, [profileQuery.data]);

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
            候选人画像
          </p>
          <h1 className="mt-3 font-display text-5xl text-ink">
            简历数据只保存在本地，并提供给各个平台模块复用。
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate">
            上传一次简历后，把结构化画像维护干净。官网搜索和引导投递都会复用这份本地候选人数据。
          </p>
        </section>

        <section className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl bg-shell p-3 text-ember">
              <Layers3 size={20} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ember">
                模块边界
              </p>
              <p className="mt-3 font-display text-4xl text-ink">
                每个平台都保持独立模块
              </p>
              <p className="mt-4 text-sm leading-7 text-slate">
                主分支只暴露平台注册信息和共享契约。Boss 目前保留为灰色占位，官网模块为当前可用实现。
              </p>
            </div>
          </div>
        </section>
      </header>

      <section className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            简历导入
          </p>
          <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-ink/20 bg-paper px-6 py-12 text-center transition hover:border-ink/40">
            <UploadCloud size={34} className="text-ink" />
            <p className="mt-4 font-medium text-ink">上传 PDF 或 DOCX 简历</p>
            <p className="mt-2 text-sm text-slate">
              解析过程只在本地执行，导入后你仍然可以手动修正每一个字段。
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
            <p className="text-xs uppercase tracking-[0.2em] text-slate">
              已注册平台模块
            </p>
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
                    搜索：{platform.search_supported ? "已启用" : "未启用"} · 查看：
                    {platform.review_open_supported ? "已启用" : "未启用"} · 引导投递：
                    {platform.guided_apply_supported ? "已启用" : "未启用"}
                  </p>
                  <p className="mt-1 text-sm text-slate">
                    {platform.selectable ? "可选" : platform.disabled_reason || "未启用"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <div className="grid gap-5 md:grid-cols-2">
            {[
              ["姓名", "full_name"],
              ["职位标题", "headline"],
              ["目标岗位", "target_roles"],
              ["期望城市", "preferred_cities"],
              ["薪资下限", "salary_floor"],
              ["工作年限", "years_experience"],
              ["学历", "degree"],
              ["技能关键词", "skills"],
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
            <span className="text-xs uppercase tracking-[0.2em] text-slate">
              个人摘要
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
            {saveMutation.isPending ? "正在保存..." : "保存画像"}
          </button>
        </div>
      </section>
    </div>
  );
}
