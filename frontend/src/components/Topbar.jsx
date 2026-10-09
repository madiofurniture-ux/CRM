import { useState, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { IS_LIGHTNING } from "@/lib/featureFlags";
import { navItemForPath } from "@/lib/apps";
import { ObjectTile } from "@/components/lightning/LightningShell";
import { Search, Plus, Bell, Shield, ShieldCheck, X } from "lucide-react";
import { usePrivacyMode } from "@/context/PrivacyModeContext";
import api from "@/lib/api";

// Where a search hit opens. Functions deep-link to the record itself.
const RESULT_ROUTE = {
  customer: (r) => `/customers/${r.id}`, lead: (r) => `/leads?open=${r.id}`,
  quotation: (r) => `/quotes/ws/${r.id}`, project: (r) => `/projects/${r.id}`,
  service_ticket: (r) => `/service?ticket=${r.id}`, architect: () => "/architects",
  virtual_item: (r) => `/virtual-catalogue?q=${encodeURIComponent((r.subtitle || "").split(" ")[0] || r.title)}`,
  inventory: () => "/inventory", employee: () => "/admin/roles",
};
const TYPE_LABEL = { service_ticket: "service", virtual_item: "catalogue" };

export default function Topbar({ title, subtitle, onAdd, addLabel = "New", actions }) {
  const { isOtherHidden, requestUnlock, relock } = usePrivacyMode();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen2] = useState(false);
  const [mobileSearch, setMobileSearch] = useState(false);
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
    setOpen2(false); setQ(""); setMobileSearch(false);
    const route = RESULT_ROUTE[r.type];
    nav(route ? route(r) : "/");
  };
  const resultsList = open && (
    <div className="absolute z-30 mt-1 left-0 right-0 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-sm)] shadow-lg max-h-80 overflow-y-auto">
      {results.length === 0 && <div className="p-3 text-xs text-[var(--color-text-muted)]">No matches</div>}
      {results.map((r, i) => (
        <button key={i} onClick={() => goTo(r)} data-testid={`search-result-${r.type}-${i}`}
          className="w-full text-left px-3 py-2 hover:bg-[var(--color-surface-muted)] border-b border-[var(--color-border)] last:border-0 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--color-text)] truncate">{r.title}</div>
            <div className="text-xs text-[var(--color-text-muted)] truncate">{r.subtitle}</div>
          </div>
          <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--color-primary-soft)] text-[var(--color-primary)] font-semibold shrink-0">{TYPE_LABEL[r.type] || r.type}</span>
        </button>
      ))}
    </div>
  );

  const privacyButton = (
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
  );

  // Lightning shell: search and the bell live in the global header; the page
  // gets a header card with its object's icon tile, title and actions.
  if (IS_LIGHTNING) {
    const item = navItemForPath(pathname);
    const objectLabel = item && item.label !== title ? item.label : "";
    return (
      <header className="lx-page-header flex flex-wrap items-center gap-3" data-testid="topbar">
        <ObjectTile id={item?.id} size={36} />
        <div className="flex-1 min-w-[10rem]">
          {objectLabel && <div className="text-xs text-[var(--color-text-muted)] leading-tight">{objectLabel}</div>}
          <h1 className="font-heading text-[18px] sm:text-[20px] font-bold text-[var(--color-text)] leading-tight truncate">{title}</h1>
          {subtitle && <div className="text-xs text-[var(--color-text-muted)] mt-0.5 truncate">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {actions}
          {privacyButton}
          {onAdd && (
            <button onClick={onAdd} className="lx-btn lx-btn-brand" data-testid="topbar-add-btn">
              <Plus size={15} strokeWidth={2} /> {addLabel}
            </button>
          )}
        </div>
      </header>
    );
  }

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
            placeholder="Search name, phone, project, quote…"
            className="bg-transparent outline-none text-sm flex-1 placeholder:text-[var(--color-text-muted)]"
            data-testid="global-search-input"
          />
          <kbd className="text-[10px] font-mono text-[var(--color-text-muted)] px-1.5 py-0.5 rounded border border-[var(--color-border)]">⌘K</kbd>
        </div>
        {!mobileSearch && resultsList}
      </div>

      <button type="button" onClick={() => setMobileSearch(true)} className="md:hidden p-2 rounded-full hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)] shrink-0"
        aria-label="Search" data-testid="mobile-search-btn">
        <Search size={17} strokeWidth={1.8} />
      </button>
      {mobileSearch && (
        <div className="md:hidden fixed inset-x-0 top-0 z-50 bg-[var(--color-surface)] border-b border-[var(--color-border)] p-3 shadow-lg">
          <div className="relative">
            <div className="flex items-center gap-2 px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--color-surface-muted)] border border-[var(--color-border)]">
              <Search size={15} className="text-[var(--color-text-muted)]" />
              <input autoFocus value={q} onChange={(e) => onSearch(e.target.value)} placeholder="Name, phone, project, quote, ticket…"
                className="bg-transparent outline-none text-base flex-1" data-testid="mobile-search-input" />
              <button type="button" onClick={() => { setMobileSearch(false); setOpen2(false); }} aria-label="Close search"><X size={16} /></button>
            </div>
            {resultsList}
          </div>
        </div>
      )}

      {actions && (
        // On a phone the page's own controls scroll within their space rather
        // than pushing Privacy Mode and Notifications off the screen.
        <div className="flex items-center gap-2 min-w-0 max-w-[55vw] overflow-x-auto sm:max-w-none sm:overflow-visible shrink">
          {actions}
        </div>
      )}

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
