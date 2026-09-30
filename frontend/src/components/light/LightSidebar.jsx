import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard } from "lucide-react";
import { NAV } from "@/lib/nav";
import { useAuth } from "@/context/AuthContext";
import {
  SHOW_DELIVERY, SHOW_INVENTORY, SHOW_FINANCE, SHOW_REPORTS,
  SHOW_RECORD_CHAIN, SHOW_INCENTIVES,
} from "@/lib/featureFlags";

// Same reversible module gating baseplateNav.js applies to the pill header
// — this shell only changes CHROME, not which modules a hidden flag or a
// role/tenant grant exposes. Keyed by nav.js item id (not by its "app"
// group) so a single flagged item inside an otherwise-visible group (e.g.
// "incentives" inside "money") can be gated independently.
const ITEM_FLAG = {
  projects: SHOW_DELIVERY, dwsurvey: SHOW_DELIVERY, outstanding: SHOW_DELIVERY,
  inventory: SHOW_INVENTORY, "stock-ledger": SHOW_INVENTORY,
  "purchase-orders": SHOW_INVENTORY, "manufacturer-orders": SHOW_INVENTORY,
  "inv-analytics": SHOW_INVENTORY,
  "invoice-gen": SHOW_FINANCE, petty: SHOW_FINANCE, cashbook: SHOW_FINANCE,
  "project-pnl": SHOW_FINANCE, "finance-payments": SHOW_FINANCE,
  incentives: SHOW_INCENTIVES,
  reports: SHOW_REPORTS, executive: SHOW_REPORTS,
  "record-chain": SHOW_RECORD_CHAIN,
};

// Primary sections requested for the light shell (Overview, Pipeline,
// Contacts/Clients, Team, Tasks, Reports), extended with the rest of
// nav.js's existing groups so no functionality is lost — everything below
// "Reports" is exactly what the header pill nav already exposes/gates,
// just grouped for a left sidebar instead of a top pill bar.
const SECTIONS = [
  { label: "Overview", ids: ["dashboard", "alerts"] },
  { label: "Pipeline", ids: ["leads", "pipeline", "requirements", "configurator", "quotes",
    "quote-builder", "quote-followups", "sales", "visitors"] },
  { label: "Contacts / Clients", ids: ["customers", "architects", "meetplan"] },
  { label: "Tasks", ids: ["tasks", "daily-planner"] },
  { label: "Team", ids: ["attendance", "payroll", "roles"] },
  { label: "Reports", ids: ["reports", "executive", "record-chain"] },
  { label: "Delivery", ids: ["projects", "dwsurvey", "outstanding"] },
  { label: "Inventory", ids: ["inventory", "stock-ledger", "purchase-orders", "manufacturer-orders", "inv-analytics"] },
  { label: "Finance", ids: ["invoice-gen", "petty", "cashbook", "project-pnl", "incentives", "finance-payments"] },
  { label: "Admin", ids: ["data-centre", "discussions", "audit-trail"] },
];

export default function LightSidebar({ collapsed = false, onNavigate }) {
  const location = useLocation();
  const { user, canAccess } = useAuth();
  const byId = Object.fromEntries(NAV.map((n) => [n.id, n]));

  const isVisible = (id) => {
    const item = byId[id];
    if (!item) return false;
    if (id in ITEM_FLAG && !ITEM_FLAG[id]) return false;
    if (item.adminOnly && user?.role !== "admin") return false;
    return canAccess(item.id);
  };

  return (
    <nav
      aria-label="Primary"
      className={`h-full flex flex-col bg-[var(--color-surface)] border-r border-[var(--color-border)] transition-all ${collapsed ? "w-16" : "w-64"}`}
    >
      <div className="flex-1 overflow-y-auto py-4 px-2 space-y-5">
        {SECTIONS.map((section) => {
          const items = section.ids.map((id) => byId[id]).filter((item) => item && isVisible(item.id));
          if (items.length === 0) return null;
          return (
            <div key={section.label}>
              {!collapsed && (
                <div className="px-3 mb-1.5 text-[10px] font-mono font-bold uppercase tracking-widest text-[var(--color-text-muted)]">
                  {section.label}
                </div>
              )}
              <div className="space-y-0.5">
                {items.map((item) => {
                  const Icon = item.icon || LayoutDashboard;
                  const active = location.pathname === item.to;
                  return (
                    <Link
                      key={item.id}
                      to={item.to}
                      onClick={onNavigate}
                      data-testid={`light-nav-${item.id}`}
                      title={collapsed ? item.label : undefined}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-3 px-3 py-2 rounded-[var(--radius-sm)] text-sm font-medium transition-colors ${
                        active
                          ? "bg-[var(--color-primary-soft)] text-[var(--color-primary)]"
                          : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]"
                      }`}
                    >
                      <Icon size={18} strokeWidth={active ? 2.25 : 1.75} className="shrink-0" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </nav>
  );
}
