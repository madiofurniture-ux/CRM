# MADIO CRM — Project Context

## Business
MADIO Group, Hyderabad (showroom: Kondapur). Three divisions:
- Furniture
- MAP (Madio Architectural Cluster, texture/acrylic paints)
- Doors & Windows (D&W)

All three follow the same workflow. MADIO sells and manages; manufacturing/
delivery partners (vendors) fulfil orders on MADIO's behalf.

## Roadmap
1. Go live for MADIO Group (tenant 1)
2. Onboard partner's interior design firm (tenant 2)
3. Commercialise as a multi-tenant SaaS product

## Stack and repo state (read before starting any task)
- **System of record:** Python (FastAPI) backend + MongoDB, React frontend.
  Multi-tenancy is built in `backend/tenancy.py`.
- Layout: `backend/` (FastAPI, deployed to Render via `render.yaml`),
  `frontend/` (React/CRA + craco + Tailwind, deployed to Netlify via
  `netlify.toml`), `docs/` (PRD, module architecture, Mongo indexes, go-live
  checklist).
- History: commit `bc0af67` accidentally deleted the web stack from `main`; it
  was restored unchanged from `c04a55a` on `claude/madio-crm-context-q7nc4m`.
- `app/` is a separate Kotlin / Jetpack Compose Android scaffold (package
  `com.example.madiocrm`). Its `CrmRepository.kt` is in-memory only: no
  backend, persistence or tenancy yet. Don't treat it as the product.
- Configurable per-entity workflows: `backend/tenancy.py` (stage schema,
  defaults), `backend/workflow_rules.py` (transition checks + automations),
  `frontend/src/pages/Workflows.jsx` (builder), `frontend/src/hooks/useWorkflow.js`
  and `frontend/src/components/StagePath.jsx` (record-level Path). See
  `docs/WORKFLOWS.md`.
- Call Log (`calls` collection, `frontend/src/pages/Calls.jsx`) and the
  Analytics hub (`backend/analytics.py`, `GET /api/analytics/hub/{tab}`,
  `frontend/src/pages/Analytics.jsx`), and the division Sales Tracker
  (`GET /api/analytics/tracker`, `analytics.division_tracker`,
  `frontend/src/pages/SalesTracker.jsx`). See `docs/ANALYTICS_AND_CALLS.md`.
- Finance: money requests (`backend/expenses.py`,
  `frontend/src/pages/MoneyRequests.jsx`) paid out of Cashbook wallets;
  visitor-to-profit lineage, Deal P&L and Company P&L
  (`backend/finance_lineage.py`, `frontend/src/pages/ProfitLoss.jsx`). Petty
  Cash is read-only history. See `docs/FINANCE.md`.
- Flows (tenant-built automations: triggers incl. scheduled, conditions,
  multi-step actions, waits, run log): `backend/flows.py`, "Flows" section of
  `server.py`, `frontend/src/pages/Flows.jsx`. See `docs/FLOWS.md`.
- New module ids must also go in `MODULES_ADDED_AFTER_TRACKING` in
  `server.py` (tenants with a saved module list then see them switched on).
- Delivery go-live (`backend/operations.py`, routes in server.py's "Delivery
  go-live" block, tests in `tests/test_delivery_golive.py`):
  division-specific project checklists stored in `projects.milestones`
  (Furniture / D&W / MAP each have their own stage list; "Production" and
  "Installation"/"Application" names feed the customer journey), project
  costing + payment status (`PUT /projects/{id}/costing`), service & warranty
  tickets (`service_tickets`), Furniture/MAP site surveys (`site_surveys`; D&W
  keeps `dw_surveys`), the follow-up engine (`GET /followups/summary`) and
  project / customer 360 (`/projects/{id}/summary`, `/customers/{id}/overview`).
  These ride the existing `projects`/`leads`/`customers` permissions — nav items
  use `perm:` in `frontend/src/lib/nav.js` — so no account needs re-granting.
  Uploaded files are private: served only by `GET /api/documents/{id}/file`.
- Tally ← CRM refresh: `tools/tally_connector/` (runs on the office Tally PC,
  reads Tally's XML server, posts to `POST /api/tally/ingest` with a per-tenant
  connector key), `backend/tally_import.py` (validation/matching), "Tally →
  CRM" block in `server.py`. CRM inventory `qty` is the stock of record; Tally
  stock sits beside it as `tally_qty`. Tally invoices are read-only
  (`source="tally"`). See `docs/TALLY_CONNECTOR.md`.
- Inventory link: `GET /inventory/lookup` (product picker); quote lines carry
  `sku`; sales reserve stock, issued invoices issue it, cancelled ones return
  it; every movement goes through `_post_stock_move`, which keeps item `qty`
  in step.
- File storage: `backend/storage.py`, `STORAGE_BACKEND=local|s3|sharepoint`.
  SharePoint goes through Microsoft Graph (app registration, client
  credentials) into `Documents/<SHAREPOINT_FOLDER>/<tenant>/<entity>/`
  (MADIO: `CRM Images and content`); setup in
  `docs/SHAREPOINT.md`, check with `GET /api/admin/storage/status`.

- Go-live data load: Admin → Go-live Data (`/admin/go-live`) reads MADIO's
  spreadsheets (`backend/go_live_import.py`), previews, then archives and
  replaces the company's business data (undoable; `data_resets`,
  `data_reset_archive`) and can add starter flows. See `docs/GO_LIVE_DATA.md`.
  The Receipts & Payments monthly sheets load as Cashbook wallets/entries
  (`_cash_books`; `pnl_exclude` marks transfers and PO-covered vendor
  payments). P&L is stated before GST (`lc.net_of_gst`, `po_net`, `mo_net`;
  sales carry `tax_total`). See `docs/FINANCE.md`.
