import { useState, useMemo } from "react";
import { NavLink } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { NAV, APPS } from "@/lib/nav";

// Role-aware "app switcher" IA: pinned Overview items always show; the rest are grouped
// into apps (Sell / Deliver / Stock / Money / Relations / Command) and revealed one app
// at a time — the same information architecture as the live web build.
export default function Sidebar() {
  const { user, canAccess, logout } = useAuth();

  const allowed = useMemo(
    () => NAV.filter((n) => (!n.adminOnly || user?.role === "admin") && canAccess(n.id)),
    [user, canAccess]
  );
  const pinned = allowed.filter((n) => n.pinned);
  const apps = APPS
    .map((a) => ({ ...a, items: allowed.filter((n) => n.app === a.key && !n.pinned) }))
    .filter((a) => a.items.length);

  const [activeApp, setActiveApp] = useState(apps[0]?.key || null);
  if (!user) return null;

  const linkClass = ({ isActive }) =>
    `flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors mb-0.5 ${
      isActive
        ? "bg-white text-[var(--ink)] shadow-[0_1px_2px_rgba(26,29,26,0.04)] border border-[var(--border-light)]"
        : "text-[var(--ink-2)] hover:bg-white/60 hover:text-[var(--ink)]"
    }`;
  const current = apps.find((a) => a.key === activeApp) || apps[0];

  return (
    <aside className="w-[240px] shrink-0 bg-[var(--surface-2)] border-r border-[var(--border)] flex flex-col h-screen sticky top-0" data-testid="sidebar">
      <div className="px-5 pt-6 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold text-sm">M</div>
          <div>
            <div className="font-heading font-bold text-[15px] tracking-tight text-[var(--ink)] leading-tight">MADIO</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--ink-3)]">CRM Suite</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        {/* Pinned overview */}
        {pinned.map((it) => {
          const Icon = it.icon;
          return (
            <NavLink key={it.id} to={it.to} end={it.to === "/"} className={linkClass} data-testid={`nav-${it.id}`}>
              <Icon size={16} strokeWidth={1.7} /><span className="font-medium">{it.label}</span>
            </NavLink>
          );
        })}

        {/* App switcher */}
        {apps.length > 0 && (
          <div className="grid grid-cols-3 gap-1 my-3 py-2 border-y border-[var(--border)]">
            {apps.map((a) => (
              <button
                key={a.key}
                onClick={() => setActiveApp(a.key)}
                data-testid={`app-${a.key}`}
                className={`flex flex-col items-center gap-1 py-2 rounded-lg text-[9px] font-medium transition-colors ${
                  current?.key === a.key ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "text-[var(--ink-3)] hover:bg-white/60"
                }`}
              >
                <span className="text-sm leading-none">{a.icon}</span>{a.label}
              </button>
            ))}
          </div>
        )}

        {/* Active app items */}
        {current && current.items.map((it) => {
          const Icon = it.icon;
          return (
            <NavLink key={it.id} to={it.to} className={linkClass} data-testid={`nav-${it.id}`}>
              <Icon size={16} strokeWidth={1.7} /><span className="font-medium">{it.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-[var(--border)] px-3 py-3 flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-heading font-bold text-xs shrink-0" style={{ background: user.color || "#1A1D1A" }}>
          {user.icon || user.name?.[0] || "U"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-[var(--ink)] truncate">{user.name}</div>
          <div className="text-[11px] text-[var(--ink-3)] uppercase tracking-wide">{user.role}</div>
        </div>
        <button onClick={logout} className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)] transition" title="Sign out" data-testid="logout-btn">
          <LogOut size={15} strokeWidth={1.7} />
        </button>
      </div>
    </aside>
  );
}
