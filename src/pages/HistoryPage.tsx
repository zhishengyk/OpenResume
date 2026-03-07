import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon } from "lucide-react";
import { StatusPill } from "../components/StatusPill";
import { api } from "../lib/api";
import { modeLabel, pillLabel } from "../lib/utils";

export function HistoryPage() {
  const queryClient = useQueryClient();
  const sessionsQuery = useQuery({
    queryKey: ["search-sessions"],
    queryFn: api.listSearchSessions,
  });
  const attemptsQuery = useQuery({
    queryKey: ["attempts"],
    queryFn: api.listAttempts,
  });
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  const emergencyStopMutation = useMutation({
    mutationFn: () =>
      api.setEmergencyStop(!appStateQuery.data?.emergency_stop_active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-state"] });
      queryClient.invalidateQueries({ queryKey: ["risk-status", "boss"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (attemptId: string) => api.cancelAttempt(attemptId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["attempts"] });
    },
  });

  return (
    <div className="space-y-6">
      <section className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-[32px] border border-ember/20 bg-ember/10 p-6 shadow-console">
          <div className="flex items-start gap-3">
            <AlertOctagon className="mt-1 text-ember" size={20} />
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-ember">
                紧急停止
              </p>
              <p className="mt-3 font-display text-4xl italic text-ink">
                立即终止所有引导动作。
              </p>
              <p className="mt-4 text-sm leading-7 text-slate">
                当页面结构异常、出现验证页，或你不希望系统继续推进任何队列中的动作时，请立刻启用急停。
              </p>
              <button
                type="button"
                className="mt-6 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-shell transition hover:bg-ink/90"
                onClick={() => emergencyStopMutation.mutate()}
              >
                {appStateQuery.data?.emergency_stop_active
                  ? "解除紧急停止"
                  : "启用紧急停止"}
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
          <p className="text-xs uppercase tracking-[0.24em] text-slate">
            搜索历史
          </p>
          <div className="mt-5 space-y-3">
            {sessionsQuery.data?.map((session) => (
              <div
                key={session.id}
                className="rounded-[24px] border border-ink/10 bg-paper px-4 py-4"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold text-ink">
                      {session.job_targets.join(" / ")}
                    </p>
                    <p className="mt-1 text-sm text-slate">
                      {pillLabel(session.platform)} · {modeLabel(session.mode)} ·{" "}
                      {new Date(session.created_at).toLocaleString()}
                    </p>
                  </div>
                  <StatusPill>{session.status}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <p className="text-xs uppercase tracking-[0.24em] text-slate">
          引导动作记录
        </p>
        <div className="mt-5 space-y-3">
          {attemptsQuery.data?.map((attempt) => (
            <div
              key={attempt.id}
              className="flex flex-wrap items-center justify-between gap-4 rounded-[24px] border border-ink/10 bg-paper px-4 py-4"
            >
              <div>
                <p className="font-semibold text-ink">{attempt.job_id}</p>
                <p className="mt-1 text-sm text-slate">
                  {pillLabel(attempt.platform)} · {modeLabel(attempt.mode)} ·{" "}
                  {new Date(attempt.created_at).toLocaleString()}
                </p>
                <p className="mt-2 text-sm leading-7 text-slate">
                  {attempt.message}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <StatusPill>{attempt.status}</StatusPill>
                <button
                  type="button"
                  className="rounded-full border border-ink/10 px-4 py-2 text-sm font-semibold text-ink transition hover:bg-shell"
                  onClick={() => cancelMutation.mutate(attempt.id)}
                  disabled={cancelMutation.isPending}
                >
                  取消
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
