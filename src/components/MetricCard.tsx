interface MetricCardProps {
  label: string;
  value: string;
  hint: string;
}

export function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className="rounded-[24px] border border-ink/10 bg-shell/90 p-4 shadow-console">
      <p className="text-xs uppercase tracking-[0.2em] text-slate">{label}</p>
      <p className="mt-2 font-display text-3xl text-ink md:text-[2rem]">{value}</p>
      <p className="mt-2 text-xs leading-6 text-slate md:text-sm">{hint}</p>
    </div>
  );
}

