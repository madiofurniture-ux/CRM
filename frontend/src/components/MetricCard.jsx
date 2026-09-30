import { Link } from "react-router-dom";

/** A single KPI tile — real value + optional sub-label, optionally a real
 * link to the page that value comes from. Token-driven so it renders
 * correctly under both the baseplate and light themes without a per-theme
 * fork. Renders "Not configured" (per docs/LIGHT_THEME_MIGRATION_PLAN.md)
 * rather than a fabricated number when `value` is null/undefined. */
export default function MetricCard({ label, value, sub, to, loading = false }) {
  const body = (
    <div
      className={`bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-4 ${
        to ? "hover:border-[var(--color-primary)] transition-colors" : ""
      }`}
      data-testid={`metric-${label}`}
    >
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
        {label}
      </div>
      {loading ? (
        <>
          <div className="h-6 w-16 bg-[var(--color-surface-muted)] rounded animate-pulse mb-2" />
          <div className="h-2.5 w-24 bg-[var(--color-surface-muted)] rounded animate-pulse" />
        </>
      ) : (
        <>
          <div className="text-xl font-bold text-[var(--color-text)] font-mono tabular-nums">
            {value == null ? "Not configured" : value}
          </div>
          {sub && <div className="text-xs text-[var(--color-text-muted)] mt-1">{sub}</div>}
        </>
      )}
    </div>
  );
  return to && !loading && value != null ? <Link to={to}>{body}</Link> : body;
}