- Furniture quotes can print as a picture price list (`quote.print_layout =
  "pricelist"`, line `mrp` before GST beside the offer rate).
- Connected records: every record carries `customer_id` (and `project_id`
  where it applies), kept right by `backend/relations.py` (`link` on every
  save and conversion, `propagate_customer` for live copies, `backfill` once).
  Quotations/orders/invoices/payments keep a snapshot of name/phone. Customer
  and project pages (`/customers/:id`, `/projects/:id`, `GET
  /customers|projects/{id}/context`), `CustomerProjectPicker`, and per-column
  list filters (`useColumnFilters` + `ColumnFilters`). See
  `docs/CONNECTED_RECORDS.md`.
- People and partners: each staff member has their own login; seeded role
  logins carry `shared_login` and are left out of staff pickers
  (`StaffPicker`, "Handled by / Assigned to"). Vendors have `vendor_type`
  (Supplier / Applicator / Manufacturer; Master Data); projects carry a
  partner (`partner_id`, role Applicator for MAP else Supplier). Supplier
  names stay admin/accounting-only; applicator names are shown.
- Pricing: landing price (`cost`) is visible to admin, accountant and users
  with `can_view_cost` (Role Manager — e.g. the Furniture Manager), gated in
  `_can_see_cost_prices`. Stock items carry quantity price breaks
  (`price_tiers` [{min_qty, price}], MRP basis); quotation/invoice lines
  picked from stock (`price_auto`) take the break for their qty
  (`lc.tier_price`, server-side); a typed rate turns it off.
- Starter flows switch on once at startup for a company with none
  (`go_live_auto_starter_flows`, run key `starter-flows-1`).
- UI shell: Salesforce Lightning-style by default (`components/lightning/*`:
  global header with search + reminders, App Launcher, app tabs from
  `lib/apps.js`; `Topbar` renders a page header with the object's icon
  tile). `REACT_APP_UI_SHELL=sidebar` restores the left-sidebar shell.
- Master data lists: `PICKLISTS` in server.py (lead sources, project types,
  task categories, service types, architect types, D&W opening types /
  frames / glass / hardware finishes, stock categories, units), stored per
  company in `settings` key `picklists`, edited in Master Data → Lists
  (`PUT /picklists/{key}`, admin), read with `usePicklists` /
  `PicklistSelect`. Saves are checked (`_check_picklists`, map
  `PICKLIST_FIELDS`); unchanged old values are never re-checked; an empty
  list accepts anything. Project architect is picked from Architects
  (`ArchitectPicker`, `architect_id`).
- Reminders: tasks carry `due_time` + `remind_minutes`, meetings
  `remind_minutes` (default 15); `GET /reminders` lists the signed-in
  person's timed tasks/meetings (yesterday–tomorrow) and `ReminderCenter`
  pops them up on any screen (snooze/dismiss kept per browser; optional
  desktop notifications).

## Core rules (never break)
- Every document carries `tenant_id` (the company/tenant) and `division`.
  The codebase uses `tenant_id`, not `company_id`. Don't introduce a second name.
- Every query is tenant-scoped. In the backend, go through the single
  chokepoint `tenancy.scope(query, collection, user)` for reads and
  `tenancy.stamp(doc, collection, user)` for writes. New tenant data
  collections must be added to `TENANT_COLLECTIONS`.
- The tenant comes from the authenticated user record, never from a header or
  client-editable claim. Fail closed: no tenant means match nothing.
- No cross-tenant reads, ever.
- One codebase. Divisions and tenants are configuration, not forks.
- Quotation is ONE engine with per-division templates (`quotation_templates.py`);
  only the formats differ. Division presets (`division_preset(tenant, division)`:
  layout, mm/ft lines, rounding, GST, standard terms, highlights, bank, logo in
  `backend/assets/brand/<tenant>/`) drive the workspace and the branded PDF
  (`backend/quote_pdf.py`, `GET /quotes/{id}/pdf`). Quote Builder quotes
  (sections, no lines) print in the same branded format (`layout="builder"`);
  workspace lines carry `group` (printed with subtotals) and `image_url`
  (typology / product picture).
- Don't rename or restructure modules outside the task's scope.

## End-to-end flow (the spine)
Visitor → Lead → Quotation → Sales Order → Vendor PO → Vendor Delivery
→ Project Execution/Installation → Customer Payment Closed

## Supporting modules
Finance (customer receipts, vendor payments, ledger), Attendance.

## Vendor module (critical)
- Vendor partners master (per division), collection `vendors`
- Vendor PO linked to a Sales Order (one SO can have multiple POs), collection
  `purchase_orders`
- PO status: Raised → Confirmed → In Production → Dispatched → Delivered → Installed
  (vendor orders are `manufacturer_orders`: Quoted → … → Installed, with
  `promised_date` / `delivered_date`, stamped on first Delivered)
- Vendor payments against a PO: amount, date, mode, reference
- Per PO: value, paid, balance, promised vs actual delivery date
- Per SO: sale value − total PO cost = gross margin

## Dates
Business dates are IST: the server sets `TZ=Asia/Kolkata` at import
(`date.today()`), the frontend uses `todayIST()` / `isoDateIST()` from
`lib/format.js` — never `new Date().toISOString().slice(0, 10)` (UTC: it gives
yesterday until 05:30 IST). Timestamps stay UTC (`now_iso`).

## Working rules for Claude Code
- One task per session. Plan first, then implement, then test, then commit.
- Small commits with clear messages.
- If a change touches more than one module, stop and list the impact before editing.
- Backend tests: `python -m pytest tests -q` from `backend/` (Mongo is faked
  with `mongomock_motor`; install it alongside `requirements.txt`).
- Frontend check: `CI=true npm run build` from `frontend/`.
