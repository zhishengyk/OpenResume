import {
  AlertTriangle,
  Bot,
  FolderSearch2,
  History,
  KeyRound,
  Settings2,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "../lib/utils";

const items = [
  { to: "/", label: "\u8d44\u6599\u8bbe\u7f6e", icon: Settings2 },
  { to: "/models", label: "\u6a21\u578b\u914d\u7f6e", icon: Bot },
  { to: "/search", label: "\u641c\u7d22\u4efb\u52a1", icon: FolderSearch2 },
  { to: "/results", label: "\u7ed3\u679c\u9762\u677f", icon: AlertTriangle },
  { to: "/assets", label: "\u8d26\u53f7\u4e0e\u7b80\u5386\u6c60", icon: KeyRound },
  { to: "/history", label: "\u5386\u53f2\u8bb0\u5f55", icon: History },
];

export function Sidebar() {
  return (
    <aside className="relative overflow-hidden rounded-[28px] border border-ink/10 bg-shell/90 px-5 py-6 shadow-console">
      <div className="absolute inset-0 bg-grid-fade bg-[size:22px_22px] opacity-40" />
      <div className="relative flex h-full flex-col gap-8">
        <div>
          <p className="font-display text-4xl text-ink">OpenResume</p>
          <p className="mt-2 max-w-[16rem] text-sm leading-6 text-slate">
            {"\u7b80\u5386\u9a71\u52a8\u641c\u5c97\u3001\u5b98\u7f51\u6295\u9012\u548c\u8d44\u4ea7\u6c60\u7ba1\u7406"}
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
            {"\u5b89\u5168\u8fb9\u754c"}
          </p>
          <p className="mt-2 leading-6">
            {
              "\u9ed8\u8ba4\u6a21\u5f0f\u4e3a\u534a\u81ea\u52a8\u6295\u9012\uff0c\u4f1a\u5728\u6700\u7ec8\u63d0\u4ea4\u524d\u505c\u4e0b\u3002\u5168\u81ea\u52a8\u63d0\u4ea4\u9700\u8981\u989d\u5916\u786e\u8ba4\u98ce\u9669\u3002"
            }
          </p>
        </div>
      </div>
    </aside>
  );
}
