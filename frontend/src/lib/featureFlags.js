// Feature flags for the frontend. Reversible on purpose: flip a boolean (or
// set the matching REACT_APP_* env var at build time) to restore behavior —
// nothing gated by a flag is ever deleted.

// Legacy/non-core nav (Stock, Finance/Petty Cash, Delivery, Reports/
// Executive Analytics, Record Chain, Team Board) — hidden by default for the
// Madio Canonical CRM v1 launch scope: CRM (Leads/Opportunities/Accounts &
// Contacts/Quotations), HR (Attendance/Payroll), Admin (Users/Brands).
// See docs/GO_LIVE_V1_CHECKLIST.md "UI Cleanup" and frontend/src/lib/baseplateNav.js.
//
// To restore: set REACT_APP_SHOW_LEGACY_MENUS=true (e.g. in frontend/.env)
// and restart the dev server / rebuild — no code changes needed.
export const SHOW_LEGACY_MENUS = process.env.REACT_APP_SHOW_LEGACY_MENUS === "true";
