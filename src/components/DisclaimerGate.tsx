import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { api } from "../lib/api";

export function DisclaimerGate() {
  const queryClient = useQueryClient();
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  const acceptMutation = useMutation({
    mutationFn: api.acceptDisclaimer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-state"] });
    },
  });

  if (!appStateQuery.data?.launch_disclaimer_required) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/50 px-6 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-[36px] border border-ember/20 bg-shell p-8 shadow-console">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl bg-ember/10 p-3 text-ember">
            <ShieldAlert size={28} />
          </div>
          <div className="flex-1">
            <p className="text-xs uppercase tracking-[0.24em] text-ember">
              {"\u5fc5\u8bfb\u544a\u77e5"}
            </p>
            <h2 className="mt-2 font-display text-4xl text-ink">
              {"\u4ec5\u652f\u6301\u7528\u6237\u4e3b\u5bfc\u7684\u81ea\u52a8\u5316"}
            </h2>
            <div className="mt-5 space-y-4 text-sm leading-7 text-slate">
              <p>
                {
                  "\u672c\u5e94\u7528\u662f\u4e00\u4e2a\u672c\u5730\u8fd0\u884c\u7684\u804c\u4f4d\u7814\u7a76\u4e0e\u5f15\u5bfc\u64cd\u4f5c\u5de5\u5177\u3002\u5b83\u4e0d\u4f1a\u81ea\u52a8\u63d0\u4ea4\u7b80\u5386\uff0c\u4e5f\u4e0d\u5e94\u88ab\u7528\u4e8e\u7ed5\u8fc7\u5e73\u53f0\u89c4\u5219\u3001\u9891\u7387\u9650\u5236\u6216\u9a8c\u8bc1\u6d41\u7a0b\u3002"
                }
              </p>
              <p>
                {
                  "\u5982\u679c\u5e73\u53f0\u68c0\u6d4b\u5230\u81ea\u52a8\u5316\u7279\u5f81\uff0c\u8d26\u53f7\u53ef\u80fd\u88ab\u9650\u5236\u751a\u81f3\u5c01\u7981\u3002\u4f7f\u7528\u672c\u5de5\u5177\u5e26\u6765\u7684\u8d26\u53f7\u3001\u6570\u636e\u548c\u6cd5\u5f8b\u98ce\u9669\uff0c\u9700\u8981\u7531\u4f60\u81ea\u884c\u627f\u62c5\u3002"
                }
              </p>
              <div className="rounded-3xl border border-ink/10 bg-paper p-4">
                <div className="flex items-center gap-3 text-ink">
                  <AlertTriangle size={16} />
                  <p className="font-semibold">
                    {
                      "\u4e25\u7981\u4f7f\u7528\u5f53\u524d\u7248\u672c\u8fdb\u884c\u81ea\u52a8\u63d0\u4ea4\u3001\u9a8c\u8bc1\u7801\u7ed5\u8fc7\u6216\u4efb\u4f55\u53cd\u68c0\u6d4b\u5bf9\u6297\u884c\u4e3a\u3002"
                    }
                  </p>
                </div>
              </div>
            </div>
            <button
              type="button"
              className="mt-6 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
              onClick={() => acceptMutation.mutate()}
              disabled={acceptMutation.isPending}
            >
              {acceptMutation.isPending
                ? "\u6b63\u5728\u4fdd\u5b58\u786e\u8ba4..."
                : "\u6211\u5df2\u4e86\u89e3\u5e76\u63a5\u53d7\u98ce\u9669\u63d0\u793a"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

