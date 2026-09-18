import { SHOW_LEGACY_MENUS } from "./featureFlags";

// Sub-nav content for every Baseplate primary pill, keyed by tab id.
// Every `to` is copied from an actual <Route path> in App.js — not invented.
// `page` mirrors the exact page="..." prop each route already uses on its
// <ProtectedRoute> in App.js, so canAccess(page) gates these sub-nav items
// the same way it gates the routes themselves. `adminOnly` mirrors the same
// flag on the equivalent entry in the old Sidebar.jsx.
//
// TODO(v1-scope): Requirements/Configurator/Visitors/Sales register (sales),
// Architects/Meet Planner (clients), Tasks/Daily Planner/Team & Access
// (people), every admin-settings item under "control" (Data Centre/Data
// Health/Financial Year/Workflows/Business Settings/Custom Fields/Roles &
// Permissions/Audit Trail), and Master Data (product) are NOT explicitly in
// the Madio Canonical CRM v1 scope (CRM: Leads/Opportunities/Accounts &
// Contacts/Quotations; HR: Attendance/Payroll; Admin: Users/Brands) but are
// kept visible per "if unsure, keep it" — revisit once v1 scope is final.
export const ALL_BASEPLATE_SUBNAV = {
  overview: [
    { code: "DA", label: "Dashboard", to: "/", page: "dashboard" },
    { code: "AL", label: "Alerts", to: "/alerts", page: "alerts" },
    { code: "RP", label: "Reports", to: "/reports", page: "reports" },
    { code: "EX", label: "Executive Analytics", to: "/executive", page: "executive" },
  ],
  sales: [
    { code: "PI", label: "Pipeline", to: "/pipeline", page: "pipeline" },
    { code: "LD", label: "Leads", to: "/leads", page: "leads" },
    { code: "RQ", label: "Requirements", to: "/requirements", page: "requirements" },
    { code: "CF", label: "Configurator", to: "/configurator", page: "configurator" },
    { code: "QT", label: "Quotations", to: "/quotes", page: "quotes", isNew: true },
    { code: "QB", label: "Quote Builder", to: "/quotes/builder", page: "quote-builder" },
    { code: "FU", label: "Follow-ups", to: "/quotes/followups", page: "quote-followups" },
    { code: "SR", label: "Sales register", to: "/sales", page: "sales" },
    { code: "VI", label: "Visitors", to: "/visitors", page: "visitors" },
  ],
  clients: [
    { code: "CU", label: "Customers", to: "/customers", page: "customers" },
    { code: "AR", label: "Architects", to: "/architects", page: "architects" },
    { code: "MP", label: "Meet Planner", to: "/meets", page: "meetplan" },
  ],
  delivery: [
    { code: "PR", label: "Projects", to: "/projects", page: "projects" },
    { code: "DW", label: "D&W Survey", to: "/dw-survey", page: "dwsurvey" },
    { code: "OS", label: "Outstanding", to: "/outstanding", page: "outstanding" },
  ],
  inventory: [
    { code: "ST", label: "Stock", to: "/inventory", page: "inventory" },
    { code: "SL", label: "Stock Ledger", to: "/stock-ledger", page: "stock-ledger" },
    { code: "IA", label: "Inv. Analytics", to: "/inventory/analytics", page: "inv-analytics" },
    { code: "PO", label: "Purchase Orders", to: "/purchase-orders", page: "purchase-orders" },
    { code: "MO", label: "Manufacturer Orders", to: "/manufacturer-orders", page: "manufacturer-orders" },
  ],
  finance: [
    { code: "TI", label: "Tax Invoices", to: "/invoices", page: "invoice-gen" },
    { code: "PC", label: "Petty Cash", to: "/petty-cash", page: "petty" },
    { code: "CB", label: "Cashbooks", to: "/cashbook", page: "cashbook" },
    { code: "TS", label: "Cashbook & Tally Sync", to: "/finance/tally", page: "cashbook" },
    { code: "PL", label: "Project P&L", to: "/reports/project-pnl", page: "project-pnl" },
    { code: "IN", label: "Incentives", to: "/incentives", page: "incentives" },
    { code: "PY", label: "Payments", to: "/payments", page: "finance-payments" },
  ],
  people: [
    { code: "TK", label: "Tasks", to: "/tasks", page: "tasks" },
    { code: "DP", label: "Daily Planner", to: "/daily-planner", page: "daily-planner" },
    { code: "AT", label: "Attendance", to: "/attendance", page: "attendance" },
    { code: "PR2", label: "Payroll", to: "/people/payroll", page: "payroll" },
    { code: "TM", label: "Team & Access", to: "/admin/teams", page: "teams", adminOnly: true },
    { code: "US", label: "Users", to: "/admin/roles", page: "roles", adminOnly: true },
  ],
  control: [
    { code: "DC", label: "Data Centre", to: "/data-centre", page: "data-centre", adminOnly: true },
    { code: "DH", label: "Data Health", to: "/admin/data-health", page: "data-health", adminOnly: true },
    { code: "FY", label: "Financial Year", to: "/admin/financial-year", page: "financial-year", adminOnly: true },
    { code: "WF", label: "Workflows", to: "/admin/workflows", page: "workflows", adminOnly: true },
    { code: "BS", label: "Business Settings", to: "/admin/business", page: "business", adminOnly: true },
    { code: "CX", label: "Custom Fields", to: "/admin/custom-fields", page: "custom-fields", adminOnly: true },
    { code: "RP2", label: "Roles & Permissions", to: "/admin/roles-permissions", page: "roles-permissions", adminOnly: true },
    { code: "AU", label: "Audit Trail", to: "/audit", page: "audit-trail", adminOnly: true },
    { code: "RC", label: "Record Chain", to: "/record-chain", page: "record-chain" },
    { code: "TB", label: "Team Board", to: "/discussions", page: "discussions" },
  ],
  product: [
    { code: "MD", label: "Master Data", to: "/admin/master-data", page: "master-data", adminOnly: true },
  ],
};

