import {
  SHOW_LEGACY_MENUS,
  SHOW_DELIVERY, SHOW_INVENTORY, SHOW_FINANCE,
  SHOW_REPORTS, SHOW_RECORD_CHAIN, SHOW_INCENTIVES,
} from "./featureFlags";

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
//
// TODO(v1.2 reconciliation, docs/MODULE_READINESS_MATRIX.md): Budgets and
// Wallets are backend-only (backend/api_budget.py, backend/api_wallets.py)
// with no frontend page yet — no entry added here until
// docs/SCREEN_API_MODEL_MATRIX.md's "smallest implementation" ships;
// adding a `to` with no matching <Route> would violate this file's own
// "not invented" rule above. SHOW_BUDGETS/SHOW_WALLETS in featureFlags.js
// exist so that wiring is a one-line addition once the pages exist.
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
    // Duplicate of the "finance" tab's "IN" entry above (same route/page) —
    // this reconciliation pass groups Incentives under People (matching the
    // reference UI), the pre-existing baseplateNav put it under Finance;
    // kept both rather than deleting the Finance one, which isn't this
    // pass's call to make. Coded "IN2" (not "IN") so ITEM_FLAGS below can
    // gate it independently.
    { code: "IN2", label: "Incentives", to: "/incentives", page: "incentives" },
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

// Whole tabs gated per-module (docs/MODULE_READINESS_MATRIX.md: each of
// these is a verified full vertical slice — frontend + live API +
// persistence + tenant/RBAC + backend tests) rather than by the single
// SHOW_LEGACY_MENUS switch. SHOW_LEGACY_MENUS still forces all of them on
// (umbrella override), same as before.
const TAB_FLAGS = { delivery: SHOW_DELIVERY, inventory: SHOW_INVENTORY, finance: SHOW_FINANCE };

// Individual sub-nav items gated per-module, same reasoning as TAB_FLAGS.
// Record Chain/Team Board live inside the always-visible "control" tab;
// Reports/Executive Analytics inside the always-visible "overview" tab —
// hence per-item rather than per-tab gating for these. The two Incentives
// entries (IN/IN2) share SHOW_INCENTIVES.
const ITEM_FLAGS = {
  RP: SHOW_REPORTS, EX: SHOW_REPORTS, RC: SHOW_RECORD_CHAIN, TB: SHOW_LEGACY_MENUS,
  IN: SHOW_INCENTIVES, IN2: SHOW_INCENTIVES,
};

function tabVisible(tab) {
  return SHOW_LEGACY_MENUS || !(tab in TAB_FLAGS) || TAB_FLAGS[tab];
}

function itemVisible(item) {
  return SHOW_LEGACY_MENUS || !(item.code in ITEM_FLAGS) || ITEM_FLAGS[item.code];
}

export const BASEPLATE_SUBNAV = Object.fromEntries(
  Object.entries(ALL_BASEPLATE_SUBNAV)
    .filter(([tab]) => tabVisible(tab))
    .map(([tab, items]) => [tab, items.filter(itemVisible)])
);

export const BASEPLATE_TABS = ALL_BASEPLATE_TABS.filter((t) => tabVisible(t.tab));

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
