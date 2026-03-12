import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  LoaderCircle,
  LogIn,
  Trash2,
  Upload,
  Vault,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { cn, pillLabel } from "../lib/utils";
import type { OfficialAccount, OfficialSite } from "../types";

interface AccountDraft {
  display_name: string;
}

const createEmptyDraft = (): AccountDraft => ({
  display_name: "",
});

function formatDate(value?: string | null) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString();
}

function loginTone(isLoggedIn: boolean) {
  return isLoggedIn
    ? "border-mint/40 bg-mint/15 text-ink"
    : "border-ember/20 bg-ember/10 text-ember";
}

function cacheStatusLabel(status?: string | null) {
  switch ((status || "").trim()) {
    case "ready":
      return "已缓存";
    case "missing":
      return "未检测到";
    case "error":
      return "缓存异常";
    default:
      return "未检测";
  }
}

export function AccountPoolPage() {
  const queryClient = useQueryClient();
  const [expandedCompanyKey, setExpandedCompanyKey] = useState<string | null>(null);
  const [assetsExpanded, setAssetsExpanded] = useState(false);
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
      is_default: boolean;
    }) =>
      api.createOfficialAccount({
        company_key: payload.company_key,
        display_name: payload.display_name,
        is_default: payload.is_default,
        status: "active",
        username: "",
        password: null,
      }),
    onSuccess: (_, payload) => {
      setAccountDrafts((current) => ({
        ...current,
        [payload.company_key]: createEmptyDraft(),
      }));
      refreshPoolQueries();
    },
  });

  const deleteAccountMutation = useMutation({
    mutationFn: (accountId: string) => api.deleteOfficialAccount(accountId),
    onSuccess: refreshPoolQueries,
  });

  const loginMutation = useMutation({
    mutationFn: (accountId: string) => api.loginOfficialAccount(accountId),
    onSuccess: refreshPoolQueries,
  });
  const sessionTestMutation = useMutation({
    mutationFn: (accountId: string) => api.testOfficialAccountSession(accountId),
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
      const bucket = grouped.get(account.company_key) || [];
      bucket.push(account);
      grouped.set(account.company_key, bucket);
    }
    return grouped;
  }, [accountsQuery.data]);

  const defaultAccountsByCompany = useMemo(() => {
    const grouped = new Map<string, OfficialAccount | undefined>();
    for (const [companyKey, accounts] of accountsByCompany.entries()) {
      grouped.set(
        companyKey,
        accounts.find((account) => account.is_default) || accounts[0],
      );
    }
    return grouped;
  }, [accountsByCompany]);

  const bindingsByCompany = useMemo(() => {
    const grouped = new Map<string, string | null>();
    for (const binding of bindingsQuery.data || []) {
      grouped.set(binding.company_key, binding.default_resume_asset_id || null);
    }
    return grouped;
  }, [bindingsQuery.data]);

  const configuredCompanies = Array.from(defaultAccountsByCompany.values()).filter(Boolean).length;
  const loggedInCompanies = Array.from(defaultAccountsByCompany.values()).filter(
    (account) => account?.is_logged_in,
  ).length;
  const boundCompanyCount = (bindingsQuery.data || []).filter(
    (binding) => binding.default_resume_asset_id,
  ).length;

  const globalError =
    (sitesQuery.error instanceof Error && sitesQuery.error.message) ||
    (accountsQuery.error instanceof Error && accountsQuery.error.message) ||
    (assetsQuery.error instanceof Error && assetsQuery.error.message) ||
    (bindingsQuery.error instanceof Error && bindingsQuery.error.message) ||
    (createAccountMutation.error instanceof Error && createAccountMutation.error.message) ||
    (deleteAccountMutation.error instanceof Error && deleteAccountMutation.error.message) ||
    (loginMutation.error instanceof Error && loginMutation.error.message) ||
    (sessionTestMutation.error instanceof Error && sessionTestMutation.error.message) ||
    (uploadAssetMutation.error instanceof Error && uploadAssetMutation.error.message) ||
    (deleteAssetMutation.error instanceof Error && deleteAssetMutation.error.message) ||
    (updateBindingMutation.error instanceof Error && updateBindingMutation.error.message) ||
    null;

  const secondaryActionButtonClass =
    "inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-3.5 py-1.5 text-xs font-semibold text-ink transition hover:bg-shell disabled:cursor-not-allowed disabled:opacity-50";
  const primaryActionButtonClass =
    "inline-flex items-center gap-2 rounded-full bg-ink px-3.5 py-1.5 text-xs font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-50";
  const compactActionButtonClass =
    "inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-3 py-1.5 text-xs font-semibold text-ink transition hover:bg-shell disabled:opacity-50";

  const ensureDefaultAccount = async (site: OfficialSite) => {
    const existingAccount = defaultAccountsByCompany.get(site.company_key);
    if (existingAccount) {
      return existingAccount;
    }

    return createAccountMutation.mutateAsync({
      company_key: site.company_key,
      display_name: `${site.company_name} 账号`,
      is_default: true,
    });
  };

  return (
    <div className="space-y-4">
      <section className="rounded-[30px] border border-ink/10 bg-shell/90 p-5 shadow-console">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-xs uppercase tracking-[0.24em] text-slate">账号与简历池</p>
            <h1 className="mt-2 font-display text-3xl text-ink md:text-4xl">
              手动登录官网，缓存会话，再复用到批量投递
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate">
              这里不再保存邮箱密码登录链路。每家公司只保留一个紧凑摘要，点击“登录”会打开对应平台官网，
              你手动完成登录后，系统只缓存会话并在投递前做有效性检查。
            </p>
          </div>

          <div className="grid min-w-[260px] gap-3 sm:grid-cols-3">
            <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate">已配置公司</p>
              <p className="mt-2 font-display text-3xl text-ink">{configuredCompanies}</p>
            </div>
            <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate">已登录</p>
              <p className="mt-2 font-display text-3xl text-ink">{loggedInCompanies}</p>
            </div>
            <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate">已绑默认简历</p>
              <p className="mt-2 font-display text-3xl text-ink">{boundCompanyCount}</p>
            </div>
          </div>
        </div>
      </section>

      {globalError ? (
        <section className="rounded-[24px] border border-ember/30 bg-ember/10 px-4 py-3 text-sm text-ember">
          {globalError}
        </section>
      ) : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {sitesQuery.data?.map((site) => {
          const accounts = accountsByCompany.get(site.company_key) || [];
          const defaultAccount = defaultAccountsByCompany.get(site.company_key);
          const bindingId = bindingsByCompany.get(site.company_key) || "";
          const expanded = expandedCompanyKey === site.company_key;
          const draft = accountDrafts[site.company_key] || createEmptyDraft();
          const isProvisioningDefaultAccount =
            createAccountMutation.isPending &&
            createAccountMutation.variables?.company_key === site.company_key;
          const isLoginPending = loginMutation.isPending && loginMutation.variables === defaultAccount?.id;
          const isSessionTestPending =
            sessionTestMutation.isPending &&
            sessionTestMutation.variables === defaultAccount?.id;

          return (
            <article
              key={site.company_key}
              className={cn(
                "rounded-[28px] border border-ink/10 bg-shell/90 p-4 shadow-console",
                expanded ? "md:col-span-2 xl:col-span-4" : "",
              )}
            >
              <div className="flex h-full flex-col gap-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="font-display text-2xl text-ink">{site.company_name}</h2>
                    <span
                      className={cn(
                        "rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]",
                        loginTone(Boolean(defaultAccount?.is_logged_in)),
                      )}
                    >
                      {defaultAccount?.is_logged_in ? "已登录" : "未登录"}
                    </span>
                    <span className="rounded-full border border-ink/10 bg-paper px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate">
                      {site.source_sites.join(" / ")}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={secondaryActionButtonClass}
                      disabled={isProvisioningDefaultAccount || isLoginPending || isSessionTestPending}
                      onClick={() => {
                        void (async () => {
                          const account = await ensureDefaultAccount(site);
                          loginMutation.mutate(account.id);
                        })();
                      }}
                    >
                      {isProvisioningDefaultAccount || isLoginPending ? (
                        <LoaderCircle size={15} className="animate-spin" />
                      ) : (
                        <LogIn size={15} />
                      )}
                      登录
                    </button>

                    <button
                      type="button"
                      className={secondaryActionButtonClass}
                      disabled={isProvisioningDefaultAccount || isLoginPending || isSessionTestPending}
                      onClick={() => {
                        void (async () => {
                          const account = await ensureDefaultAccount(site);
                          sessionTestMutation.mutate(account.id);
                        })();
                      }}
                    >
                      {isSessionTestPending ? (
                        <LoaderCircle size={15} className="animate-spin" />
                      ) : (
                        <Vault size={15} />
                      )}
                      检测缓存
                    </button>

                    <button
                      type="button"
                      className={primaryActionButtonClass}
                      onClick={() =>
                        setExpandedCompanyKey((current) =>
                          current === site.company_key ? null : site.company_key,
                        )
                      }
                    >
                      {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                      {expanded ? "收起" : "展开"}
                    </button>
                  </div>
                </div>

                {expanded ? (
                <div className="mt-4 grid gap-4">
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <div
                      className={cn(
                        "rounded-[22px] border px-4 py-3",
                        loginTone(Boolean(defaultAccount?.is_logged_in)),
                      )}
                    >
                      <p className="text-[11px] uppercase tracking-[0.18em]">登录状态</p>
                      <p className="mt-2 text-sm font-semibold">
                        {defaultAccount?.is_logged_in ? "已登录" : "未登录"}
                      </p>
                    </div>

                    <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate">最近测试结果</p>
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-ink">
                        {defaultAccount?.last_test_message || "尚未测试"}
                      </p>
                    </div>

                    <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate">最近测试时间</p>
                      <p className="mt-2 text-sm font-semibold text-ink">
                        {formatDate(defaultAccount?.last_tested_at)}
                      </p>
                    </div>

                    <div className="rounded-[22px] border border-ink/10 bg-paper px-4 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate">缓存状态</p>
                      <p className="mt-2 text-sm font-semibold text-ink">
                        {cacheStatusLabel(defaultAccount?.session_cache?.status)}
                      </p>
                    </div>
                  </div>

                  <p className="text-[11px] leading-5 text-slate">
                    点击登录后会打开官网页面。请在官网里手动完成登录，并关闭该窗口后再回到这里查看状态。
                  </p>

                  <div className="rounded-[20px] border border-ink/10 bg-paper px-4 py-3 text-xs text-slate">
                    <p className="uppercase tracking-[0.18em]">缓存路径</p>
                    <p className="mt-2 break-all text-ink">
                      {defaultAccount?.session_cache?.storage_state_path || "尚未创建会话缓存"}
                    </p>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                    <section className="rounded-[24px] border border-ink/10 bg-paper p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.2em] text-slate">账号列表</p>
                        <p className="mt-1 text-sm text-slate">
                          这里只管理显示名和缓存状态；登录统一走平台官网。
                        </p>
                      </div>
                      <span className="rounded-full border border-ink/10 bg-shell px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate">
                        {accounts.length} 个账号
                      </span>
                    </div>

                    <div className="mt-4 space-y-3">
                      {accounts.length ? (
                        accounts.map((account) => {
                          const accountLoginPending =
                            loginMutation.isPending && loginMutation.variables === account.id;
                          const accountSessionTestPending =
                            sessionTestMutation.isPending &&
                            sessionTestMutation.variables === account.id;

                          return (
                            <div
                              key={account.id}
                              className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-ink/10 bg-shell px-4 py-3"
                            >
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="truncate text-sm font-semibold text-ink">
                                    {account.display_name}
                                  </p>
                                  <span
                                    className={cn(
                                      "rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.18em]",
                                      loginTone(account.is_logged_in),
                                    )}
                                  >
                                    {account.is_logged_in ? "已登录" : "未登录"}
                                  </span>
                                  <span className="rounded-full border border-ink/10 bg-paper px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-slate">
                                    {cacheStatusLabel(account.session_cache?.status)}
                                  </span>
                                </div>
                                <p className="mt-1 text-xs text-slate">
                                  {account.last_test_message || "暂无测试记录"}
                                </p>
                                <p className="mt-1 break-all text-[11px] text-slate">
                                  {account.session_cache?.storage_state_path || ""}
                                </p>
                              </div>

                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  className={compactActionButtonClass}
                                  disabled={accountLoginPending || accountSessionTestPending}
                                  onClick={() => loginMutation.mutate(account.id)}
                                >
                                  {accountLoginPending ? (
                                    <LoaderCircle size={13} className="animate-spin" />
                                  ) : (
                                    <LogIn size={13} />
                                  )}
                                  登录
                                </button>
                                <button
                                  type="button"
                                  className={compactActionButtonClass}
                                  disabled={accountLoginPending || accountSessionTestPending}
                                  onClick={() => sessionTestMutation.mutate(account.id)}
                                >
                                  {accountSessionTestPending ? (
                                    <LoaderCircle size={13} className="animate-spin" />
                                  ) : (
                                    <Vault size={13} />
                                  )}
                                  检测
                                </button>
                                <button
                                  type="button"
                                  className={compactActionButtonClass}
                                  disabled={deleteAccountMutation.isPending}
                                  onClick={() => deleteAccountMutation.mutate(account.id)}
                                >
                                  <Trash2 size={13} />
                                  删除
                                </button>
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="rounded-[20px] border border-dashed border-ink/15 bg-shell px-4 py-4 text-sm text-slate">
                          还没有给这家公司添加账号。
                        </div>
                      )}
                    </div>

                    <div className="mt-4 rounded-[20px] border border-ink/10 bg-shell px-4 py-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate">新增账号</p>
                      <div className="mt-3 flex flex-col gap-3 md:flex-row">
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
                          className="min-w-0 flex-1 rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                          placeholder={`${site.company_name} 账号`}
                        />
                        <button
                          type="button"
                          className={primaryActionButtonClass}
                          disabled={!draft.display_name.trim() || createAccountMutation.isPending}
                          onClick={() =>
                            createAccountMutation.mutate({
                              company_key: site.company_key,
                              display_name: draft.display_name.trim(),
                              is_default: accounts.length === 0,
                            })
                          }
                        >
                          {createAccountMutation.isPending ? "保存中..." : "添加账号"}
                        </button>
                      </div>
                    </div>
                    </section>

                    <section className="rounded-[24px] border border-ink/10 bg-paper p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate">默认简历</p>
                    <p className="mt-1 text-sm text-slate">
                      批量投递时会自动套用这份简历，不在这里执行投递动作。
                    </p>

                    <div className="mt-4 rounded-[20px] border border-ink/10 bg-shell px-4 py-4">
                      <label className="space-y-2">
                        <span className="text-xs uppercase tracking-[0.18em] text-slate">
                          绑定到 {site.company_name}
                        </span>
                        <select
                          value={bindingId}
                          onChange={(event) =>
                            updateBindingMutation.mutate({
                              companyKey: site.company_key,
                              defaultResumeAssetId: event.target.value || null,
                            })
                          }
                          className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                        >
                          <option value="">未绑定</option>
                          {assetsQuery.data?.map((asset) => (
                            <option key={asset.id} value={asset.id}>
                              {asset.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      <div className="mt-4 rounded-[18px] border border-dashed border-ink/15 bg-paper px-4 py-4 text-sm text-slate">
                        {bindingId
                          ? `当前默认简历：${
                              assetsQuery.data?.find((asset) => asset.id === bindingId)?.label ||
                              "已绑定"
                            }`
                          : "还没绑定简历。先展开下方简历池上传一份，再给这家公司设置默认简历。"}
                      </div>
                    </div>

                    <div className="mt-4 rounded-[20px] border border-ink/10 bg-shell px-4 py-4">
                      <p className="text-xs uppercase tracking-[0.18em] text-slate">支持来源</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {site.supported_variants.map((variant) => (
                          <span
                            key={variant}
                            className="rounded-full border border-ink/10 bg-paper px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate"
                          >
                            {pillLabel(variant)}
                          </span>
                        ))}
                      </div>
                    </div>
                    </section>
                  </div>
                </div>
                ) : null}
              </div>
            </article>
          );
        })}
      </section>

      <section className="rounded-[28px] border border-ink/10 bg-shell/90 p-4 shadow-console">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 rounded-[22px] border border-ink/10 bg-paper px-4 py-4 text-left"
          onClick={() => setAssetsExpanded((current) => !current)}
        >
          <div className="flex items-center gap-3">
            <Vault size={18} className="text-slate" />
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate">简历池</p>
              <p className="mt-1 text-sm text-ink">
                已收纳 {assetsQuery.data?.length || 0} 份投递资产，默认收起避免页面过大。
              </p>
            </div>
          </div>
          {assetsExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {assetsExpanded ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
            <div className="rounded-[24px] border border-ink/10 bg-paper p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate">上传简历</p>
              <div className="mt-4 space-y-3">
                <input
                  value={assetLabel}
                  onChange={(event) => setAssetLabel(event.target.value)}
                  className="w-full rounded-2xl border border-ink/10 bg-shell px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
                  placeholder="例如：2026 社招主简历"
                />

                <label className="flex min-h-[132px] cursor-pointer flex-col items-center justify-center rounded-[24px] border border-dashed border-ink/20 bg-shell text-center transition hover:border-ink/35 hover:bg-paper">
                  <Upload size={18} className="text-slate" />
                  <p className="mt-4 text-sm font-semibold text-ink">
                    {selectedFile?.name || "选择 PDF / DOCX 简历"}
                  </p>
                  <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate">
                    单击替换文件
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
                  className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!selectedFile || uploadAssetMutation.isPending}
                  onClick={() => {
                    if (!selectedFile) {
                      return;
                    }
                    uploadAssetMutation.mutate({ file: selectedFile, label: assetLabel });
                  }}
                >
                  {uploadAssetMutation.isPending ? (
                    <LoaderCircle size={15} className="animate-spin" />
                  ) : (
                    <Upload size={15} />
                  )}
                  {uploadAssetMutation.isPending ? "上传中..." : "收进简历池"}
                </button>
              </div>
            </div>

            <div className="rounded-[24px] border border-ink/10 bg-paper p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-slate">资产列表</p>
              <div className="mt-4 space-y-3">
                {assetsQuery.data?.length ? (
                  assetsQuery.data.map((asset) => (
                    <div
                      key={asset.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-ink/10 bg-shell px-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-ink">{asset.label}</p>
                        <p className="mt-1 text-xs text-slate">
                          {asset.source_filename} | {(asset.file_size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-3 py-2 text-xs font-semibold text-ink transition hover:bg-shell disabled:opacity-50"
                        disabled={deleteAssetMutation.isPending}
                        onClick={() => deleteAssetMutation.mutate(asset.id)}
                      >
                        <Trash2 size={13} />
                        删除
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[20px] border border-dashed border-ink/15 bg-shell px-4 py-4 text-sm text-slate">
                    暂无投递资产。先上传一份简历，再给各家公司配置默认绑定。
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
