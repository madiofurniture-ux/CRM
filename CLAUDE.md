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
  `frontend/src/pages/Analytics.jsx`). See `docs/ANALYTICS_AND_CALLS.md`.
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
  (`backend/quote_pdf.py`, `GET /quotes/{id}/pdf`).
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
- Vendor payments against a PO: amount, date, mode, reference
- Per PO: value, paid, balance, promised vs actual delivery date
- Per SO: sale value − total PO cost = gross margin

## Working rules for Claude Code
- One task per session. Plan first, then implement, then test, then commit.
- Small commits with clear messages.
- If a change touches more than one module, stop and list the impact before editing.
- Backend tests: `python -m pytest tests -q` from `backend/` (Mongo is faked
  with `mongomock_motor`; install it alongside `requirements.txt`).
- Frontend check: `CI=true npm run build` from `frontend/`.
