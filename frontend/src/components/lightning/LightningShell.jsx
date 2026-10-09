import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, LogOut, Search, X, Grip, Settings2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { APPS, NAV_BY_ID, OBJECT_COLOR, navItemForPath, splitTabs } from "@/lib/apps";
import {
  SHOW_DELIVERY, SHOW_INVENTORY, SHOW_FINANCE, SHOW_REPORTS, SHOW_RECORD_CHAIN, SHOW_INCENTIVES,
} from "@/lib/featureFlags";
import GlobalSearch from "@/components/lightning/GlobalSearch";
import ReminderCenter from "@/components/lightning/ReminderCenter";

// Same reversible module gating as the sidebar shell (featureFlags.js).
const ITEM_FLAG = {
  projects: SHOW_DELIVERY, dwsurvey: SHOW_DELIVERY, outstanding: SHOW_DELIVERY, service: SHOW_DELIVERY,
  inventory: SHOW_INVENTORY, "stock-ledger": SHOW_INVENTORY, "purchase-orders": SHOW_INVENTORY,
  "manufacturer-orders": SHOW_INVENTORY, "inv-analytics": SHOW_INVENTORY,
  "invoice-gen": SHOW_FINANCE, petty: SHOW_FINANCE, cashbook: SHOW_FINANCE, "project-pnl": SHOW_FINANCE,
  "finance-payments": SHOW_FINANCE, expenses: SHOW_FINANCE, pnl: SHOW_FINANCE,
  incentives: SHOW_INCENTIVES, reports: SHOW_REPORTS, executive: SHOW_REPORTS, "record-chain": SHOW_RECORD_CHAIN,
};
const APP_KEY = "madio.app";

export function ObjectTile({ id, size = 32, icon: IconOverride }) {
  const item = NAV_BY_ID[id];
  const Icon = IconOverride || item?.icon;
  return (
    <span className="lx-tile" style={{ background: OBJECT_COLOR[id] || "#5867E8", width: size, height: size }} aria-hidden="true">
      {Icon && <Icon size={Math.round(size * 0.55)} strokeWidth={2} />}
    </span>
  );
}

/** Salesforce Lightning-style chrome: global header (search, reminders,
 * profile), then the app bar (App Launcher, app name, the app's tabs). */
