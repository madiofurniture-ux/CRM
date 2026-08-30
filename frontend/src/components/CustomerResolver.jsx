import { useState, useRef } from "react";
import api from "@/lib/api";
import { Search, UserCheck } from "lucide-react";

/**
 * Shared "does this customer already exist" lookup — Walk-in, Lead, and
 * Quotation creation all use this instead of rolling their own dedup check.
 * Search by phone or name; picking a result calls onSelect(customer).
 *
 * Usage: <CustomerResolver onSelect={(c) => prefillFrom(c)} />
 */
export default function CustomerResolver({ onSelect, placeholder = "Search phone or name…" }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  const onChange = (v) => {
    setQ(v);
    clearTimeout(timer.current);
    if (v.trim().length < 2) { setResults([]); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      try {
        // The literal query string is part of the cache key in lib/api.js's
        // GET cache — using axios's `params` instead would make every
        // search collide on the same cache entry ("/customers/search").
        const { data } = await api.get(`/customers/search?q=${encodeURIComponent(v.trim())}`);
        setResults(data);
        setOpen(true);
      } catch { setResults([]); }
    }, 300);
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] bg-white">
        <Search size={14} className="text-[var(--ink-3)]" />
        <input
          value={q} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
          className="flex-1 outline-none text-sm bg-transparent"
          onFocus={() => results.length && setOpen(true)}
          data-testid="customer-resolver-input"
        />
      </div>
      {open && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-[var(--border)] rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {results.length === 0 && <div className="p-3 text-xs text-[var(--ink-3)]">No matching customer — create new.</div>}
          {results.map((c) => (
            <button
              key={c.id} type="button"
              onClick={() => { onSelect(c); setOpen(false); setQ(c.name); }}
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-hover)] border-b border-[var(--border-light)] last:border-0 flex items-center justify-between gap-2"
              data-testid={`customer-resolver-${c.id}`}
            >
              <div>
                <div className="text-sm font-medium text-[var(--ink)]">{c.name}</div>
                <div className="text-xs font-mono text-[var(--ink-3)]">{c.phone}</div>
              </div>
              <div className="text-[10px] text-[var(--ink-3)] text-right shrink-0">
                <div>{c.project_count || 0} Projects</div>
                <div>{c.quote_count || 0} Quotes</div>
              </div>
            </button>
          ))}
          <button type="button" onClick={() => setOpen(false)} className="w-full text-left px-3 py-2 text-xs text-[var(--brand)] font-medium hover:bg-[var(--surface-hover)] flex items-center gap-1.5">
            <UserCheck size={12} /> None of these — create new customer
          </button>
        </div>
      )}
    </div>
  );
}
