import { useQuery } from "@tanstack/react-query";
import { ConfigurationGuide } from "../components/ConfigurationGuide";
import { ModelConfigPanel } from "../components/ModelConfigPanel";
import { api, apiBaseUrl } from "../lib/api";

export function ModelConfigPage() {
  const runtimeConfigQuery = useQuery({
    queryKey: ["runtime-config"],
    queryFn: api.getRuntimeConfig,
  });

  if (!runtimeConfigQuery.data) {
    return (
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 text-sm leading-7 text-slate shadow-console">
        正在读取模型配置...
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <ConfigurationGuide
        apiBaseUrl={apiBaseUrl}
        runtimeConfig={runtimeConfigQuery.data}
        onRetry={() => {
          void runtimeConfigQuery.refetch();
        }}
      />
      <ModelConfigPanel runtimeConfig={runtimeConfigQuery.data} />
    </div>
  );
}
