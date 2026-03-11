import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Trash2, Upload, Vault } from "lucide-react";
import { useMemo, useState } from "react";
import { MetricCard } from "../components/MetricCard";
import { StatusPill } from "../components/StatusPill";
import { api } from "../lib/api";
import { pillLabel } from "../lib/utils";
import type { OfficialAccount } from "../types";

interface AccountDraft {
  display_name: string;
  username: string;
  password: string;
  is_default: boolean;
}

const emptyDraft = (): AccountDraft => ({
  display_name: "",
  username: "",
  password: "",
  is_default: true,
});

export function AccountPoolPage() {
  const queryClient = useQueryClient();
  const [accountDrafts, setAccountDrafts] = useState<Record<string, AccountDraft>>({});
  const [assetLabel, setAssetLabel] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const sitesQuery = useQuery({
    queryKey: ["official-sites"],
    queryFn: api.getOfficialSites,
  });
  const accountsQuery = useQuery({
    queryKey: ["official-accounts"],
    queryFn: () => api.listOfficialAccounts(),
  });
  const assetsQuery = useQuery({
    queryKey: ["resume-assets"],
    queryFn: api.listResumeAssets,
  });
  const bindingsQuery = useQuery({
    queryKey: ["company-bindings"],
    queryFn: api.listCompanyBindings,
  });

  const refreshPoolQueries = () => {
    void queryClient.invalidateQueries({ queryKey: ["official-accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["resume-assets"] });
    void queryClient.invalidateQueries({ queryKey: ["company-bindings"] });
  };

  const createAccountMutation = useMutation({
    mutationFn: (payload: {
      company_key: string;
      display_name: string;
      username: string;
      password?: string | null;
      is_default: boolean;
      status: string;
    }) => api.createOfficialAccount(payload),
    onSuccess: (_, payload) => {
      setAccountDrafts((current) => ({
        ...current,
        [payload.company_key]: emptyDraft(),
      }));
      refreshPoolQueries();
    },
  });

  const updateAccountMutation = useMutation({
    mutationFn: (payload: {
      accountId: string;
      company_key: string;
      display_name: string;
      username: string;
      password?: string | null;
      is_default: boolean;
      status: string;
    }) =>
      api.updateOfficialAccount(payload.accountId, {
        company_key: payload.company_key,
        display_name: payload.display_name,
        username: payload.username,
        password: payload.password,
        is_default: payload.is_default,
        status: payload.status,
      }),
    onSuccess: refreshPoolQueries,
  });

  const deleteAccountMutation = useMutation({
    mutationFn: (accountId: string) => api.deleteOfficialAccount(accountId),
    onSuccess: refreshPoolQueries,
  });

  const uploadAssetMutation = useMutation({
    mutationFn: ({ file, label }: { file: File; label?: string }) =>
      api.uploadResumeAsset(file, label),
    onSuccess: () => {
      setAssetLabel("");
      setSelectedFile(null);
      refreshPoolQueries();
    },
  });

  const deleteAssetMutation = useMutation({
    mutationFn: (resumeAssetId: string) => api.deleteResumeAsset(resumeAssetId),
    onSuccess: refreshPoolQueries,
  });

  const updateBindingMutation = useMutation({
    mutationFn: (payload: { companyKey: string; defaultResumeAssetId?: string | null }) =>
      api.updateCompanyBinding(payload.companyKey, payload.defaultResumeAssetId),
    onSuccess: refreshPoolQueries,
  });

  const accountsByCompany = useMemo(() => {
    const grouped = new Map<string, OfficialAccount[]>();
    for (const account of accountsQuery.data || []) {
      const items = grouped.get(account.company_key) || [];
      items.push(account);
      grouped.set(account.company_key, items);
    }
    return grouped;
  }, [accountsQuery.data]);

  const bindingsByCompany = useMemo(() => {
    const grouped = new Map<string, string | null>();
    for (const binding of bindingsQuery.data || []) {
      grouped.set(binding.company_key, binding.default_resume_asset_id || null);
    }
    return grouped;
  }, [bindingsQuery.data]);

  const defaultAccountCount = (accountsQuery.data || []).filter((item) => item.is_default).length;
  const boundCompanyCount = (bindingsQuery.data || []).filter(
    (item) => item.default_resume_asset_id,
  ).length;

  const globalError =
    (sitesQuery.error instanceof Error && sitesQuery.error.message) ||
    (accountsQuery.error instanceof Error && accountsQuery.error.message) ||
    (assetsQuery.error instanceof Error && assetsQuery.error.message) ||
    (bindingsQuery.error instanceof Error && bindingsQuery.error.message) ||
    (createAccountMutation.error instanceof Error && createAccountMutation.error.message) ||
    (updateAccountMutation.error instanceof Error && updateAccountMutation.error.message) ||
    (uploadAssetMutation.error instanceof Error && uploadAssetMutation.error.message) ||
    (updateBindingMutation.error instanceof Error && updateBindingMutation.error.message) ||
    (deleteAccountMutation.error instanceof Error && deleteAccountMutation.error.message) ||
    (deleteAssetMutation.error instanceof Error && deleteAssetMutation.error.message) ||
    null;

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="absolute inset-0 bg-grid-fade bg-[size:22px_22px] opacity-35" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.24em] text-slate">
              {"\u8d26\u53f7\u4e0e\u7b80\u5386\u6c60"}
            </p>
            <h1 className="mt-3 font-display text-5xl text-ink">
              {"\u628a\u5b98\u7f51\u8d26\u53f7\u3001\u4f1a\u8bdd\u7f13\u5b58\u548c\u9ed8\u8ba4\u7b80\u5386\u90fd\u6536\u8fdb\u540c\u4e00\u4e2a\u6295\u9012\u8d44\u4ea7\u5e93"}
            </h1>
            <p className="mt-4 text-sm leading-7 text-slate">
              {
                "\u6279\u91cf\u6295\u9012\u4f1a\u4ece\u8fd9\u91cc\u8bfb\u53d6\u6bcf\u5bb6\u516c\u53f8\u7684\u9ed8\u8ba4\u8d26\u53f7\u548c\u7b80\u5386\u3002\u7f13\u5b58\u7684 storage state \u4e5f\u4f1a\u8ddf\u8d26\u53f7\u7ed1\u5b9a\u5c55\u793a\u5728\u6b64\u9875\u3002"
              }
            </p>
          </div>
          <div className="rounded-[28px] border border-ink/10 bg-paper/80 p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">
              {"\u6295\u9012\u7b56\u7565"}
            </p>
            <p className="mt-3 max-w-xs text-sm leading-7 text-ink">
              {
                "\u9ed8\u8ba4\u4f7f\u7528\u534a\u81ea\u52a8\u6a21\u5f0f\uff0c\u81ea\u52a8\u586b\u5199\u540e\u505c\u5728\u6700\u7ec8\u63d0\u4ea4\u524d\u3002\u5168\u81ea\u52a8\u6a21\u5f0f\u53ea\u5728\u7ed3\u679c\u9875\u663e\u5f0f\u5f00\u542f\u3002"
              }
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <MetricCard
          label="\u5df2\u914d\u7f6e\u7ad9\u70b9"
          value={String(sitesQuery.data?.length || 0)}
          hint="\u9996\u6279\u56fa\u5b9a\u8986\u76d6 5 \u5bb6\u5b98\u7f51"
        />
        <MetricCard
          label="\u9ed8\u8ba4\u8d26\u53f7"
          value={String(defaultAccountCount)}
          hint="\u6bcf\u5bb6\u516c\u53f8\u6700\u591a\u53ea\u4f1a\u6709\u4e00\u4e2a\u9ed8\u8ba4\u8d26\u53f7"
        />
        <MetricCard
          label="\u7ed1\u5b9a\u7b80\u5386"
          value={String(boundCompanyCount)}
          hint="\u6279\u91cf\u6295\u9012\u4f1a\u76f4\u63a5\u5957\u7528\u8fd9\u4e9b\u9ed8\u8ba4\u7b80\u5386"
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.82fr_1.18fr]">
        <div className="space-y-6">
          <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
            <div className="flex items-center gap-3">
              <Vault size={18} className="text-slate" />
              <p className="text-xs uppercase tracking-[0.22em] text-slate">
                {"\u7b80\u5386\u8d44\u4ea7"}
              </p>
            </div>

            <div className="mt-5 space-y-3 rounded-[28px] border border-ink/10 bg-paper p-4">
              <label className="space-y-2">
                <span className="text-xs uppercase tracking-[0.18em] text-slate">
                  {"\u8d44\u4ea7\u540d\u79f0"}
                </span>
                <input
                  value={assetLabel}
                  onChange={(event) => setAssetLabel(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-shell px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                  placeholder="\u4f8b\u5982\uff1a2026 \u793e\u62db\u7248"
                />
              </label>

              <label className="flex min-h-[148px] cursor-pointer flex-col items-center justify-center rounded-[28px] border border-dashed border-ink/20 bg-shell text-center transition hover:border-ink/35 hover:bg-paper">
                <Upload size={18} className="text-slate" />
                <p className="mt-4 text-sm font-semibold text-ink">
                  {selectedFile?.name || "\u9009\u62e9 PDF / DOCX \u7b80\u5386"}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate">
                  {"\u5355\u51fb\u66ff\u6362\u6587\u4ef6"}
                </p>
                <input
                  type="file"
                  accept=".pdf,.docx"
                  className="hidden"
                  onChange={(event) => {
                    setSelectedFile(event.target.files?.[0] || null);
                  }}
                />
              </label>

              <button
                type="button"
                className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
                disabled={!selectedFile || uploadAssetMutation.isPending}
                onClick={() => {
                  if (!selectedFile) {
                    return;
                  }
                  uploadAssetMutation.mutate({ file: selectedFile, label: assetLabel });
                }}
              >
                {uploadAssetMutation.isPending ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : (
                  <Upload size={16} />
                )}
                {uploadAssetMutation.isPending
                  ? "\u4e0a\u4f20\u4e2d..."
                  : "\u6536\u8fdb\u7b80\u5386\u6c60"}
              </button>
            </div>

            <div className="mt-5 space-y-3">
              {(assetsQuery.data || []).map((asset) => (
                <div
                  key={asset.id}
                  className="rounded-[24px] border border-ink/10 bg-paper px-4 py-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-ink">{asset.label}</p>
                      <p className="mt-1 truncate text-sm text-slate">{asset.source_filename}</p>
                      <p className="mt-2 text-xs text-slate">
                        {new Date(asset.updated_at).toLocaleString()}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="rounded-full border border-ink/10 bg-shell p-2 text-ink transition hover:bg-paper disabled:opacity-50"
                      disabled={deleteAssetMutation.isPending}
                      onClick={() => deleteAssetMutation.mutate(asset.id)}
                      aria-label="\u5220\u9664\u7b80\u5386\u8d44\u4ea7"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
              {!assetsQuery.data?.length ? (
                <div className="rounded-[24px] border border-dashed border-ink/15 bg-paper px-4 py-5 text-sm leading-7 text-slate">
                  {"\u6682\u65e0\u6295\u9012\u8d44\u4ea7\u3002\u5148\u4e0a\u4f20\u4e00\u4efd\u7b80\u5386\uff0c\u518d\u7ed9\u6bcf\u5bb6\u5b98\u7f51\u914d\u7f6e\u9ed8\u8ba4\u7ed1\u5b9a\u3002"}
                </div>
              ) : null}
            </div>
          </section>
        </div>

        <section className="space-y-4">
          {(sitesQuery.data || []).map((site) => {
            const siteAccounts = accountsByCompany.get(site.company_key) || [];
            const draft = accountDrafts[site.company_key] || emptyDraft();
            const selectedResumeId = bindingsByCompany.get(site.company_key) || "";
            return (
              <article
                key={site.company_key}
                className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate">
                      {site.label}
                    </p>
                    <h2 className="mt-2 font-display text-3xl text-ink">
                      {site.company_name}
                    </h2>
                    <p className="mt-2 text-sm leading-7 text-slate">
                      {site.source_sites.join(" | ")} |{" "}
                      {site.supported_variants.map((item) => pillLabel(item)).join(" / ")}
                    </p>
                  </div>
                  <div className="rounded-3xl border border-ink/10 bg-paper px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate">
                      {"\u9ed8\u8ba4\u7b80\u5386"}
                    </p>
                    <select
                      value={selectedResumeId}
                      className="mt-2 min-w-[220px] rounded-2xl border border-ink/10 bg-shell px-3 py-2 text-sm text-ink outline-none"
                      onChange={(event) =>
                        updateBindingMutation.mutate({
                          companyKey: site.company_key,
                          defaultResumeAssetId: event.target.value || null,
                        })
                      }
                    >
                      <option value="">{"\u672a\u7ed1\u5b9a"}</option>
                      {(assetsQuery.data || []).map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-5 grid gap-5 xl:grid-cols-[1.08fr_0.92fr]">
                  <div className="space-y-3">
                    {siteAccounts.map((account) => (
                      <div
                        key={account.id}
                        className="rounded-[26px] border border-ink/10 bg-paper px-4 py-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="font-semibold text-ink">{account.display_name}</p>
                              {account.is_default ? <StatusPill>default</StatusPill> : null}
                              <StatusPill>{account.status}</StatusPill>
                              <StatusPill>
                                {account.session_cache?.status || "missing"}
                              </StatusPill>
                            </div>
                            <p className="mt-1 text-sm text-slate">{account.username}</p>
                            <p className="mt-2 text-xs text-slate">
                              {account.session_cache?.storage_state_path ||
                                "\u6682\u65e0\u7f13\u5b58\u8def\u5f84"}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {!account.is_default ? (
                              <button
                                type="button"
                                className="rounded-full border border-ink/10 bg-shell px-4 py-2 text-sm font-semibold text-ink transition hover:bg-paper disabled:opacity-50"
                                disabled={updateAccountMutation.isPending}
                                onClick={() =>
                                  updateAccountMutation.mutate({
                                    accountId: account.id,
                                    company_key: account.company_key,
                                    display_name: account.display_name,
                                    username: account.username,
                                    password: null,
                                    is_default: true,
                                    status: account.status,
                                  })
                                }
                              >
                                {"\u8bbe\u4e3a\u9ed8\u8ba4"}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="rounded-full border border-ink/10 bg-shell p-2 text-ink transition hover:bg-paper disabled:opacity-50"
                              disabled={deleteAccountMutation.isPending}
                              onClick={() => deleteAccountMutation.mutate(account.id)}
                              aria-label="\u5220\u9664\u8d26\u53f7"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                    {!siteAccounts.length ? (
                      <div className="rounded-[24px] border border-dashed border-ink/15 bg-paper px-4 py-5 text-sm leading-7 text-slate">
                        {"\u8fd8\u6ca1\u6709\u7ed9\u8fd9\u5bb6\u5b98\u7f51\u6dfb\u52a0\u53ef\u7528\u8d26\u53f7\u3002"}
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-[28px] border border-ink/10 bg-paper p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate">
                      {"\u65b0\u589e\u8d26\u53f7"}
                    </p>
                    <div className="mt-4 space-y-3">
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.16em] text-slate">
                          {"\u663e\u793a\u540d"}
                        </span>
                        <input
                          value={draft.display_name}
                          onChange={(event) =>
                            setAccountDrafts((current) => ({
                              ...current,
                              [site.company_key]: {
                                ...draft,
                                display_name: event.target.value,
                              },
                            }))
                          }
                          className="w-full rounded-2xl border border-ink/10 bg-shell px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                          placeholder="\u4f8b\u5982\uff1a\u6821\u62db\u526f\u8d26\u53f7"
                        />
                      </label>
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.16em] text-slate">
                          {"\u767b\u5f55\u540d"}
                        </span>
                        <input
                          value={draft.username}
                          onChange={(event) =>
                            setAccountDrafts((current) => ({
                              ...current,
                              [site.company_key]: {
                                ...draft,
                                username: event.target.value,
                              },
                            }))
                          }
                          className="w-full rounded-2xl border border-ink/10 bg-shell px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                          placeholder="candidate@example.com"
                        />
                      </label>
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.16em] text-slate">
                          {"\u5bc6\u7801"}
                        </span>
                        <input
                          type="password"
                          value={draft.password}
                          onChange={(event) =>
                            setAccountDrafts((current) => ({
                              ...current,
                              [site.company_key]: {
                                ...draft,
                                password: event.target.value,
                              },
                            }))
                          }
                          className="w-full rounded-2xl border border-ink/10 bg-shell px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                          placeholder="******"
                        />
                      </label>
                      <label className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-4 py-3 text-sm text-ink">
                        <input
                          type="checkbox"
                          checked={draft.is_default}
                          onChange={(event) =>
                            setAccountDrafts((current) => ({
                              ...current,
                              [site.company_key]: {
                                ...draft,
                                is_default: event.target.checked,
                              },
                            }))
                          }
                        />
                        {"\u8bbe\u4e3a\u9ed8\u8ba4\u8d26\u53f7"}
                      </label>

                      <button
                        type="button"
                        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
                        disabled={
                          createAccountMutation.isPending ||
                          !draft.username.trim() ||
                          !draft.password.trim()
                        }
                        onClick={() =>
                          createAccountMutation.mutate({
                            company_key: site.company_key,
                            display_name: draft.display_name,
                            username: draft.username,
                            password: draft.password,
                            is_default: draft.is_default,
                            status: "active",
                          })
                        }
                      >
                        {createAccountMutation.isPending ? (
                          <LoaderCircle size={16} className="animate-spin" />
                        ) : null}
                        {createAccountMutation.isPending
                          ? "\u4fdd\u5b58\u4e2d..."
                          : "\u5199\u5165\u8d26\u53f7\u6c60"}
                      </button>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      </section>

      {globalError ? (
        <section className="rounded-[28px] border border-ember/30 bg-ember/10 px-5 py-4 text-sm text-ink">
          {globalError}
        </section>
      ) : null}
    </div>
  );
}
