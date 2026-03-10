import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, KeyRound, ListRestart, Save, Search, Wifi, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { cn } from "../lib/utils";
import type { RuntimeConfig } from "../types";

interface ModelConfigPanelProps {
  runtimeConfig: RuntimeConfig;
}

interface DraftState {
  llm_provider: string;
  openai_base_url: string;
  openai_model: string;
  openai_api_key: string;
}

interface ModelPickerDialogProps {
  models: string[];
  filter: string;
  open: boolean;
  selectedModel: string;
  onClose: () => void;
  onConfirm: () => void;
  onFilterChange: (value: string) => void;
  onSelect: (model: string) => void;
}

function normalizeValue(value?: string | null) {
  return value || "";
}

function extractError(error: unknown) {
  return error instanceof Error ? error.message : "操作失败";
}

function ModelPickerDialog({
  models,
  filter,
  open,
  selectedModel,
  onClose,
  onConfirm,
  onFilterChange,
  onSelect,
}: ModelPickerDialogProps) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const normalizedFilter = filter.trim().toLowerCase();
  const filteredModels = normalizedFilter
    ? models.filter((model) => model.toLowerCase().includes(normalizedFilter))
    : models;

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-ink/45 px-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-[32px] border border-ink/10 bg-shell p-6 shadow-console"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="模型列表"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-slate">模型列表</p>
            <h3 className="mt-2 font-display text-3xl text-ink">选择排序模型</h3>
            <p className="mt-3 text-sm leading-7 text-slate">
              已加载 {models.length} 个模型。可以筛选后再选择。
            </p>
          </div>
          <button
            type="button"
            className="rounded-full border border-ink/10 bg-paper p-2 text-ink transition hover:bg-shell"
            onClick={onClose}
            aria-label="关闭模型列表"
          >
            <X size={16} />
          </button>
        </div>

        <label className="mt-5 block space-y-2">
          <span className="text-xs uppercase tracking-[0.2em] text-slate">筛选</span>
          <div className="flex items-center gap-3 rounded-2xl border border-ink/10 bg-paper px-4 py-3">
            <Search size={16} className="text-slate" />
            <input
              value={filter}
              onChange={(event) => onFilterChange(event.target.value)}
              placeholder="搜索模型名，例如 qwen、gpt 或 deepseek"
              className="w-full bg-transparent text-sm text-ink outline-none"
            />
          </div>
        </label>

        <div className="mt-5 rounded-[28px] border border-ink/10 bg-paper p-3">
          <div className="max-h-[24rem] space-y-2 overflow-y-auto pr-2">
            {filteredModels.length ? (
              filteredModels.map((model) => {
                const checked = model === selectedModel;
                return (
                  <button
                    key={model}
                    type="button"
                    className={cn(
                      "flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition",
                      checked
                        ? "border-ink bg-ink text-shell"
                        : "border-ink/10 bg-shell text-ink hover:border-ink/30 hover:bg-paper",
                    )}
                    onClick={() => onSelect(model)}
                  >
                    <p className="truncate text-sm font-semibold">{model}</p>
                    <span
                      className={cn(
                        "ml-4 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                        checked
                          ? "border-shell/70 bg-shell/15 text-shell"
                          : "border-ink/15 bg-paper text-transparent",
                      )}
                    >
                      <Bot size={12} />
                    </span>
                  </button>
                );
              })
            ) : (
              <div className="rounded-2xl border border-dashed border-ink/15 bg-shell px-4 py-8 text-center text-sm leading-7 text-slate">
                当前筛选条件下没有匹配的模型。
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate">
            已选择：{selectedModel || "尚未选择模型"}
          </p>
          <div className="flex flex-wrap gap-3">
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
              onClick={onConfirm}
              disabled={!selectedModel}
            >
              使用所选模型
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ModelConfigPanel({ runtimeConfig }: ModelConfigPanelProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<DraftState>({
    llm_provider: runtimeConfig.llm_provider,
    openai_base_url: normalizeValue(runtimeConfig.openai_base_url),
    openai_model: normalizeValue(runtimeConfig.openai_model),
    openai_api_key: "",
  });
  const [clearSavedApiKey, setClearSavedApiKey] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [testSummary, setTestSummary] = useState<string | null>(null);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelFilter, setModelFilter] = useState("");
  const [pickerSelection, setPickerSelection] = useState("");

  useEffect(() => {
    setDraft({
      llm_provider: runtimeConfig.llm_provider,
      openai_base_url: normalizeValue(runtimeConfig.openai_base_url),
      openai_model: normalizeValue(runtimeConfig.openai_model),
      openai_api_key: "",
    });
    setClearSavedApiKey(false);
  }, [runtimeConfig]);

  useEffect(() => {
    if (draft.llm_provider !== "openai_compatible") {
      setModelPickerOpen(false);
    }
  }, [draft.llm_provider]);

  const openModelPicker = () => {
    if (!availableModels.length) {
      return;
    }
    setPickerSelection(
      availableModels.includes(draft.openai_model)
        ? draft.openai_model
        : availableModels[0],
    );
    setModelFilter("");
    setModelPickerOpen(true);
  };

  const applySelectedModel = () => {
    if (!pickerSelection) {
      return;
    }
    setDraft((current) => ({ ...current, openai_model: pickerSelection }));
    setTestSummary(`已选择模型：${pickerSelection}`);
    setModelPickerOpen(false);
  };

  const buildProbePayload = () => ({
    llm_provider: draft.llm_provider,
    openai_base_url: draft.openai_base_url.trim() || null,
    openai_model: draft.openai_model.trim() || null,
    openai_api_key: draft.openai_api_key.trim() || null,
    use_saved_api_key: !clearSavedApiKey && !draft.openai_api_key.trim(),
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateRuntimeConfig({
        llm_provider: draft.llm_provider,
        openai_base_url: draft.openai_base_url.trim() || null,
        openai_model: draft.openai_model.trim() || null,
        openai_api_key: draft.openai_api_key.trim() || null,
        replace_api_key: clearSavedApiKey || Boolean(draft.openai_api_key.trim()),
      }),
    onSuccess: () => {
      setTestSummary("模型配置已保存。");
      setDraft((current) => ({ ...current, openai_api_key: "" }));
      setClearSavedApiKey(false);
      queryClient.invalidateQueries({ queryKey: ["runtime-config"] });
    },
  });

  const fetchModelsMutation = useMutation({
    mutationFn: () => api.listRuntimeModels(buildProbePayload()),
    onSuccess: (result) => {
      setAvailableModels(result.models);
      setPickerSelection(
        result.models.includes(draft.openai_model)
          ? draft.openai_model
          : (result.models[0] ?? ""),
      );
      setModelFilter("");
      setModelPickerOpen(result.models.length > 0);
      setTestSummary(
        result.models.length > 0
          ? `${result.message} 已打开模型列表。`
          : result.message,
      );
    },
  });

  const testMutation = useMutation({
    mutationFn: () => api.testRuntimeLLM(buildProbePayload()),
    onSuccess: (result) => {
      const latencyText =
        typeof result.latency_ms === "number" ? `，耗时 ${result.latency_ms} ms` : "";
      const previewText = result.reply_preview
        ? `，返回预览：${result.reply_preview}`
        : "";
      setTestSummary(`${result.message}${latencyText}${previewText}`);
    },
  });

  const actionError = saveMutation.error || fetchModelsMutation.error || testMutation.error;
  const openAIFieldsDisabled = draft.llm_provider !== "openai_compatible";

  return (
    <>
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate">模型配置</p>
            <h2 className="mt-3 font-display text-4xl text-ink">
              在界面里配置排序模型，并直接测试连通性。
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
              保存后的值会写入本地运行时配置。原始 API Key 不会回传到前端。
              当前官网来源：{runtimeConfig.official_sources_summary}。
            </p>
          </div>
          <div className="rounded-[24px] border border-ink/10 bg-paper px-5 py-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate">当前状态</p>
            <p className="mt-2 font-semibold text-ink">{runtimeConfig.llm_notice}</p>
            <p className="mt-2 text-sm text-slate">
              生效提供方：{runtimeConfig.llm_effective_provider}
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate">提供方</span>
            <select
              value={draft.llm_provider}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  llm_provider: event.target.value,
                }))
              }
              className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30"
            >
              <option value="heuristic">启发式</option>
              <option value="openai_compatible">OpenAI 兼容</option>
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate">接口地址</span>
            <input
              value={draft.openai_base_url}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  openai_base_url: event.target.value,
                }))
              }
              disabled={openAIFieldsDisabled}
              placeholder="https://your-model-endpoint/v1"
              className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30 disabled:cursor-not-allowed disabled:bg-paper/70"
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate">模型名</span>
            <input
              value={draft.openai_model}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  openai_model: event.target.value,
                }))
              }
              disabled={openAIFieldsDisabled}
              placeholder="gpt-4.1-mini"
              className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30 disabled:cursor-not-allowed disabled:bg-paper/70"
            />
            <div className="flex items-center justify-between gap-3 text-xs text-slate">
              <span>
                {availableModels.length
                  ? `已加载 ${availableModels.length} 个模型。`
                  : "也可以手动直接输入模型名。"}
              </span>
              <button
                type="button"
                className="font-semibold text-ink transition hover:text-ink/70 disabled:cursor-not-allowed disabled:text-slate/60"
                onClick={openModelPicker}
                disabled={!availableModels.length || openAIFieldsDisabled}
              >
                打开模型列表
              </button>
            </div>
          </label>

          <label className="space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate">API Key</span>
            <input
              type="password"
              value={draft.openai_api_key}
              onChange={(event) => {
                setDraft((current) => ({
                  ...current,
                  openai_api_key: event.target.value,
                }));
                if (event.target.value) {
                  setClearSavedApiKey(false);
                }
              }}
              disabled={openAIFieldsDisabled}
              placeholder={
                runtimeConfig.openai_api_key_configured
                  ? "留空则继续使用已保存的 Key"
                  : "输入新的 API Key"
              }
              className="w-full rounded-2xl border border-ink/10 bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-ink/30 disabled:cursor-not-allowed disabled:bg-paper/70"
            />
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate">
          <div className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2">
            <KeyRound size={14} />
            {runtimeConfig.openai_api_key_configured
              ? `已保存 Key：${runtimeConfig.openai_api_key_preview}`
              : "尚未保存 Key"}
          </div>
          <label className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-paper px-4 py-2 text-ink">
            <input
              type="checkbox"
              checked={clearSavedApiKey}
              onChange={(event) => setClearSavedApiKey(event.target.checked)}
              disabled={!runtimeConfig.openai_api_key_configured || openAIFieldsDisabled}
            />
            清除已保存 Key
          </label>
          <span>官网来源：{runtimeConfig.official_sources_summary}</span>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:bg-ink/40"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            <Save size={16} />
            {saveMutation.isPending ? "保存中..." : "保存配置"}
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => fetchModelsMutation.mutate()}
            disabled={fetchModelsMutation.isPending || openAIFieldsDisabled}
          >
            <ListRestart size={16} />
            {fetchModelsMutation.isPending ? "加载模型中..." : "拉取模型列表"}
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-shell px-5 py-3 text-sm font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending || openAIFieldsDisabled}
          >
            <Wifi size={16} />
            {testMutation.isPending ? "测试中..." : "测试连接"}
          </button>
        </div>

        {testSummary ? (
          <div className="mt-5 rounded-[24px] border border-mint/30 bg-mint/10 px-4 py-3 text-sm leading-7 text-ink">
            {testSummary}
          </div>
        ) : null}

        {actionError ? (
          <div className="mt-5 rounded-[24px] border border-ember/30 bg-ember/10 px-4 py-3 text-sm leading-7 text-ink">
            {extractError(actionError)}
          </div>
        ) : null}
      </section>

      <ModelPickerDialog
        models={availableModels}
        filter={modelFilter}
        open={modelPickerOpen}
        selectedModel={pickerSelection}
        onClose={() => setModelPickerOpen(false)}
        onConfirm={applySelectedModel}
        onFilterChange={setModelFilter}
        onSelect={setPickerSelection}
      />
    </>
  );
}
