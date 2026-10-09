import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import api from "@/lib/api";

// Where a search hit opens. Functions deep-link to the record itself.
const RESULT_ROUTE = {
  customer: (r) => `/customers/${r.id}`, lead: (r) => `/leads?open=${r.id}`,
  quotation: (r) => `/quotes/ws/${r.id}`, project: (r) => `/projects/${r.id}`,
  service_ticket: (r) => `/service?ticket=${r.id}`, architect: () => "/architects",
  virtual_item: (r) => `/virtual-catalogue?q=${encodeURIComponent((r.subtitle || "").split(" ")[0] || r.title)}`,
  inventory: () => "/inventory", employee: () => "/admin/roles",
};
const TYPE_LABEL = { service_ticket: "Service", quotation: "Quotation", customer: "Customer", lead: "Lead",
                     project: "Project", architect: "Architect", inventory: "Stock", virtual_item: "Catalogue product",
                     employee: "Staff" };

/** One search box for every record, in the global header (Ctrl/⌘ K). */
export default function GlobalSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const timer = useRef(null);
  const inputRef = useRef(null);
  const rootRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); inputRef.current?.focus(); }
    };
    const onDoc = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDoc); };
  }, []);

  const onSearch = (v) => {
    setQ(v);
    clearTimeout(timer.current);
    if (v.trim().length < 2) { setResults([]); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      try {
        const { data } = await api.get(`/search?q=${encodeURIComponent(v.trim())}`);
        setResults(data || []); setActive(0); setOpen(true);
      } catch { setResults([]); }
    }, 250);
  };
  const go = (r) => {
    setOpen(false); setQ("");
    inputRef.current?.blur();
    nav(RESULT_ROUTE[r.type] ? RESULT_ROUTE[r.type](r) : "/");
  };
  const onKeyDown = (e) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    if (e.key === "Enter") { e.preventDefault(); go(results[active]); }
    if (e.key === "Escape") setOpen(false);
  };

  return (
    <div className="relative w-full max-w-xl" ref={rootRef}>
      <div className="lx-search">
        <Search size={15} className="text-[var(--color-text-muted)] shrink-0" aria-hidden="true" />
        <input
          ref={inputRef} value={q} onChange={(e) => onSearch(e.target.value)} onKeyDown={onKeyDown}
          onFocus={() => results.length && setOpen(true)}
          placeholder="Search customers, leads, quotations, projects…"
          aria-label="Search every record"
          className="bg-transparent outline-none text-sm flex-1 min-w-0 placeholder:text-[var(--color-text-muted)]"
          data-testid="global-search-input"
        />
        {q ? (
          <button type="button" onClick={() => { setQ(""); setResults([]); setOpen(false); }} aria-label="Clear search"
                  className="text-[var(--color-text-muted)]"><X size={14} /></button>
        ) : <kbd className="hidden lg:inline text-[10px] text-[var(--color-text-muted)] border border-[var(--color-border)] rounded px-1">Ctrl K</kbd>}
      </div>
      {open && (
        <div className="absolute z-50 mt-1 left-0 right-0 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl max-h-96 overflow-y-auto" role="listbox">
          {results.length === 0 && <div className="p-3 text-sm text-[var(--color-text-muted)]">Nothing matches “{q}”.</div>}
          {results.map((r, i) => (
            <button key={`${r.type}-${r.id}-${i}`} onClick={() => go(r)} onMouseEnter={() => setActive(i)} role="option" aria-selected={i === active}
              data-testid={`search-result-${r.type}-${i}`}
              className={`w-full text-left px-3 py-2 flex items-center justify-between gap-3 ${i === active ? "bg-[var(--color-primary-soft)]" : ""}`}>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-[var(--color-text)] truncate">{r.title}</span>
                <span className="block text-xs text-[var(--color-text-muted)] truncate">{r.subtitle}</span>
              </span>
              <span className="text-[11px] text-[var(--color-text-muted)] shrink-0">{TYPE_LABEL[r.type] || r.type}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
