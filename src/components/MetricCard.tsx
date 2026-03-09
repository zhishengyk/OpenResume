interface MetricCardProps {
  label: string;
  value: string;
  hint: string;
}

export function MetricCard({ label, value, hint }: MetricCardProps) {
  return (
    <div className="rounded-[28px] border border-ink/10 bg-shell/90 p-5 shadow-console">
      <p className="text-xs uppercase tracking-[0.2em] text-slate">{label}</p>
      <p className="mt-3 font-display text-4xl text-ink">{value}</p>
      <p className="mt-2 text-sm text-slate">{hint}</p>
    </div>
  );
}

