import { Link } from "react-router-dom";
import { Menu, LogOut } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/** Top bar for the light shell: menu toggle (mobile sidebar), tenant/business
 * name (real value from AuthContext's tenant record — no tenant-switcher UI
 * since login is single-tenant-per-session, nothing to switch between), and
 * a compact user profile/logout area. */
export default function LightTopbar({ onToggleSidebar }) {
  const { user, tenant, logout } = useAuth();

  return (
    <header
      className="h-16 shrink-0 flex items-center justify-between gap-4 px-4 md:px-6 bg-[var(--color-surface)] border-b border-[var(--color-border)]"
      data-testid="light-topbar"
    >
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Toggle navigation sidebar"
          data-testid="light-sidebar-toggle"
          className="p-2 rounded-[var(--radius-sm)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)] transition-colors"
        >
          <Menu size={18} />
        </button>
        <Link to="/" className="flex items-center gap-2 min-w-0">
          <div
            className="w-8 h-8 rounded-[var(--radius-sm)] bg-[var(--color-primary)] text-white flex items-center justify-center font-bold text-sm shrink-0"
            aria-hidden="true"
          >
            {(tenant?.name || "M").slice(0, 1).toUpperCase()}
          </div>
          <span className="text-sm font-semibold text-[var(--color-text)] truncate">
            {tenant?.name || "Madio CRM"}
          </span>
        </Link>
      </div>

      <button
        type="button"
        onClick={logout}
        title="Log out"
        aria-label={`Log out (${user?.name || "current user"})`}
        data-testid="light-logout"
        className="flex items-center gap-2 shrink-0 px-2 py-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--color-surface-muted)] transition-colors group"
      >
        <div className="w-8 h-8 rounded-full bg-[var(--color-primary-soft)] text-[var(--color-primary)] flex items-center justify-center font-bold text-xs">
          {user?.icon || (user?.name || "?").slice(0, 1).toUpperCase()}
        </div>
        <div className="hidden sm:block leading-tight text-left">
          <div className="text-xs font-semibold text-[var(--color-text)]">{user?.name || "Account"}</div>
          <div className="text-[10px] text-[var(--color-text-muted)] flex items-center gap-1 group-hover:text-[var(--color-primary)]">
            <LogOut size={10} /> Log out
          </div>
        </div>
      </button>
    </header>
  );
}
