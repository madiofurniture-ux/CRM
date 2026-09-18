import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Plus, Bell, Shield, ShieldCheck } from "lucide-react";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import api from "@/lib/api";

const RESULT_ROUTE = {
  customer: "/customers", lead: "/leads", quotation: null /* built per-row */,
  project: "/projects", inventory: "/inventory", employee: "/admin/roles",
};

export default function Topbar({ title, subtitle, onAdd, addLabel = "New", actions }) {
  const { isOtherHidden, requestUnlock, relock } = usePrivacyMode();
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
        // Query string inlined into the URL, not passed as axios `params` —
        // lib/api.js's GET cache keys on the literal url string only, so
        // `params` alone would make every search collide on one cache entry.
        const { data } = await api.get(`/search?q=${encodeURIComponent(v.trim())}`);
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
    <header className="sticky top-0 z-30 h-16 bg-[var(--color-surface)]/85 backdrop-blur-md border-b border-[var(--color-border)] flex items-center px-3 sm:px-6 gap-2 sm:gap-4" data-testid="topbar">
      <div className="flex-1 min-w-0">
        <h1 className="font-heading text-[17px] sm:text-[20px] font-semibold text-[var(--color-text)] tracking-tight leading-tight truncate">
          {title}
        </h1>
        {subtitle && <div className="hidden sm:block text-xs text-[var(--color-text-muted)] mt-0.5">{subtitle}</div>}
      </div>

      <div className="hidden md:block relative w-72">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)]">
          <Search size={14} className="text-[var(--color-text-muted)]" strokeWidth={1.7} />
          <input
            value={q} onChange={(e) => onSearch(e.target.value)}
            onFocus={() => results.length && setOpen2(true)}
            placeholder="Search customers, leads, quotes…"
            className="bg-transparent outline-none text-sm flex-1 placeholder:text-[var(--color-text-muted)]"
            data-testid="global-search-input"
          />
          <kbd className="text-[10px] font-mono text-[var(--color-text-muted)] px-1.5 py-0.5 rounded border border-[var(--color-border)]">⌘K</kbd>
        </div>
        {open && (
          <div className="absolute z-30 mt-1 w-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-sm)] shadow-lg max-h-80 overflow-y-auto">
            {results.length === 0 && <div className="p-3 text-xs text-[var(--color-text-muted)]">No matches</div>}
            {results.map((r, i) => (
              <button key={i} onClick={() => goTo(r)} data-testid={`search-result-${r.type}-${i}`}
                className="w-full text-left px-3 py-2 hover:bg-[var(--color-surface-muted)] border-b border-[var(--color-border)] last:border-0 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-[var(--color-text)] truncate">{r.title}</div>
                  <div className="text-xs text-[var(--color-text-muted)] truncate">{r.subtitle}</div>
                </div>
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-semibold shrink-0">{r.type}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {actions}

      <button
        onClick={isOtherHidden ? requestUnlock : relock}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-semibold shrink-0 ${
          isOtherHidden ? "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]" : "bg-[var(--color-primary)] text-white"
        }`}
        title={isOtherHidden ? "Privacy Mode: ON — Other amounts masked" : "Unlocked — all Other amounts visible. Click to relock."}
        aria-label={isOtherHidden ? "Privacy Mode on, Other amounts masked. Click to unlock." : "Privacy Mode unlocked. Click to relock."}
        data-testid="privacy-mode-toggle"
      >
        {isOtherHidden ? <Shield size={15} strokeWidth={1.8} /> : <ShieldCheck size={15} strokeWidth={1.8} />}
        <span className="hidden sm:inline">{isOtherHidden ? "Privacy Mode" : "Unlocked"}</span>
      </button>

      <button className="p-2 rounded-full hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] shrink-0" aria-label="Notifications" data-testid="topbar-notifications">
        <Bell size={17} strokeWidth={1.7} />
      </button>

      {onAdd && (
        <button onClick={onAdd} className="btn-primary shrink-0 px-3 sm:px-4" data-testid="topbar-add-btn">
          <Plus size={15} strokeWidth={2} />
          <span className="hidden sm:inline">{addLabel}</span>
        </button>
      )}
    </header>
  );
}
