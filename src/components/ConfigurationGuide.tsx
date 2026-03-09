import { Bot, RefreshCw, Server, TerminalSquare } from "lucide-react";
import type { RuntimeConfig } from "../types";

interface ConfigurationGuideProps {
  apiBaseUrl: string;
  apiUnavailableMessage?: string;
  runtimeConfig?: RuntimeConfig;
  onRetry?: () => void;
}

const desktopStartCommand = [
  "cd C:\\Users\\admin\\Desktop\\openresume",
  "npm run dev",
].join("\n");

const backendOnlyCommand = [
  "cd C:\\Users\\admin\\Desktop\\openresume\\backend",
  "python -m openresume_api",
].join("\n");

const modelConfigExample = [
  '$env:OPENRESUME_LLM_PROVIDER="openai_compatible"',
  '$env:OPENRESUME_OPENAI_BASE_URL="https://your-model-endpoint/v1"',
  '$env:OPENRESUME_OPENAI_API_KEY="your-api-key"',
  '$env:OPENRESUME_OPENAI_MODEL="your-model-name"',
  "npm run dev",
].join("\n");

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="mt-3 overflow-x-auto rounded-[24px] border border-ink/10 bg-paper p-4 text-sm leading-7 text-ink">
      <code>{children}</code>
    </pre>
  );
}

export function ConfigurationGuide({
  apiBaseUrl,
  apiUnavailableMessage,
  runtimeConfig,
  onRetry,
}: ConfigurationGuideProps) {
  const runningInDesktopShell = Boolean(window.openResumeDesktop);
  const healthUrl = `${apiBaseUrl}/health`;
  const shouldShowModelGuide =
    runtimeConfig && runtimeConfig.llm_effective_provider === "heuristic";

  if (!apiUnavailableMessage && !runtimeConfig) {
    return null;
  }

  return (
    <div className="space-y-6">
      {apiUnavailableMessage ? (
        <section className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-shell p-3 text-ember">
              <Server size={24} />
            </div>
            <div className="flex-1">
              <p className="text-xs uppercase tracking-[0.24em] text-ember">
                本地接口未连接
              </p>
              <h2 className="mt-2 font-display text-4xl text-ink">
                先把桌面应用或后端接口启动起来，再刷新前端。
              </h2>
              <p className="mt-4 text-sm leading-7 text-slate">
                当前前端无法访问 <span className="font-semibold text-ink">{apiBaseUrl}</span>，
                所以页面里的资料、平台和搜索接口都不会返回数据。
              </p>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <div className="rounded-[24px] border border-ink/10 bg-shell/80 p-4">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <TerminalSquare size={16} />
                    启动整套桌面应用
                  </p>
                  <CodeBlock>{desktopStartCommand}</CodeBlock>
                </div>
                <div className="rounded-[24px] border border-ink/10 bg-shell/80 p-4">
                  <p className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <TerminalSquare size={16} />
                    只启动后端接口
                  </p>
                  <CodeBlock>{backendOnlyCommand}</CodeBlock>
                </div>
              </div>

              <div className="mt-5 rounded-[24px] border border-ink/10 bg-shell/80 p-4 text-sm leading-7 text-slate">
                <p>
                  健康检查地址：
                  <span className="font-semibold text-ink"> {healthUrl}</span>
                </p>
                <p className="mt-2">
                  能看到 <span className="font-semibold text-ink">{"{\"status\":\"ok\"}"}</span>
                  就说明后端已经起来了。
                </p>
                {!runningInDesktopShell ? (
                  <p className="mt-2">
                    你当前看起来是在普通浏览器里打开前端。开发模式建议直接运行
                    <span className="font-semibold text-ink"> npm run dev</span>，
                    这样 Electron、前端和本地后端会一起拉起。
                  </p>
                ) : null}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
                  onClick={onRetry}
                >
                  <RefreshCw size={16} />
                  重新检测
                </button>
              </div>

              <p className="mt-4 rounded-[24px] border border-ember/20 bg-paper px-4 py-3 text-sm leading-7 text-ink">
                原始错误：{apiUnavailableMessage}
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {shouldShowModelGuide ? (
        <section className="rounded-[32px] border border-amber-500/30 bg-amber-500/10 p-6 shadow-console">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-shell p-3 text-amber-700">
              <Bot size={24} />
            </div>
            <div className="flex-1">
              <p className="text-xs uppercase tracking-[0.24em] text-amber-700">
                模型配置引导
              </p>
              <h2 className="mt-2 font-display text-4xl text-ink">
                当前还没有用上真实大模型，岗位会先走规则降级。
              </h2>
              <p className="mt-4 text-sm leading-7 text-slate">
                {runtimeConfig?.llm_notice}
              </p>
              <p className="mt-2 text-sm leading-7 text-slate">
                你可以直接在下方“模型配置”里保存、拉取模型列表并测试连接；如果仍然偏好环境变量方式，也可以继续用命令行配置。
              </p>

              {runtimeConfig?.llm_missing_envs.length ? (
                <p className="mt-4 text-sm leading-7 text-slate">
                  缺少配置项：
                  <span className="font-semibold text-ink">
                    {" "}{runtimeConfig.llm_missing_envs.join("、")}
                  </span>
                </p>
              ) : null}

              <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="rounded-[24px] border border-ink/10 bg-shell/80 p-4">
                  <p className="text-sm font-semibold text-ink">
                    PowerShell 示例
                  </p>
                  <CodeBlock>{modelConfigExample}</CodeBlock>
                </div>
                <div className="rounded-[24px] border border-ink/10 bg-shell/80 p-4 text-sm leading-7 text-slate">
                  <p>
                    当前请求配置：
                    <span className="font-semibold text-ink"> {runtimeConfig?.llm_provider}</span>
                  </p>
                  <p className="mt-2">
                    当前生效排序：
                    <span className="font-semibold text-ink">
                      {" "}{runtimeConfig?.llm_effective_provider}
                    </span>
                  </p>
                  <p className="mt-2">
                    官网源文件：
                    <span className="font-semibold text-ink">
                      {" "}{runtimeConfig?.official_source_file}
                    </span>
                  </p>
                  {runtimeConfig?.openai_base_url ? (
                    <p className="mt-2">
                      当前模型地址：
                      <span className="font-semibold text-ink">
                        {" "}{runtimeConfig.openai_base_url}
                      </span>
                    </p>
                  ) : null}
                  {runtimeConfig?.openai_model ? (
                    <p className="mt-2">
                      当前模型名：
                      <span className="font-semibold text-ink">
                        {" "}{runtimeConfig.openai_model}
                      </span>
                    </p>
                  ) : null}
                  <p className="mt-2">
                    如果你改的是环境变量，需要重新启动应用；如果你改的是下方表单，保存后会立即写入本地运行时配置。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {runtimeConfig && runtimeConfig.llm_effective_provider !== "heuristic" ? (
        <section className="rounded-[32px] border border-mint/30 bg-mint/10 p-6 shadow-console">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl bg-shell p-3 text-ink">
              <Bot size={24} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-slate">
                模型状态
              </p>
              <h2 className="mt-2 font-display text-4xl text-ink">
                大模型排序已启用
              </h2>
              <p className="mt-4 text-sm leading-7 text-slate">
                当前模型：{runtimeConfig.openai_model || "未命名"}，接口地址：
                {runtimeConfig.openai_base_url || "未显示"}。官网源文件使用
                {runtimeConfig.official_source_file}。
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
