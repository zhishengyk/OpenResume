import { useQuery } from "@tanstack/react-query";
import { Route, Routes } from "react-router-dom";
import { DisclaimerGate } from "./components/DisclaimerGate";
import { Sidebar } from "./components/Sidebar";
import { StatusPill } from "./components/StatusPill";
import { api } from "./lib/api";
import { HistoryPage } from "./pages/HistoryPage";
import { ResultsPage } from "./pages/ResultsPage";
import { SearchPage } from "./pages/SearchPage";
import { SetupPage } from "./pages/SetupPage";

export default function App() {
  const appStateQuery = useQuery({
    queryKey: ["app-state"],
    queryFn: api.getAppState,
  });

  return (
    <>
      <DisclaimerGate />
      <div className="min-h-screen bg-paper text-ink">
        <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-4 py-4 md:px-6 md:py-6">
          <div className="hidden w-[290px] shrink-0 lg:block">
            <Sidebar />
          </div>

          <main className="flex-1 space-y-6">
            <header className="relative overflow-hidden rounded-[32px] border border-ink/10 bg-shell/90 p-6 shadow-console">
              <div className="absolute inset-0 bg-grid-fade bg-[size:26px_26px] opacity-25" />
              <div className="relative flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-slate">
                    Safe workflow console
                  </p>
                  <p className="mt-3 max-w-2xl font-display text-5xl italic leading-tight text-ink">
                    Search hard, explain the fit, and stop before the risky click.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <StatusPill>
                    {appStateQuery.data?.emergency_stop_active ? "blocked" : "armed"}
                  </StatusPill>
                  <StatusPill>local api</StatusPill>
                  <StatusPill>boss adapter</StatusPill>
                </div>
              </div>
            </header>

            <Routes>
              <Route path="/" element={<SetupPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/results" element={<ResultsPage />} />
              <Route path="/history" element={<HistoryPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </>
  );
}
