// Single source of truth for navigation: which pages exist, their route, and which
// role-aware "app" group they belong to. The Sidebar renders from this, RoleManager
// grants permissions from this, and canAccess() gates on the ids here.
import {
  LayoutDashboard, Bell, Columns3, FileText, Receipt, UserPlus, Sparkles,
  Building2, CalendarDays, Hammer, DoorOpen, Package, BarChart3, ListTodo,
  Users, IndianRupee, AlertTriangle, FileSpreadsheet, PieChart, Fingerprint,
  Layers, Database,
} from "lucide-react";

// app: the switcher group · id: permission key · to: route · label/icon: display
export const NAV = [
  // Overview (pinned — always shown above the app switcher)
  { app: "overview", id: "dashboard", to: "/", label: "Dashboard", icon: LayoutDashboard, pinned: true },
  { app: "overview", id: "alerts", to: "/alerts", label: "Follow-Up Alerts", icon: Bell, pinned: true },

  // Sell
  { app: "sell", id: "leads", to: "/leads", label: "Leads", icon: Sparkles },
  { app: "sell", id: "pipeline", to: "/pipeline", label: "Pipeline", icon: Columns3 },
  { app: "sell", id: "quotes", to: "/quotes", label: "Deals / Quotes", icon: FileText },
  { app: "sell", id: "sales", to: "/sales", label: "Sales Register", icon: Receipt },
  { app: "sell", id: "visitors", to: "/visitors", label: "Visitors", icon: UserPlus },

  // Deliver
  { app: "deliver", id: "projects", to: "/projects", label: "MAP Projects", icon: Hammer },
  { app: "deliver", id: "dwsurvey", to: "/dw-survey", label: "D&W Survey", icon: DoorOpen },
  { app: "deliver", id: "outstanding", to: "/outstanding", label: "Outstanding", icon: AlertTriangle },

  // Stock
  { app: "stock", id: "inventory", to: "/inventory", label: "Stock", icon: Package },
  { app: "stock", id: "stock-ledger", to: "/stock-ledger", label: "Stock Ledger", icon: Layers },
  { app: "stock", id: "inv-analytics", to: "/inventory/analytics", label: "Inv. Analytics", icon: BarChart3 },

  // Money
  { app: "money", id: "invoice-gen", to: "/invoices", label: "Tax Invoices", icon: FileSpreadsheet },
  { app: "money", id: "petty", to: "/petty-cash", label: "Petty Cash", icon: IndianRupee },

  // Relations
  { app: "relations", id: "architects", to: "/architects", label: "Architects", icon: Building2 },
  { app: "relations", id: "meetplan", to: "/meets", label: "Meet Planner", icon: CalendarDays },

  // Command
  { app: "command", id: "reports", to: "/reports", label: "Reports", icon: PieChart },
  { app: "command", id: "tasks", to: "/tasks", label: "Tasks", icon: ListTodo },
  { app: "command", id: "attendance", to: "/attendance", label: "Attendance", icon: Fingerprint },
  { app: "command", id: "data-centre", to: "/data-centre", label: "Data Centre", icon: Database },
  { app: "command", id: "roles", to: "/admin/roles", label: "Role Manager", icon: Users, adminOnly: true },
];

export const APPS = [
  { key: "sell", label: "Sell", icon: "◇" },
  { key: "deliver", label: "Deliver", icon: "🎨" },
  { key: "stock", label: "Stock", icon: "▣" },
  { key: "money", label: "Money", icon: "₹" },
  { key: "relations", label: "Relations", icon: "✦" },
  { key: "command", label: "Command", icon: "⌘" },
];

// Flat list for the Role Manager permission grid.
export const ALL_PAGES = NAV.filter((n) => !n.adminOnly || n.id === "roles")
  .map((n) => ({ id: n.id, label: n.label }));
