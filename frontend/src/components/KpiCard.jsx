export default function KpiCard({ label, value, hint, accent = "brand", icon: Icon, testid }) {
  const accents = {
    brand: { dot: "bg-[var(--brand)]", text: "text-[var(--brand)]" },
    moss: { dot: "bg-[var(--moss)]", text: "text-[var(--moss)]" },
    warn: { dot: "bg-[var(--warn)]", text: "text-[var(--warn)]" },
    danger: { dot: "bg-[var(--danger)]", text: "text-[var(--danger)]" },
    neutral: { dot: "bg-[var(--ink)]", text: "text-[var(--ink)]" },
  };
  const a = accents[accent] || accents.brand;
  return (
    <div
      className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 shadow-[0_1px_2px_rgba(26,29,26,0.04)] hover:shadow-[0_4px_12px_rgba(26,29,26,0.06)] transition"
      data-testid={testid}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${a.dot}`} />
          <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--ink-3)] font-semibold">{label}</span>
        </div>
        {Icon && <Icon size={15} strokeWidth={1.6} className="text-[var(--ink-3)]" />}
      </div>
      <div className="font-heading font-bold text-[28px] leading-none text-[var(--ink)] tracking-tight">
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-[var(--ink-3)]">{hint}</div>}
    </div>
  );
}
