<!-- Generated: 2026-08-26 | Files scanned: ~45 | Token estimate: ~500 -->
# Frontend — MADIO CRM SPA

React 19, bootstrapped via CRACO (`frontend/craco.config.js`), routed with
react-router-dom v7. shadcn/ui + Radix primitives for components, Tailwind
for styling, axios for API calls, recharts for charts, react-hook-form + zod
for forms.

## Entry & routing
`frontend/src/index.js` -> `App.js` (`frontend/src/App.js`) mounts
`BrowserRouter` and declares every route. All routes except `/login` are
wrapped in `<ProtectedRoute page="..."><Layout>...</Layout></ProtectedRoute>`.

## Page tree (path -> ProtectedRoute page key -> component)
```
/login                        Login.jsx
/                    dashboard      Dashboard.jsx
/pipeline            pipeline       Pipeline.jsx
/quotes              quotes         Quotes.jsx
/quotes/ws/:id       quotes         QuoteWorkspace.jsx
/sales               sales          Sales.jsx
/visitors            visitors       Visitors.jsx
/leads               leads          Leads.jsx
/architects          architects     Architects.jsx
/inventory           inventory      Inventory.jsx
/inventory/analytics inv-analytics  InventoryAnalytics.jsx
/tasks               tasks          Tasks.jsx
/projects            projects       Projects.jsx
/attendance          attendance     Attendance.jsx
/admin/roles         roles          RoleManager.jsx
/outstanding         outstanding    Outstanding.jsx
/invoices            invoice-gen    Invoices.jsx
/petty-cash          petty          PettyCash.jsx
/meets               meetplan       Meets.jsx
/reports             reports        Reports.jsx
/alerts              alerts         Alerts.jsx
/dw-survey           dwsurvey       DWSurvey.jsx
/stock-ledger        stock-ledger   StockLedger.jsx
/data-centre         data-centre    DataCentre.jsx
/admin/financial-year financial-year FinancialYear.jsx
/admin/workflows     workflows      Workflows.jsx
```
`ProtectedRoute`'s `page` prop is checked against the signed-in user's role
permissions (fetched via `/api/auth/roles` / `/api/auth/me`) before rendering.

## Shared components (`frontend/src/components/`)
- `Layout.jsx`, `Sidebar.jsx`, `Topbar.jsx` — app chrome, wraps every
  protected page.
- `ProtectedRoute.jsx` — auth + role gate.
- `KpiCard.jsx`, `StageBadge.jsx`, `FilterChips.jsx`, `JourneyDrawer.jsx` —
  reused across Dashboard/Pipeline/Leads-style list pages.
- `components/ui/` — shadcn primitives (button, dialog, table, etc.).

## State & data access
- `context/AuthContext.jsx` — JWT/session, current user, permissions.
- `context/SidebarContext.jsx` — sidebar collapse state.
- `lib/api.js` — axios instance, base URL, attaches JWT bearer header.
- `lib/constants.js`, `lib/format.js`, `lib/image.js`, `lib/nav.js`,
  `lib/utils.js` — no global state library (no Redux/Zustand); pages fetch
  via `lib/api.js` directly and hold data in local component state.

## Known gotcha (fixed, keep pattern in mind)
Commit `a0ca265` fixed a duplicate-record bug that affected **every page with
a save form** — a shared submit-handling pattern, so a future bug in one
form's submit logic is worth checking against sibling pages, not just the one
reported.
