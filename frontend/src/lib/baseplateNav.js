// Sub-nav content for every Baseplate primary pill, keyed by tab id.
// Every `to` is copied from an actual <Route path> in App.js — not invented.
export const BASEPLATE_SUBNAV = {
  overview: [
    { code: "DA", label: "Dashboard", to: "/" },
    { code: "AL", label: "Alerts", to: "/alerts" },
    { code: "RP", label: "Reports", to: "/reports" },
    { code: "EX", label: "Executive Analytics", to: "/executive" },
  ],
  sales: [
    { code: "PI", label: "Pipeline", to: "/pipeline" },
    { code: "LD", label: "Leads", to: "/leads" },
    { code: "RQ", label: "Requirements", to: "/requirements" },
    { code: "CF", label: "Configurator", to: "/configurator" },
    { code: "QT", label: "Quotations", to: "/quotes", isNew: true },
    { code: "QB", label: "Quote Builder", to: "/quotes/builder" },
    { code: "FU", label: "Follow-ups", to: "/quotes/followups" },
    { code: "SR", label: "Sales register", to: "/sales" },
    { code: "VI", label: "Visitors", to: "/visitors" },
  ],
  clients: [
    { code: "CU", label: "Customers", to: "/customers" },
    { code: "AR", label: "Architects", to: "/architects" },
    { code: "MP", label: "Meet Planner", to: "/meets" },
  ],
  delivery: [
    { code: "PR", label: "Projects", to: "/projects" },
    { code: "DW", label: "D&W Survey", to: "/dw-survey" },
    { code: "OS", label: "Outstanding", to: "/outstanding" },
  ],
  inventory: [
    { code: "ST", label: "Stock", to: "/inventory" },
    { code: "SL", label: "Stock Ledger", to: "/stock-ledger" },
    { code: "IA", label: "Inv. Analytics", to: "/inventory/analytics" },
    { code: "PO", label: "Purchase Orders", to: "/purchase-orders" },
    { code: "MO", label: "Manufacturer Orders", to: "/manufacturer-orders" },
  ],
  finance: [
    { code: "TI", label: "Tax Invoices", to: "/invoices" },
    { code: "PC", label: "Petty Cash", to: "/petty-cash" },
    { code: "CB", label: "Cashbooks", to: "/cashbook" },
    { code: "TS", label: "Cashbook & Tally Sync", to: "/finance/tally" },
    { code: "PL", label: "Project P&L", to: "/reports/project-pnl" },
    { code: "IN", label: "Incentives", to: "/incentives" },
    { code: "PY", label: "Payments", to: "/payments" },
  ],
  people: [
    { code: "TK", label: "Tasks", to: "/tasks" },
    { code: "DP", label: "Daily Planner", to: "/daily-planner" },
    { code: "AT", label: "Attendance", to: "/attendance" },
    { code: "TM", label: "Team & Access", to: "/admin/teams" },
    { code: "US", label: "Users", to: "/admin/roles" },
  ],
  control: [
    { code: "DC", label: "Data Centre", to: "/data-centre" },
    { code: "DH", label: "Data Health", to: "/admin/data-health" },
    { code: "FY", label: "Financial Year", to: "/admin/financial-year" },
    { code: "WF", label: "Workflows", to: "/admin/workflows" },
    { code: "BS", label: "Business Settings", to: "/admin/business" },
    { code: "CX", label: "Custom Fields", to: "/admin/custom-fields" },
    { code: "RP2", label: "Roles & Permissions", to: "/admin/roles-permissions" },
    { code: "AU", label: "Audit Trail", to: "/audit" },
    { code: "RC", label: "Record Chain", to: "/record-chain" },
    { code: "TB", label: "Team Board", to: "/discussions" },
  ],
  product: [
    { code: "MD", label: "Master Data", to: "/admin/master-data" },
  ],
};

export const BASEPLATE_TABS = [
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

// Which tab a given pathname belongs to, so the header highlights the right
// pill/sub-item on a hard refresh or a link followed from outside the header.
export function tabForPath(pathname) {
  for (const [tab, items] of Object.entries(BASEPLATE_SUBNAV)) {
    if (items.some((i) => i.to === pathname)) return tab;
  }
  return "overview";
}
