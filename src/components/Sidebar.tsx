import { AlertTriangle, FolderSearch2, History, Settings2 } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "../lib/utils";

const items = [
  { to: "/", label: "Setup", icon: Settings2 },
  { to: "/search", label: "Search", icon: FolderSearch2 },
  { to: "/results", label: "Results", icon: AlertTriangle },
  { to: "/history", label: "History", icon: History },
];

export function Sidebar() {
  return (
    <aside className="relative overflow-hidden rounded-[28px] border border-ink/10 bg-shell/90 px-5 py-6 shadow-console">
      <div className="absolute inset-0 bg-grid-fade bg-[size:22px_22px] opacity-40" />
      <div className="relative flex h-full flex-col gap-8">
        <div>
          <p className="font-display text-4xl italic text-ink">OpenResume</p>
          <p className="mt-2 max-w-[16rem] text-sm leading-6 text-slate">
            Resume-first job scouting with explicit risk controls and user-held
            submission authority.
          </p>
        </div>

        <nav className="flex flex-col gap-2">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-2xl border border-transparent px-4 py-3 text-sm font-medium transition-all",
                    isActive
                      ? "border-ink/10 bg-ink text-shell"
                      : "text-ink/70 hover:border-ink/10 hover:bg-paper",
                  )
                }
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        <div className="mt-auto rounded-3xl border border-ember/20 bg-ember/10 p-4 text-sm text-ink/80">
          <p className="font-semibold uppercase tracking-[0.18em] text-ember">
            Safety line
          </p>
          <p className="mt-2 leading-6">
            This build never auto-submits applications. Guided actions stop at
            the final user-controlled step.
          </p>
        </div>
      </div>
    </aside>
  );
}

