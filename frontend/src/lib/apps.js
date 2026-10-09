// Lightning-style navigation: the App Launcher's apps, the tabs each app
// shows, and every object's icon colour. Items come from lib/nav.js (the one
// list of pages, routes and permissions); this only groups and colours them.
import { NAV } from "@/lib/nav";

export const APPS = [
  { id: "sales", label: "Sales", blurb: "Leads, deals and orders", color: "#0B827C",
    // Day-to-day pages first, so on a narrow screen it's the occasional ones
    // (catalogues, the builder) that go under "More".
    tabs: ["dashboard", "leads", "followups", "pipeline", "quotes", "quote-followups", "sales", "customers", "calls",
           "meetplan", "tasks", "visitors", "architects", "catalogues", "virtual-catalogue", "vendor-brochures",
           "quote-builder"] },
  { id: "service", label: "Delivery", blurb: "Projects, surveys and service", color: "#3BA755",
    tabs: ["projects", "dwsurvey", "service", "outstanding", "tasks", "meetplan", "customers"] },
  { id: "stock", label: "Stock", blurb: "Inventory and purchasing", color: "#8A5A3B",
    tabs: ["inventory", "stock-ledger", "purchase-orders", "manufacturer-orders", "inv-analytics"] },
  { id: "finance", label: "Finance", blurb: "Money, invoices and P&L", color: "#2E6E73",
    tabs: ["invoice-gen", "finance-payments", "expenses", "cashbook", "pnl", "project-pnl", "outstanding", "incentives", "petty"] },
  { id: "people", label: "People", blurb: "Your day, attendance and payroll", color: "#C98A1B",
    tabs: ["daily-planner", "tasks", "meetplan", "attendance", "payroll", "discussions"] },
  { id: "insights", label: "Insights", blurb: "Analytics and reports", color: "#5867E8",
    tabs: ["dashboard", "analytics", "sales-tracker", "alerts", "reports", "executive", "record-chain"] },
  { id: "admin", label: "Setup", blurb: "Users, workflows and data", color: "#706E6B",
    tabs: ["roles", "workflows", "flows", "data-centre", "audit-trail", "go-live"] },
];

// Object icon tiles, as Lightning colours each object type.
export const OBJECT_COLOR = {
  dashboard: "#5867E8", analytics: "#5867E8", "sales-tracker": "#5867E8", alerts: "#E4A201", reports: "#5867E8",
  executive: "#5867E8", "record-chain": "#5867E8",
  leads: "#F88962", followups: "#E4A201", calls: "#4BC076", pipeline: "#FCB95B", quotes: "#FCB95B",
  "quote-builder": "#FCB95B", catalogues: "#9050E9", "virtual-catalogue": "#9050E9", "vendor-brochures": "#A86B32", "quote-followups": "#E4A201", sales: "#3BA755", visitors: "#F88962",
  customers: "#7F8DE1", architects: "#7F8DE1", meetplan: "#EB7092", tasks: "#4BC076", "daily-planner": "#4BC076",
  projects: "#3BA755", dwsurvey: "#2E6E73", service: "#F2CF5B", outstanding: "#BA0517",
  inventory: "#8A5A3B", "stock-ledger": "#8A5A3B", "purchase-orders": "#A86B32", "manufacturer-orders": "#A86B32",
  "inv-analytics": "#8A5A3B",
  "invoice-gen": "#2E6E73", "finance-payments": "#2E6E73", expenses: "#2E6E73", cashbook: "#2E6E73",
  pnl: "#2E6E73", "project-pnl": "#2E6E73", incentives: "#2E6E73", petty: "#2E6E73",
  attendance: "#C98A1B", payroll: "#C98A1B", discussions: "#C98A1B",
  roles: "#706E6B", workflows: "#706E6B", flows: "#706E6B", "data-centre": "#706E6B", "audit-trail": "#706E6B",
  "go-live": "#706E6B",
};

export const NAV_BY_ID = Object.fromEntries(NAV.map((n) => [n.id, n]));

// Routes that aren't nav items but belong to one (record pages and editors).
const EXTRA_ROUTES = [
  ["/customers/", "customers"], ["/projects/", "projects"], ["/quotes/ws/", "quotes"],
  ["/quotes/builder", "quote-builder"], ["/admin/master-data", "data-centre"], ["/admin/business", "data-centre"],
  ["/admin/custom-fields", "data-centre"], ["/admin/teams", "roles"], ["/admin/roles-permissions", "roles"],
  ["/admin/data-health", "data-centre"], ["/admin/financial-year", "data-centre"], ["/finance/tally", "cashbook"],
  ["/approvals", "expenses"],
];

/** The nav item a path belongs to: exact route first, then known
 * sub-routes, then the longest route prefix. */
export function navItemForPath(pathname) {
  const exact = NAV.find((n) => n.to === pathname);
  if (exact) return exact;
  const extra = EXTRA_ROUTES.find(([prefix]) => pathname.startsWith(prefix));
  if (extra) return NAV_BY_ID[extra[1]];
  return [...NAV].filter((n) => n.to !== "/" && pathname.startsWith(n.to)).sort((a, b) => b.to.length - a.to.length)[0]
    || NAV_BY_ID.dashboard;
}

/** Which tabs fit in the app bar and which go under "More".
 * widths: { [id]: natural width in px, __more: the More button's width };
 * avail: the row's width. Tabs keep their order; the page you're on always
 * has its tab in the bar (it takes the last place that fits). Until widths
 * are known every tab is shown. */
export function splitTabs(items, widths, avail, currentId) {
  if (!widths || !(avail > 0)) return { shown: items, extra: [] };
  // The active tab is set in bold, a little wider than measured.
  const w = (i) => (widths[i.id] || 0) * (i.id === currentId ? 1.08 : 1);
  if (items.reduce((sum, i) => sum + w(i), 0) <= avail) return { shown: items, extra: [] };
  const room = avail - (widths.__more || 90);
  const shown = [];
  let used = 0;
  for (const i of items) {
    if (used + w(i) > room) break;
    shown.push(i);
    used += w(i);
  }
  const active = items.find((i) => i.id === currentId);
  if (active && !shown.includes(active)) {
    while (shown.length && used + w(active) > room) used -= w(shown.pop());
    shown.push(active);
  }
  return { shown, extra: items.filter((i) => !shown.includes(i)) };
}
