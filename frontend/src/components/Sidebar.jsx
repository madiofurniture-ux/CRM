import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Columns3, FileText, Receipt, UserPlus,
  Sparkles, Building2, Package, BarChart3, ListTodo, Users, LogOut, HardHat, MapPin,
  Bell, PieChart, DoorOpen, Layers, Database, IndianRupee, AlertTriangle, CalendarDays, FileSpreadsheet,
  CalendarRange, Workflow
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const SECTIONS = [
  {
    title: "Overview",
    items: [
      { id: "dashboard", to: "/", label: "Dashboard", icon: LayoutDashboard },
      { id: "alerts", to: "/alerts", label: "Follow-Up Alerts", icon: Bell },
      { id: "reports", to: "/reports", label: "Reports", icon: PieChart },
    ],
  },
  {
    title: "Sales CRM",
    items: [
      { id: "pipeline", to: "/pipeline", label: "Pipeline", icon: Columns3 },
      { id: "quotes", to: "/quotes", label: "Quotations", icon: FileText },
      { id: "sales", to: "/sales", label: "Sales Register", icon: Receipt },
      { id: "visitors", to: "/visitors", label: "Visitors", icon: UserPlus },
      { id: "leads", to: "/leads", label: "Leads", icon: Sparkles },
      { id: "architects", to: "/architects", label: "Architects", icon: Building2 },
    ],
  },
  {
    title: "Inventory",
    items: [
      { id: "inventory", to: "/inventory", label: "Stock", icon: Package },
      { id: "stock-ledger", to: "/stock-ledger", label: "Stock Ledger", icon: Layers },
      { id: "inv-analytics", to: "/inventory/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    title: "Work",
    items: [
      { id: "projects", to: "/projects", label: "Projects", icon: HardHat },
      { id: "dwsurvey", to: "/dw-survey", label: "D&W Survey", icon: DoorOpen },
      { id: "attendance", to: "/attendance", label: "Attendance", icon: MapPin },
      { id: "tasks", to: "/tasks", label: "Tasks", icon: ListTodo },
      { id: "meetplan", to: "/meets", label: "Meet Planner", icon: CalendarDays },
    ],
  },
  {
    title: "Finance",
    items: [
      { id: "invoice-gen", to: "/invoices", label: "Tax Invoices", icon: FileSpreadsheet },
      { id: "petty", to: "/petty-cash", label: "Petty Cash", icon: IndianRupee },
      { id: "outstanding", to: "/outstanding", label: "Outstanding", icon: AlertTriangle },
    ],
  },
  {
    title: "Admin",
    items: [
      { id: "data-centre", to: "/data-centre", label: "Data Centre", icon: Database, adminOnly: true },
      { id: "financial-year", to: "/admin/financial-year", label: "Financial Year", icon: CalendarRange, adminOnly: true },
      { id: "workflows", to: "/admin/workflows", label: "Workflows", icon: Workflow, adminOnly: true },
      { id: "roles", to: "/admin/roles", label: "Role Manager", icon: Users, adminOnly: true },
    ],
  },
];

export default function Sidebar() {
  const { user, canAccess, logout } = useAuth();
  if (!user) return null;

  return (
    <aside className="w-[240px] shrink-0 bg-[var(--surface-2)] border-r border-[var(--border)] flex flex-col h-screen sticky top-0" data-testid="sidebar">
      {/* Logo */}
      <div className="px-5 pt-6 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[var(--brand)] flex items-center justify-center text-white font-heading font-bold text-sm">M</div>
          <div>
            <div className="font-heading font-bold text-[15px] tracking-tight text-[var(--ink)] leading-tight">MADIO</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--ink-3)]">CRM Suite</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        {SECTIONS.map((sec) => {
          const visible = sec.items.filter((it) => {
            if (it.adminOnly && user.role !== "admin") return false;
            return canAccess(it.id);
          });
          if (visible.length === 0) return null;
          return (
            <div key={sec.title} className="mb-4">
              <div className="px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--ink-3)]">
                {sec.title}
              </div>
              {visible.map((it) => {
                const Icon = it.icon;
                return (
                  <NavLink
                    key={it.id}
                    to={it.to}
                    end={it.to === "/"}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors mb-0.5 ${
                        isActive
                          ? "bg-white text-[var(--ink)] shadow-[0_1px_2px_rgba(26,29,26,0.04)] border border-[var(--border-light)]"
                          : "text-[var(--ink-2)] hover:bg-white/60 hover:text-[var(--ink)]"
                      }`
                    }
                    data-testid={`nav-${it.id}`}
                  >
                    <Icon size={16} strokeWidth={1.7} />
                    <span className="font-medium">{it.label}</span>
                  </NavLink>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--border)] px-3 py-3 flex items-center gap-2.5">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-heading font-bold text-xs shrink-0"
          style={{ background: user.color || "#1A1D1A" }}
        >
          {user.icon || user.name?.[0] || "U"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-[var(--ink)] truncate">{user.name}</div>
          <div className="text-[11px] text-[var(--ink-3)] uppercase tracking-wide">{user.role}</div>
        </div>
        <button
          onClick={logout}
          className="p-1.5 rounded-md hover:bg-[var(--surface-hover)] text-[var(--ink-2)] transition"
          title="Sign out"
          data-testid="logout-btn"
        >
          <LogOut size={15} strokeWidth={1.7} />
        </button>
      </div>
    </aside>
  );
}
