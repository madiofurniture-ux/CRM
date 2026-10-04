// Single source of truth for navigation: which pages exist, their route, and which
// role-aware "app" group they belong to. The Sidebar renders from this, RoleManager
// grants permissions from this, and canAccess() gates on the ids here.
import {
  LayoutDashboard, Bell, Columns3, FileText, Receipt, UserPlus, Sparkles,
  Building2, CalendarDays, Hammer, DoorOpen, Package, BarChart3, ListTodo,
  Users, IndianRupee, AlertTriangle, FileSpreadsheet, PieChart, Fingerprint,
  Layers, Database, Contact, PhoneCall, TrendingUp, Wallet, LineChart, CalendarCheck2, HandCoins,
  LayoutTemplate, Landmark, ShoppingCart, Factory, MessageSquare, PhoneOutgoing,
  AlarmClock, LifeBuoy, Workflow, Zap, Rocket,
} from "lucide-react";

// app: the switcher group · id: unique key · to: route · label/icon: display
// perm (optional): the page grant that gates this item when it differs from
// id — lets a new screen ride an existing grant (Follow-ups -> leads,
// Service -> projects) so no existing account needs re-permissioning.
export const NAV = [
  // Overview (pinned — always shown above the app switcher)
  { app: "overview", id: "dashboard", to: "/", label: "Dashboard", icon: LayoutDashboard, pinned: true },
  { app: "overview", id: "analytics", to: "/analytics", label: "Analytics", icon: BarChart3, pinned: true },
  { app: "overview", id: "sales-tracker", perm: "analytics", to: "/sales-tracker", label: "Sales Tracker", icon: TrendingUp, pinned: true },
  { app: "overview", id: "alerts", to: "/alerts", label: "Follow-Up Alerts", icon: Bell, pinned: true },

  // Sell
  { app: "sell", id: "leads", to: "/leads", label: "Leads", icon: Sparkles },
  { app: "sell", id: "followups", perm: "leads", to: "/follow-ups", label: "Lead Follow-ups", icon: AlarmClock },
  { app: "sell", id: "calls", to: "/calls", label: "Call Log", icon: PhoneOutgoing },
  { app: "sell", id: "pipeline", to: "/pipeline", label: "Pipeline", icon: Columns3 },
  { app: "sell", id: "quotes", to: "/quotes", label: "Deals / Quotes", icon: FileText },
  { app: "sell", id: "quote-builder", to: "/quotes/builder", label: "Quote Builder", icon: LayoutTemplate },
  { app: "sell", id: "quote-followups", to: "/quotes/followups", label: "Quote Follow-ups", icon: PhoneCall },
  { app: "sell", id: "sales", to: "/sales", label: "Sales Register", icon: Receipt },
  { app: "sell", id: "visitors", to: "/visitors", label: "Visitors", icon: UserPlus },

  // Deliver
  { app: "deliver", id: "projects", to: "/projects", label: "Projects", icon: Hammer },
  { app: "deliver", id: "service", perm: "projects", to: "/service", label: "Service & Warranty", icon: LifeBuoy },
  { app: "deliver", id: "dwsurvey", to: "/dw-survey", label: "D&W Survey", icon: DoorOpen },
  { app: "deliver", id: "outstanding", to: "/outstanding", label: "Outstanding", icon: AlertTriangle },

  // Stock
  { app: "stock", id: "inventory", to: "/inventory", label: "Stock", icon: Package },
  { app: "stock", id: "stock-ledger", to: "/stock-ledger", label: "Stock Ledger", icon: Layers },
  { app: "stock", id: "purchase-orders", to: "/purchase-orders", label: "Purchase Orders", icon: ShoppingCart },
  { app: "stock", id: "manufacturer-orders", to: "/manufacturer-orders", label: "Manufacturer Orders", icon: Factory },
  { app: "stock", id: "inv-analytics", to: "/inventory/analytics", label: "Inv. Analytics", icon: BarChart3 },

  // Money
  { app: "money", id: "expenses", to: "/money-requests", label: "Money Requests", icon: HandCoins },
  { app: "money", id: "cashbook", to: "/cashbook", label: "Wallets & Cashbooks", icon: Wallet },
  { app: "money", id: "pnl", to: "/finance/pnl", label: "Profit & Loss", icon: TrendingUp },
  { app: "money", id: "project-pnl", to: "/reports/project-pnl", label: "Project P&L", icon: LineChart },
  { app: "money", id: "invoice-gen", to: "/invoices", label: "Tax Invoices", icon: FileSpreadsheet },
  { app: "money", id: "petty", to: "/petty-cash", label: "Petty Cash (history)", icon: IndianRupee },
  { app: "money", id: "incentives", to: "/incentives", label: "Incentives", icon: HandCoins },
  { app: "money", id: "finance-payments", to: "/payments", label: "Payments & Tax Invoices", icon: Landmark },

  // Relations
  { app: "relations", id: "customers", to: "/customers", label: "Customers", icon: Contact },
  { app: "relations", id: "architects", to: "/architects", label: "Architects", icon: Building2 },
  { app: "relations", id: "meetplan", to: "/meets", label: "Meet Planner", icon: CalendarDays },

  // Command
  { app: "command", id: "executive", to: "/executive", label: "Executive Analytics", icon: TrendingUp },
  { app: "command", id: "reports", to: "/reports", label: "Reports", icon: PieChart },
  { app: "command", id: "tasks", to: "/tasks", label: "Tasks", icon: ListTodo },
  { app: "command", id: "daily-planner", to: "/daily-planner", label: "Daily Planner", icon: CalendarCheck2 },
  { app: "command", id: "attendance", to: "/attendance", label: "Attendance", icon: Fingerprint },
  { app: "command", id: "payroll", to: "/people/payroll", label: "Payroll", icon: IndianRupee },
  { app: "command", id: "data-centre", to: "/data-centre", label: "Data Centre", icon: Database },
  { app: "command", id: "discussions", to: "/discussions", label: "Team Board", icon: MessageSquare },
  { app: "command", id: "record-chain", to: "/record-chain", label: "Record Chain", icon: TrendingUp },
  { app: "command", id: "audit-trail", to: "/audit", label: "Audit Trail", icon: AlertTriangle, adminOnly: true },
  { app: "command", id: "roles", to: "/admin/roles", label: "Role Manager", icon: Users, adminOnly: true },
  { app: "command", id: "setup", to: "/admin/setup", label: "Business Setup", icon: Rocket, adminOnly: true },
  { app: "command", id: "workflows", to: "/admin/workflows", label: "Workflows", icon: Workflow, adminOnly: true },
  { app: "command", id: "flows", to: "/admin/flows", label: "Flows", icon: Zap, adminOnly: true },
  { app: "command", id: "go-live", to: "/admin/go-live", label: "Go-live Data", icon: Database, adminOnly: true },
];

// Flat list for the Role Manager permission grid.
export const ALL_PAGES = NAV.filter((n) => (!n.adminOnly || n.id === "roles") && !n.perm)
  .map((n) => ({ id: n.id, label: n.label }));