export const ALL_BASEPLATE_TABS = [
  { n: "01", label: "Overview", tab: "overview" },
  { n: "02", label: "Sales", tab: "sales" },
  { n: "03", label: "Clients", tab: "clients" },
  { n: "04", label: "Delivery", tab: "delivery" },
  { n: "05", label: "Inventory", tab: "inventory" },
  { n: "06", label: "Finance", tab: "finance" },
  { n: "07", label: "People", tab: "people" },
  { n: "08", label: "Control", tab: "control" },
  { n: "09", label: "Product", tab: "product" },
];

// Whole tabs outside v1 scope (CRM/HR/Admin — see the mission this was built
// for, docs/GO_LIVE_V1_CHECKLIST.md "UI Cleanup"): Delivery (project
// execution), Inventory (stock), Finance (invoicing/petty cash/cashbooks —
// distinct from HR Payroll, which has no dedicated page yet, see the
// checklist). Not deleted — just excluded from the exported, rendered list
// below unless SHOW_LEGACY_MENUS is on.
const LEGACY_TABS = new Set(["delivery", "inventory", "finance"]);

// Individual sub-nav items, outside v1 scope but living in tabs that stay
// (Reports/Executive Analytics are "advanced analytics"; Record Chain and
// Team Board/Discussions are outside CRM/HR/Admin v1 scope). Matched by code.
const LEGACY_ITEM_CODES = new Set(["RP", "EX", "RC", "TB"]);

export const BASEPLATE_SUBNAV = SHOW_LEGACY_MENUS
  ? ALL_BASEPLATE_SUBNAV
  : Object.fromEntries(
      Object.entries(ALL_BASEPLATE_SUBNAV)
        .filter(([tab]) => !LEGACY_TABS.has(tab))
        .map(([tab, items]) => [tab, items.filter((i) => !LEGACY_ITEM_CODES.has(i.code))])
    );

export const BASEPLATE_TABS = SHOW_LEGACY_MENUS
  ? ALL_BASEPLATE_TABS
  : ALL_BASEPLATE_TABS.filter((t) => !LEGACY_TABS.has(t.tab));

// Which tab a given pathname belongs to, so the header highlights the right
// pill/sub-item on a hard refresh or a link followed from outside the header.
// Scans the UNFILTERED map on purpose: a hidden route is still a real route
// (nothing removed from App.js), so a direct link to one should still
// highlight correctly rather than falling back to "overview".
export function tabForPath(pathname) {
  for (const [tab, items] of Object.entries(ALL_BASEPLATE_SUBNAV)) {
    if (items.some((i) => i.to === pathname)) return tab;
  }
  return "overview";
}
