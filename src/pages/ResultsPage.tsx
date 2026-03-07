import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { MetricCard } from "../components/MetricCard";
import { StatusPill } from "../components/StatusPill";
import { Timeline } from "../components/Timeline";
import { useEventStream } from "../hooks/useEventStream";
import { api } from "../lib/api";
import type { SearchEvent } from "../types";

export function ResultsPage() {
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<SearchEvent[]>([]);
  const sessionId = params.get("session") || undefined;

  const sessionQuery = useQuery({
    queryKey: ["search-session", sessionId],
    queryFn: () => api.getSearchSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: sessionId ? 2000 : false,
  });

  const matchesQuery = useQuery({
    queryKey: ["search-matches", sessionId],
    queryFn: () => api.getSearchMatches(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: sessionId ? 2500 : false,
  });

  useEventStream(sessionId, (event) => {
    setEvents((current) => {
      if (current.some((item) => item.type === event.type && item.timestamp === event.timestamp)) {
        return current;
      }

      return [...current, event];
    });
    queryClient.invalidateQueries({ queryKey: ["search-session", sessionId] });
    queryClient.invalidateQueries({ queryKey: ["search-matches", sessionId] });
  });

  const topMatch = matchesQuery.data?.[0];

  return (
    <div className="space-y-6">
      <section className="rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate">
              Search session
            </p>
            <h1 className="mt-3 font-display text-5xl italic text-ink">
              Observe the pipeline before you touch the platform.
            </h1>
          </div>
          {sessionQuery.data ? (
            <StatusPill>{sessionQuery.data.status}</StatusPill>
          ) : null}
        </div>
        {sessionQuery.data?.summary ? (
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate">
            {sessionQuery.data.summary}
          </p>
        ) : null}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <MetricCard
          label="Matches visible"
          value={String(matchesQuery.data?.length ?? 0)}
          hint="Cards appear from rule ranking first, then gain richer LLM commentary."
        />
        <MetricCard
          label="Current platform"
          value={sessionQuery.data?.platform.toUpperCase() || "--"}
          hint="Platform adapters stay capability-scoped, not fully privileged."
        />
        <MetricCard
          label="Top score"
          value={topMatch ? String(Math.round(topMatch.final_score)) : "--"}
          hint="Combined rule and LLM score after conservative hard filtering."
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Timeline events={events} />
        <div className="space-y-5">
          {matchesQuery.data?.length ? (
            matchesQuery.data.map((match) => <MatchCard key={match.id} match={match} />)
          ) : (
            <div className="rounded-[32px] border border-ink/10 bg-shell/90 p-8 text-sm leading-7 text-slate shadow-console">
              Search output will land here after the first pipeline stage publishes
              matches. Rule-ranked cards appear before LLM commentary is attached.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

