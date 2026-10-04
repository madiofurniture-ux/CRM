import { useMemo, useState } from "react";
import { Filter, X } from "lucide-react";
import { fmtDate } from "@/lib/format";

/**
 * "Filters" button + panel with one control per column, active filters as
 * removable chips, "Clear filters" and the match count. Pair with
 * useColumnFilters(page, columns): <ColumnFilters filters={cf} rows={rows} shown={n} />
 */
export default function ColumnFilters({ filters, rows = [], shown, testid = "column-filters" }) {
  const { columns, values, set, clear, active, read } = filters;
  const [open, setOpen] = useState(false);

  const options = useMemo(() => {
    const out = {};
    for (const c of columns) {
      if (c.type !== "select") continue;
      if (c.options) { out[c.key] = c.options; continue; }
      const seen = new Set();
      let blank = false;
      for (const r of rows) {
        const v = read(c, r);
        if (v == null || String(v).trim() === "") blank = true;
        else seen.add(String(v));
      }
      out[c.key] = [...[...seen].sort((a, b) => a.localeCompare(b)), ...(blank ? ["(blank)"] : [])];
    }
    return out;
  }, [columns, rows, read]);

  const chip = (c) => {
    const v = values[c.key];
    if (c.type === "date") return [v.from && `from ${fmtDate(v.from)}`, v.to && `to ${fmtDate(v.to)}`].filter(Boolean).join(" ");
    if (c.type === "number") return [v.min !== "" && v.min != null && `≥ ${v.min}`, v.max !== "" && v.max != null && `≤ ${v.max}`].filter(Boolean).join(" ");
    return c.type === "text" ? `“${v}”` : v;
  };

  const input = "w-full px-2 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm outline-none focus:border-[var(--color-primary)]";

  return (
    <div className="w-full" data-testid={testid}>
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm ${
            active.length ? "border-[var(--color-primary)] text-[var(--color-primary)] bg-[var(--color-primary-soft)]"
                          : "border-[var(--color-border)] text-[var(--color-text)] bg-[var(--color-surface)]"}`}
          data-testid={`${testid}-toggle`}
        >
          <Filter size={14} /> Filters{active.length ? ` (${active.length})` : ""}
        </button>
        {active.map((c) => (
          <span key={c.key} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border border-[var(--color-border)] bg-[var(--color-surface-muted)]">
            <span className="text-[var(--color-text-muted)]">{c.label}:</span> {chip(c)}
            <button type="button" onClick={() => clear(c.key)} aria-label={`Remove ${c.label} filter`} className="opacity-60 hover:opacity-100">
              <X size={11} />
            </button>
          </span>
        ))}
        {active.length > 0 && (
          <>
            <button type="button" onClick={() => clear()} className="text-xs font-medium text-[var(--color-primary)] px-1" data-testid={`${testid}-clear`}>
              Clear filters
            </button>
            {shown != null && <span className="text-xs text-[var(--color-text-muted)]" data-testid={`${testid}-count`}>{shown} of {rows.length} match</span>}
          </>
        )}
      </div>
      {open && (
        <div className="mt-2 p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid={`${testid}-panel`}>
          {columns.map((c) => (
            <label key={c.key} className="block text-xs text-[var(--color-text-muted)]">
              <span className="block mb-1 font-medium">{c.label}</span>
              {c.type === "select" && (
                <select value={values[c.key] || ""} onChange={(e) => set(c.key, e.target.value)} className={input} data-testid={`${testid}-${c.key}`}>
                  <option value="">Any</option>
                  {(options[c.key] || []).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {c.type === "date" && (
                <div className="flex gap-1">
                  <input type="date" value={values[c.key]?.from || ""} aria-label={`${c.label} from`}
                         onChange={(e) => set(c.key, { ...(values[c.key] || {}), from: e.target.value })} className={input} />
                  <input type="date" value={values[c.key]?.to || ""} aria-label={`${c.label} to`}
                         onChange={(e) => set(c.key, { ...(values[c.key] || {}), to: e.target.value })} className={input} />
                </div>
              )}
              {c.type === "number" && (
                <div className="flex gap-1">
                  <input type="number" inputMode="decimal" placeholder="Min" value={values[c.key]?.min ?? ""} aria-label={`${c.label} min`}
                         onChange={(e) => set(c.key, { ...(values[c.key] || {}), min: e.target.value })} className={input} />
                  <input type="number" inputMode="decimal" placeholder="Max" value={values[c.key]?.max ?? ""} aria-label={`${c.label} max`}
                         onChange={(e) => set(c.key, { ...(values[c.key] || {}), max: e.target.value })} className={input} />
                </div>
              )}
              {(!c.type || c.type === "text") && (
                <input value={values[c.key] || ""} placeholder="Contains…" onChange={(e) => set(c.key, e.target.value)}
                       className={input} data-testid={`${testid}-${c.key}`} />
              )}
            </label>
          ))}
          <div className="sm:col-span-2 lg:col-span-4 flex items-center justify-between text-xs">
            <span className="text-[var(--color-text-muted)]">{shown != null ? `${shown} of ${rows.length} match` : ""}</span>
            <span className="flex gap-3">
              <button type="button" onClick={() => clear()} className="text-[var(--color-text)]">Clear filters</button>
              <button type="button" onClick={() => setOpen(false)} className="font-medium text-[var(--color-primary)]">Done</button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
