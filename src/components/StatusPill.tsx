import { cn, statusTone } from "../lib/utils";

interface StatusPillProps {
  children: string;
  className?: string;
}

export function StatusPill({ children, className }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em]",
        statusTone(children.toLowerCase()),
        className,
      )}
    >
      {children.replaceAll("_", " ")}
    </span>
  );
}

