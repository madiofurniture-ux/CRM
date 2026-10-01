<!-- Updated: 2026-09-30 | Scanned: frontend/src/App.js, lib/, pages/, components/ -->
# Frontend: MADIO CRM SPA

React 19 on CRA + CRACO, react-router-dom v7, Tailwind + shadcn/ui (Radix),
axios, recharts, sonner toasts. There's no global store: pages fetch through
`lib/api.js` and keep data in component state.

## Entry, shell and theme
`index.js` → `App.js` declares every route. Everything except `/login` is
`<ProtectedRoute page="…"><Layout>…</Layout></ProtectedRoute>`.
`Layout.jsx` renders the **light (Salesforce Lightning-style) shell** by
default (`components/light/LightAppShell`, `LightSidebar`, `LightTopbar`), or
the older dark `Header.jsx` pill nav when `REACT_APP_UI_THEME=baseplate`.
Theme tokens are in `index.css` (`--color-*`, remapped legacy tokens under
`[data-ui-theme="light"]`).

## Navigation and access
- `lib/nav.js`: the single source of pages (`id` = permission/page key).
- `components/light/LightSidebar.jsx` groups nav ids into sections;
  `lib/baseplateNav.js` does the same for the older shell.
- `lib/featureFlags.js`: `UI_THEME`, and per-module menu flags
  `SHOW_DELIVERY/INVENTORY/FINANCE/REPORTS/…`. Finance is **on** by default.
- `context/AuthContext.jsx`: `canAccess(page)` (tenant `enabled_modules`,
  role grants, legacy `pages`) and `canDo(module, action)`. Add new gated
  modules to `GATED_MODULES` here and to `MODULES` in `RolesPermissions.jsx`.

## Page tree (path → page key → component), highlights
```
/                     dashboard     CommandCentre.jsx (overview)
/analytics            analytics     Analytics.jsx (Sales/Leads/Calls/Attendance/Vendors tabs)
/leads                leads         Leads.jsx (StagePath in the follow-up drawer)
/calls                calls         Calls.jsx (call log, convert to lead)
/pipeline             pipeline      Pipeline.jsx (columns + probability from the quote workflow)
/quotes, /quotes/ws/:id  quotes     Quotes.jsx, QuoteWorkspace.jsx
/sales                sales         Sales.jsx (WhatsApp button via source quotation's phone)
/visitors             visitors      Visitors.jsx
/projects             projects      Projects.jsx (StagePath + link to deal P&L)
/money-requests       expenses      MoneyRequests.jsx
/approvals            expenses      MoneyRequests.jsx ("Assigned to you" view)
/finance/pnl          pnl           ProfitLoss.jsx (Company P&L, Deals, deal lineage)
/cashbook             cashbook      Cashbook.jsx (wallets)
/reports/project-pnl  project-pnl   ProjectPnL.jsx
/petty-cash           petty         PettyCash.jsx (read-only history)
/admin/workflows      workflows     Workflows.jsx (stages, gates, automations builder)
/admin/flows          flows         Flows.jsx (flow builder, dry run, run log)
/admin/roles          roles         RoleManager.jsx (users, incl. "Reports to")
/discussions          discussions   Discussions.jsx (Team Board, polls every 15s)
```
Other pages (inventory, invoices, attendance, payroll, tasks, …) follow the
same pattern; `App.js` is the complete list.

## Shared building blocks
- `components/StagePath.jsx` + `hooks/useWorkflow.js`: Lightning-style stage
  bar driven by the tenant's workflow. Pages take stage lists and
  probabilities from `useWorkflow(entity, fallback)`, never from hardcoded
  arrays. Use `stageErrorMessage(err)` to show gate refusals.
- `Topbar.jsx`, `EmptyState.jsx`, `ErrorState.jsx` (`hint`, `onRetry`),
  `SearchSelect.jsx` (`options[{id,label,sub}]`), `StageBadge.jsx`,
  `KpiCard.jsx`, `JourneyDrawer.jsx`.
- `AttachmentPanel.jsx` (`/api/documents`) and `WhatsAppButton.jsx`
  (`lib/whatsapp.js`, templates from the backend so copy never drifts).
- `context/PrivacyModeContext.jsx`: `isOtherHidden` → send
  `mask_other=true` on P&L and wallet reads; `requestUnlock()` asks for the PIN.

## Data access conventions
- `lib/api.js`: axios with the bearer token, plus a **GET cache** (20s,
  stale-while-revalidate, keyed on the literal URL). Put query params in the
  URL string, not axios `params`. Pass `{ skipCache: true }` for
  must-be-fresh reads. Any POST/PUT/DELETE clears that resource's cache.
  `formatApiError(detail)` also reads `{message}` details.
- `lib/format.js`: `inr`, `inrFull`, `fmtDate`, `todayIST`/`isoDateIST`
  (IST day boundaries). `lib/image.js`: `shrinkImage` for photo uploads.

## Gotchas
- CI builds treat ESLint warnings as errors (`CI=true npm run build`): unused
  imports and `react-hooks/exhaustive-deps` fail the build.
- With Tailwind, `w-full` and `w-auto` on the same element conflict; keep a
  width-less base class for inline controls.
- Commit `a0ca265` fixed a duplicate-submit bug shared by every save form.
  Check sibling forms when one misbehaves.
