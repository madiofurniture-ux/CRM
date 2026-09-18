// Feature flags for the frontend. Reversible on purpose: flip a boolean (or
// set the matching REACT_APP_* env var at build time) to restore behavior —
// nothing gated by a flag is ever deleted.

// UI shell theme. "baseplate" = the existing dark-header pill nav
// (components/Header.jsx) — the current production default, kept as the
// safe rollback. "light" = the new spacious light-blue-gray SaaS shell
// (components/light/LightAppShell.jsx) built from
// docs/LIGHT_THEME_MIGRATION_PLAN.md. Any other/unset value falls back to
// "baseplate" — changing the *production* default here would be a visible,
// unreviewed UX change shipped by an env var, so it stays opt-in.
const RAW_UI_THEME = (process.env.REACT_APP_UI_THEME || "").trim().toLowerCase();
export const UI_THEME = RAW_UI_THEME === "light" ? "light" : "baseplate";
export const IS_LIGHT_THEME = UI_THEME === "light";

// Legacy/non-core nav — kept default-off as the umbrella override: set
// REACT_APP_SHOW_LEGACY_MENUS=true (e.g. in frontend/.env) and restart the
// dev server / rebuild to restore everything at once, no code changes
// needed. See docs/GO_LIVE_V1_CHECKLIST.md "UI Cleanup" and
// frontend/src/lib/baseplateNav.js. The per-module flags below are the
// supported way to turn a verified module back on individually instead.
export const SHOW_LEGACY_MENUS = process.env.REACT_APP_SHOW_LEGACY_MENUS === "true";

// Per-module override: REACT_APP_SHOW_<NAME>=true/false wins over
// `defaultOn`; unset falls back to `defaultOn`.
//
// `defaultOn` is GO-LIVE OFF for every module below: the v1 launch scope is
// CRM (Leads/Opportunities/Accounts & Contacts/Quotations), HR (Attendance/
// Payroll), Admin (Users/Brands) only — see docs/GO_LIVE_V1_CHECKLIST.md "UI
// Cleanup". Each module IS a verified, fully working vertical slice
// (frontend + live API + persistence + tenant/RBAC + backend tests — see
// docs/MODULE_READINESS_MATRIX.md for the evidence), so this is a nav
// decision, not a readiness gap — flip any one back to `true` (or set its
// REACT_APP_SHOW_* env var) the moment it's wanted back in v1 scope.
function moduleFlag(name, defaultOn) {
  const raw = process.env[`REACT_APP_SHOW_${name}`];
  if (raw === "true") return true;
  if (raw === "false") return false;
  return defaultOn;
}

// Delivery (Projects, D&W Survey/BOQ, Outstanding) — outside v1 scope.
export const SHOW_DELIVERY = moduleFlag("DELIVERY", false);

// Inventory (Stock, Stock Ledger, Purchasing) — outside v1 scope.
export const SHOW_INVENTORY = moduleFlag("INVENTORY", false);

// Finance (Tax Invoices, Petty Cash, Cashbooks, Project P&L, Payments) —
// outside v1 scope (distinct from HR Payroll, which stays visible).
export const SHOW_FINANCE = moduleFlag("FINANCE", false);

// Reports / Executive Analytics — "advanced analytics", outside v1 scope.
export const SHOW_REPORTS = moduleFlag("REPORTS", false);

// Record Chain — outside v1 scope.
export const SHOW_RECORD_CHAIN = moduleFlag("RECORD_CHAIN", false);

// Incentives — outside v1 scope (also removes the People-tab duplicate
// entry added alongside its original Finance-tab one).
export const SHOW_INCENTIVES = moduleFlag("INCENTIVES", false);

// Budgets (backend-only: backend/api_budget.py/models_budget.py, 14 tests,
// prompt_3_budgets.md) — NO frontend page exists yet. Stays off until
// docs/SCREEN_API_MODEL_MATRIX.md's "smallest implementation" (a read-only
// Budgets.jsx) is built — the flag exists now so nav wiring is ready.
export const SHOW_BUDGETS = moduleFlag("BUDGETS", false);

// Wallets (backend-only: backend/api_wallets.py/models_wallet.py, 10 tests,
// prompt_1_wallets.md) — NO frontend page exists yet, AND its Cashbook/
// PettyCash overlap (docs/WALLETS_DESIGN.md) is unresolved: exposing it
// today would show a second, disagreeing cash-in-hand figure next to
// Cashbook/Petty Cash. Stays off until both the UI is built and that
// overlap is resolved.
export const SHOW_WALLETS = moduleFlag("WALLETS", false);
