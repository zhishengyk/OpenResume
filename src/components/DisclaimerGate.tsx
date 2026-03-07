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
              Mandatory disclosure
            </p>
            <h2 className="mt-2 font-display text-4xl italic text-ink">
              User-controlled automation only
            </h2>
            <div className="mt-5 space-y-4 text-sm leading-7 text-slate">
              <p>
                This application is a local research and guided-action tool. It
                does not auto-submit applications and should not be used to
                bypass platform rules, rate limits, or verification flows.
              </p>
              <p>
                Platform providers may suspend or ban accounts that exhibit
                automation-like behavior. You are responsible for the account,
                data, and legal risk of using any guided workflow.
              </p>
              <div className="rounded-3xl border border-ink/10 bg-paper p-4">
                <div className="flex items-center gap-3 text-ink">
                  <AlertTriangle size={16} />
                  <p className="font-semibold">
                    Never use this build to auto-submit, evade captcha, or
                    imitate anti-detection tooling.
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
              {acceptMutation.isPending ? "Saving acknowledgement..." : "I understand the risk"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

