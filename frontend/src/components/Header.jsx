import { Link, useLocation, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { BASEPLATE_SUBNAV, BASEPLATE_TABS, tabForPath } from "@/lib/baseplateNav";
import { useAuth } from "@/context/AuthContext";

const PILL_COUNTS = { overview: 3, sales: 5, clients: 3, delivery: 5, inventory: 3, finance: 6, people: 8, control: 7, product: 8 };

/**
 * Baseplate dual-tier shell: dark environment bar, primary numbered-pill nav,
 * and a sub-nav strip below it for whichever category the current route
 * belongs to. This is the app-wide header — Layout renders it once, above
 * every page's own content.
 */
export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, canAccess, logout } = useAuth();

  const isVisible = (item) => {
    if (item.adminOnly && user?.role !== "admin") return false;
    return canAccess(item.page);
  };

  const visibleTabs = BASEPLATE_TABS.filter((t) => (BASEPLATE_SUBNAV[t.tab] || []).some(isVisible));
  const activeTab = tabForPath(location.pathname);
  const subnav = (BASEPLATE_SUBNAV[activeTab] || []).filter(isVisible);

  const selectTab = (tab) => {
    const items = (BASEPLATE_SUBNAV[tab] || []).filter(isVisible);
    if (items[0]) navigate(items[0].to);
  };

  return (
    <div className="font-sans" data-testid="baseplate-header">
      {/* Baseplate bar */}
      <div className="h-8 bg-[#0B0D12] text-[11px] text-white/70 flex items-center justify-between px-4">
        <div className="flex items-center gap-1.5 font-mono uppercase tracking-wider">
          <span className="text-white font-semibold">BASEPLATE</span>
          <span className="text-white/30">/</span>
          <span>in_madio</span>
          <span className="text-white/30">/</span>
          <span>Madio — template org</span>
        </div>
        <div className="flex items-center gap-2 font-mono uppercase tracking-wider">
          <span>scope: unit</span>
          <span className="text-white/30">|</span>
          <span>FY 2026-27</span>
          <span className="text-white/30">|</span>
          <span>prod · release 4.2.0</span>
        </div>
      </div>

      {/* Primary nav */}
      <div className="h-16 bg-[#14161C] flex items-center justify-between px-4 gap-4">
        <Link to="/" className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-[#EC3013] text-white flex items-center justify-center font-bold text-sm">M</div>
          <div className="text-white text-sm font-semibold hidden lg:block">Madio — template org</div>
        </Link>

        <nav className="flex items-center gap-1 overflow-x-auto">
          {visibleTabs.map((p) => {
            const active = activeTab === p.tab;
            return (
              <button
                key={p.tab}
                type="button"
                onClick={() => selectTab(p.tab)}
                data-testid={`nav-pill-${p.tab}`}
                className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition ${
                  active ? "bg-[#EC3013] text-white" : "text-white/60 hover:text-white hover:bg-white/5"
                }`}
              >
                {p.n} {p.label} <span className={active ? "text-white/80" : "text-white/40"}>({PILL_COUNTS[p.tab]})</span>
              </button>
            );
          })}
        </nav>

        <button
          type="button"
          onClick={logout}
          title="Log out"
          aria-label={`Log out (${user?.name || "current user"})`}
          data-testid="baseplate-logout"
          className="flex items-center gap-2 shrink-0 group"
        >
          <div className="w-8 h-8 rounded-full bg-white/10 text-white flex items-center justify-center font-bold text-xs group-hover:bg-[#EC3013] transition">
            {user?.icon || "?"}
          </div>
          <div className="hidden xl:block leading-tight text-left">
            <div className="text-white text-xs font-semibold">{user?.name || "Account"}</div>
            <div className="text-white/40 text-[10px] group-hover:text-white/70 flex items-center gap-1">
              <LogOut size={10} /> Log out
            </div>
          </div>
        </button>
      </div>

      {/* Sub-nav strip */}
      {subnav.length > 0 && (
        <div className="h-11 bg-[#1B1E26] flex items-center gap-3 px-4 overflow-x-auto" data-testid="subnav-strip">
          <span className="shrink-0 text-[10px] font-mono font-bold tracking-widest text-[#EC3013]">
            {activeTab.toUpperCase()}
          </span>
          <div className="flex items-center gap-1.5">
            {subnav.map((s) => (
              <Link
                key={s.code}
                to={s.to}
                data-testid={`subnav-${s.code}`}
                className={`shrink-0 px-2.5 py-1 rounded-md text-[11px] font-mono transition flex items-center gap-1 ${
                  location.pathname === s.to ? "bg-white/10 text-white" : "text-white/70 hover:text-white hover:bg-white/5"
                }`}
              >
                <span className="text-white/40">{s.code}</span> {s.label}
                {s.isNew && <span className="text-[9px] px-1 rounded bg-[#EC3013] text-white font-bold">NEW</span>}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