export default function LightningShell({ children }) {
  const { user, tenant, logout, canAccess, canSeeCost } = useAuth();
  const { pathname } = useLocation();
  const nav = useNavigate();
  const [launcher, setLauncher] = useState(false);
  const [profile, setProfile] = useState(false);
  const [mobileSearch, setMobileSearch] = useState(false);
  const profileRef = useRef(null);

  const visible = (id) => {
    const item = NAV_BY_ID[id];
    if (!item) return false;
    if (id in ITEM_FLAG && !ITEM_FLAG[id]) return false;
    if (item.adminOnly && user?.role !== "admin") return false;
    if (item.costOnly && !canSeeCost) return false;
    return canAccess(item.perm || item.id);
  };
  const apps = useMemo(() => APPS.map((a) => ({ ...a, items: a.tabs.filter(visible).map((id) => NAV_BY_ID[id]) }))
    .filter((a) => a.items.length), [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const current = navItemForPath(pathname);
  // The app stays what the person chose while its tabs cover this page;
  // otherwise it follows the page.
  const [appId, setAppId] = useState(() => { try { return window.localStorage.getItem(APP_KEY) || ""; } catch { return ""; } });
  const app = useMemo(() => {
    const chosen = apps.find((a) => a.id === appId);
    if (chosen && chosen.items.some((i) => i.id === current?.id)) return chosen;
    return apps.find((a) => a.items.some((i) => i.id === current?.id)) || chosen || apps[0];
  }, [apps, appId, current]);
  const chooseApp = (a) => {
    setAppId(a.id);
    try { window.localStorage.setItem(APP_KEY, a.id); } catch { /* per-browser convenience only */ }
    setLauncher(false);
    nav(a.items[0].to);
  };

  useEffect(() => {
    const onDoc = (e) => { if (profileRef.current && !profileRef.current.contains(e.target)) setProfile(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const initials = (user?.name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg)]" data-testid="lightning-shell">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[90] lx-btn">Skip to content</a>
      <header className="lx-header" data-testid="lx-header">
        <div className="lx-divisions" aria-hidden="true"><span /><span /><span /></div>
        <div className="flex items-center gap-3 px-3 sm:px-4 h-14">
          <Link to="/" className="flex items-center gap-2 shrink-0" aria-label={`${tenant?.name || "MADIO"} home`}>
            <span className="lx-mark">{(tenant?.name || "M").slice(0, 1).toUpperCase()}</span>
            <span className="hidden lg:block font-heading font-bold text-[15px] tracking-tight">{tenant?.name || "MADIO"}</span>
          </Link>
          <div className="flex-1 flex justify-center min-w-0">
            <div className="hidden sm:flex w-full justify-center"><GlobalSearch /></div>
          </div>
          <button type="button" className="sm:hidden lx-icon-btn" aria-label="Search" onClick={() => setMobileSearch(true)} data-testid="mobile-search-btn"><Search size={18} /></button>
          <ReminderCenter />
          <div className="relative" ref={profileRef}>
            <button type="button" onClick={() => setProfile((p) => !p)} aria-expanded={profile} aria-label={`Account: ${user?.name || ""}`}
                    className="lx-avatar" data-testid="lx-profile">{initials}</button>
            {profile && (
              <div className="absolute right-0 mt-2 w-60 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl z-50 py-1">
                <div className="px-4 py-3 border-b border-[var(--color-border)]">
                  <div className="font-semibold text-sm">{user?.name}</div>
                  <div className="text-xs text-[var(--color-text-muted)]">{tenant?.name}</div>
                </div>
                {user?.role === "admin" && (
                  <Link to="/admin/master-data" onClick={() => setProfile(false)} className="flex items-center gap-2 px-4 py-2 text-sm hover:bg-[var(--color-surface-muted)]">
                    <Settings2 size={15} /> Setup
                  </Link>
                )}
                <button type="button" onClick={logout} className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-[var(--color-surface-muted)]" data-testid="light-logout">
                  <LogOut size={15} /> Log out
                </button>
              </div>
            )}
          </div>
        </div>

        {mobileSearch && (
          <div className="sm:hidden absolute inset-x-0 top-0 z-50 bg-[var(--color-surface)] p-3 flex gap-2 shadow-lg">
            <GlobalSearch />
            <button type="button" className="lx-icon-btn" aria-label="Close search" onClick={() => setMobileSearch(false)}><X size={18} /></button>
          </div>
        )}
        <nav className="lx-appbar" aria-label="App navigation">
          <button type="button" onClick={() => setLauncher(true)} className="lx-launcher" aria-label="App Launcher" data-testid="app-launcher">
            <Grip size={18} />
          </button>
          <span className="lx-appname" data-testid="lx-app-name">{app?.label}</span>
          <AppTabs items={app?.items || []} currentId={current?.id} />
        </nav>
      </header>

      <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 outline-none overflow-x-hidden">
        {children}
      </main>

      {launcher && <AppLauncher apps={apps} onClose={() => setLauncher(false)} onApp={chooseApp}
                                 onItem={(i) => { setLauncher(false); nav(i.to); }} />}
    </div>
  );
}

/** The app's tabs; ones that don't fit go under "More". Each tab's real
 * width is measured (from an invisible copy of the row) and the row's
 * width is watched, so as many tabs show as actually fit — at any screen
 * size or browser zoom — and the page you're on always keeps its tab. */
function AppTabs({ items, currentId }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [widths, setWidths] = useState(null);
  const [avail, setAvail] = useState(0);
  const wrap = useRef(null);
  const measure = useRef(null);
  const moreRef = useRef(null);
  const ids = items.map((i) => i.id).join(",");

  useLayoutEffect(() => {
    const read = () => {
      const el = measure.current;
      if (!el) return;
      const w = {};
      el.querySelectorAll("[data-measure]").forEach((n) => { w[n.dataset.measure] = Math.ceil(n.getBoundingClientRect().width); });
      setWidths(w);
    };
    read();
    let live = true;
    // Web fonts arrive after the first paint and change every width.
    document.fonts?.ready?.then(() => live && read()).catch(() => {});
    return () => { live = false; };
  }, [ids]);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return undefined;
    const update = () => setAvail(Math.floor(el.clientWidth));
    update();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    ro?.observe(el);
    window.addEventListener("resize", update);
    return () => { ro?.disconnect(); window.removeEventListener("resize", update); };
  }, []);

  useEffect(() => {
    const onDoc = (e) => { if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  useEffect(() => { setMoreOpen(false); }, [currentId]);

  const { shown, extra } = useMemo(() => splitTabs(items, widths, avail, currentId), [items, widths, avail, currentId]);
  return (
    <div ref={wrap} className="flex-1 min-w-0 flex items-stretch relative" data-testid="lx-app-tabs">
      <div className="flex items-stretch min-w-0 overflow-hidden">
        {shown.map((i) => (
          <Link key={i.id} to={i.to} className={`lx-tab ${i.id === currentId ? "is-active" : ""}`}
                aria-current={i.id === currentId ? "page" : undefined} data-testid={`light-nav-${i.id}`}>
            {i.label}
          </Link>
        ))}
      </div>
      {extra.length > 0 && (
        <div className="relative flex shrink-0" ref={moreRef}>
          <button type="button" onClick={() => setMoreOpen((o) => !o)} aria-expanded={moreOpen} aria-haspopup="menu"
                  className="lx-tab" data-testid="lx-more">
            More <span className="lx-more-count">{extra.length}</span> <ChevronDown size={14} className="ml-1" />
          </button>
          {moreOpen && (
            <div role="menu" className="absolute right-0 top-full mt-1 w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl z-50 py-1">
              {extra.map((i) => (
                <Link key={i.id} to={i.to} role="menuitem" onClick={() => setMoreOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--color-surface-muted)]" data-testid={`light-nav-${i.id}`}>
                  <ObjectTile id={i.id} size={22} /> {i.label}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
      {/* Invisible copy of the row: each tab's natural width (bold is allowed for in splitTabs). */}
      <div ref={measure} aria-hidden="true" className="absolute left-0 top-0 flex invisible pointer-events-none h-0 overflow-hidden"
           style={{ width: "max-content" }}>
        {items.map((i) => <span key={i.id} data-measure={i.id} className="lx-tab shrink-0">{i.label}</span>)}
        <span data-measure="__more" className="lx-tab shrink-0">More <span className="lx-more-count">{items.length}</span> <ChevronDown size={14} className="ml-1" /></span>
      </div>
    </div>
  );
}

/** App Launcher: the apps, and every page you can open, searchable. */
function AppLauncher({ apps, onClose, onApp, onItem }) {
  const [q, setQ] = useState("");
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const all = useMemo(() => {
    const seen = new Set();
    return apps.flatMap((a) => a.items).filter((i) => (seen.has(i.id) ? false : seen.add(i.id)));
  }, [apps]);
  const term = q.trim().toLowerCase();
  const items = term ? all.filter((i) => i.label.toLowerCase().includes(term)) : all;
  const shownApps = term ? apps.filter((a) => a.label.toLowerCase().includes(term) || a.blurb.toLowerCase().includes(term)) : apps;
  return (
    <div className="fixed inset-0 z-[70] bg-black/40 flex items-start justify-center p-3 sm:p-8" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="App Launcher" onClick={(e) => e.stopPropagation()}
           className="bg-[var(--color-surface)] rounded-[var(--radius-lg)] shadow-2xl w-full max-w-4xl max-h-[88vh] overflow-y-auto" data-testid="app-launcher-panel">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[var(--color-border)]">
          <h2 className="font-heading font-bold text-lg">App Launcher</h2>
          <div className="lx-search flex-1 max-w-sm ml-auto">
            <Search size={15} className="text-[var(--color-text-muted)]" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search apps and pages"
                   className="bg-transparent outline-none text-sm flex-1" aria-label="Search apps and pages" />
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="lx-icon-btn"><X size={18} /></button>
        </div>
        {shownApps.length > 0 && (
          <section className="p-5">
            <h3 className="text-sm font-semibold mb-3">Apps</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {shownApps.map((a) => (
                <button key={a.id} type="button" onClick={() => onApp(a)} data-testid={`app-${a.id}`}
                        className="flex items-center gap-3 p-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] text-left hover:border-[var(--color-primary)] hover:bg-[var(--color-primary-soft)]">
                  <span className="lx-app-tile" style={{ background: a.color }}>{a.label.slice(0, 2)}</span>
                  <span>
                    <span className="block font-semibold text-sm">{a.label}</span>
                    <span className="block text-xs text-[var(--color-text-muted)]">{a.blurb}</span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
        <section className="px-5 pb-5">
          <h3 className="text-sm font-semibold mb-3">All pages</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1">
            {items.map((i) => (
              <button key={i.id} type="button" onClick={() => onItem(i)}
                      className="flex items-center gap-2 px-2 py-2 rounded text-sm text-left hover:bg-[var(--color-surface-muted)]">
                <ObjectTile id={i.id} size={24} /> <span className="truncate">{i.label}</span>
              </button>
            ))}
            {!items.length && <div className="text-sm text-[var(--color-text-muted)]">No page matches “{q}”.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
