import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Plus, Menu } from "lucide-react";
import { useSidebar } from "@/context/SidebarContext";
import api from "@/lib/api";

const RESULT_ROUTE = {
  customer: "/customers", lead: "/leads", quotation: null /* built per-row */,
  project: "/projects", inventory: "/inventory", employee: "/admin/roles",
};

export default function Topbar({ title, subtitle, onAdd, addLabel = "New", actions }) {
  const { setOpen } = useSidebar();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen2] = useState(false);
  const timer = useRef(null);

  const onSearch = (v) => {
    setQ(v);
    clearTimeout(timer.current);
    if (v.trim().length < 2) { setResults([]); setOpen2(false); return; }
    timer.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/search", { params: { q: v.trim() } });
        setResults(data); setOpen2(true);
      } catch { setResults([]); }
    }, 300);
  };
  const goTo = (r) => {
    setOpen2(false); setQ("");
    if (r.type === "quotation") nav(`/quotes/ws/${r.id}`);
    else nav(RESULT_ROUTE[r.type] || "/");
  };

  return (
    <div className="sticky top-0 z-30 h-16 bg-white/85 backdrop-blur-md border-b border-[var(--border)] flex items-center px-3 sm:px-6 gap-2 sm:gap-4" data-testid="topbar">
      <button
        onClick={() => setOpen(true)}
        className="p-2 -ml-1 rounded-md hover:bg-[var(--surface-2)] text-[var(--ink-2)] lg:hidden shrink-0"
        aria-label="Open menu"
        data-testid="sidebar-open-btn"
      >
        <Menu size={20} strokeWidth={1.7} />
      </button>

      <div className="flex-1 min-w-0">
        <h1 className="font-heading text-[17px] sm:text-[20px] font-semibold text-[var(--ink)] tracking-tight leading-tight truncate">
          {title}
        </h1>
        {subtitle && <div className="hidden sm:block text-xs text-[var(--ink-3)] mt-0.5">{subtitle}</div>}
      </div>

      <div className="hidden md:block relative w-72">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-2)] border border-[var(--border)]">
          <Search size={14} className="text-[var(--ink-3)]" strokeWidth={1.7} />
          <input
            value={q} onChange={(e) => onSearch(e.target.value)}
            onFocus={() => results.length && setOpen2(true)}
            placeholder="Search customers, leads, quotes…"
            className="bg-transparent outline-none text-sm flex-1 placeholder:text-[var(--ink-3)]"
            data-testid="global-search-input"
          />
          <kbd className="text-[10px] font-mono text-[var(--ink-3)] px-1.5 py-0.5 rounded border border-[var(--border)]">⌘K</kbd>
        </div>
        {open && (
          <div className="absolute z-30 mt-1 w-full bg-white border border-[var(--border)] rounded-lg shadow-lg max-h-80 overflow-y-auto">
            {results.length === 0 && <div className="p-3 text-xs text-[var(--ink-3)]">No matches</div>}
            {results.map((r, i) => (
              <button key={i} onClick={() => goTo(r)} data-testid={`search-result-${r.type}-${i}`}
                className="w-full text-left px-3 py-2 hover:bg-[var(--surface-hover)] border-b border-[var(--border-light)] last:border-0 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-[var(--ink)] truncate">{r.title}</div>
                  <div className="text-xs text-[var(--ink-3)] truncate">{r.subtitle}</div>
                </div>
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--brand-soft)] text-[var(--brand)] font-semibold shrink-0">{r.type}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {actions}

      {onAdd && (
        <button onClick={onAdd} className="btn-primary shrink-0 px-3 sm:px-4" data-testid="topbar-add-btn">
          <Plus size={15} strokeWidth={2} />
          <span className="hidden sm:inline">{addLabel}</span>
        </button>
      )}
    </div>
  );
}
