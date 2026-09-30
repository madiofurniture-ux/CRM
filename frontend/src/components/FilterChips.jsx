/**
 * A row of saved-view chips with live counts — the filter pattern used across the
 * live web app's list pages. `views` is [{ key, label, count }]; the active key is
 * controlled by the parent.
 */
export default function FilterChips({ views, active, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5" data-testid="filter-chips">
      {views.map((v) => (
        <button
          key={v.key}
          onClick={() => onChange(v.key)}
          data-testid={`chip-${v.key}`}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            active === v.key
              ? "bg-[var(--brand-soft)] border-[var(--brand)] text-[var(--brand)]"
              : "bg-[var(--surface)] border-[var(--border)] text-[var(--ink-2)] hover:bg-[var(--surface-2)]"
          }`}
        >
          {v.label}
          {v.count != null && <span className="ml-1.5 opacity-70">{v.count}</span>}
        </button>
      ))}
    </div>
  );
}
