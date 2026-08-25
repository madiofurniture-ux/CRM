import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";

/**
 * A searchable dropdown for picking one item from an existing list — used by
 * Visitors' "Reference" (Architects) and "Attended by" (Staff) fields so both
 * reuse the same already-loaded data instead of a plain text input.
 *
 * options: [{ id, label, sub }]   sub is optional secondary text (firm/type…)
 * value:   the selected id (or "" for none)
 * onChange(id, option)
 */
export default function SearchSelect({ options, value, onChange, placeholder = "Search…", emptyLabel = "No matches", testId }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    const onDoc = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const selected = useMemo(() => options.find((o) => o.id === value) || null, [options, value]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return options;
    return options.filter((o) =>
      o.label.toLowerCase().includes(s) || (o.sub || "").toLowerCase().includes(s)
    );
  }, [options, q]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 rounded-lg border border-[var(--border)] bg-white text-sm outline-none focus:border-[var(--brand)] flex items-center justify-between gap-2 text-left"
        data-testid={testId}
      >
        <span className={selected ? "truncate" : "truncate text-[var(--ink-3)]"}>
          {selected ? selected.label : placeholder}
        </span>
        <span className="flex items-center gap-1 shrink-0">
          {selected && (
            <X
              size={13}
              className="text-[var(--ink-3)] hover:text-[var(--ink)]"
              onClick={(e) => { e.stopPropagation(); onChange("", null); }}
            />
          )}
          <ChevronDown size={14} className="text-[var(--ink-3)]" />
        </span>
      </button>

      {open && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-[var(--border)] rounded-lg shadow-lg max-h-64 overflow-hidden flex flex-col">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Type to search…"
            className="px-3 py-2 text-sm border-b border-[var(--border-light)] outline-none"
          />
          <div className="overflow-y-auto">
            {filtered.length === 0 && (
              <div className="px-3 py-3 text-xs text-[var(--ink-3)]">{emptyLabel}</div>
            )}
            {filtered.map((o) => (
              <button
                type="button"
                key={o.id}
                onClick={() => { onChange(o.id, o); setOpen(false); setQ(""); }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-[var(--surface-2)] ${o.id === value ? "bg-[var(--brand-soft)]" : ""}`}
              >
                <div className="font-medium text-[var(--ink)] truncate">{o.label}</div>
                {o.sub && <div className="text-[11px] text-[var(--ink-3)] truncate">{o.sub}</div>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
