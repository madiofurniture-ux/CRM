# Screen ↔ API ↔ Model Matrix

Exact file/route mapping behind every row of `docs/MODULE_READINESS_MATRIX.md`,
plus — per instruction — for every non-COMPLETE item: exact files/routes,
smallest implementation, dependencies, whether it's safe to expose in nav,
and an acceptance test.

## Part 1 — COMPLETE / HIDDEN_READY screens (file → route → backend → model → test)

| Screen | Frontend file | Route | Backend route(s) | Model | Test file |
|---|---|---|---|---|---|
| Command centre | `pages/CommandCentre.jsx` | `/`, `/overview` | `GET /api/command-centre/overview` | n/a (aggregation) | `test_command_centre_overview.py` |
| Reports | `pages/Reports.jsx` | `/reports` | `GET /reports` | n/a (aggregation) | none dedicated |
| Record Chain | `pages/RecordChain.jsx` | `/record-chain` | `GET /journey/{phone}` | n/a (aggregation) | none dedicated |
| Pipeline | `pages/Pipeline.jsx` | `/pipeline` | `leads`/`sales` CRUD | `Lead`, `Sale` | `test_leads.py` |
| Leads | `pages/Leads.jsx` | `/leads` | `/leads` CRUD (`server.py:1642`) | `LeadCreate`/`Lead` (`models.py`) | `test_leads.py` |
| Quotations | `pages/Quotes.jsx`, `QuoteBuilder.jsx`, `QuoteWorkspace.jsx` | `/quotes`, `/quotes/builder[/:id]`, `/quotes/ws/:id` | `/quotes` CRUD (`server.py:1866`) | `Quote` | `test_quote_builder.py` |
| Sales Register | `pages/Sales.jsx` | `/sales` | `/sales` CRUD (`server.py:1868`) | `Sale` | indirect (`test_split_payments.py`) |
| Visitors | `pages/Visitors.jsx` | `/visitors` | `/visitors` CRUD (`server.py:1640`) | `Visitor` | `test_visitor_customer_linkage.py` |
| Customers | `pages/Customers.jsx` | `/customers` | `/customers` CRUD (`server.py:4230`) | `Customer` | via `test_visitor_customer_linkage.py` |
| Architects | `pages/Architects.jsx` | `/architects` | `/architects` CRUD (`server.py:1645`) | `Architect` | none dedicated |
| Projects | `pages/Projects.jsx` | `/projects` | project CRUD + `/projects/{id}/*` | `ProjectBase` (`models.py:1300`) | `test_project_tracking.py`, `test_project_pnl.py` |
| Survey/BOQ | `pages/DWSurvey.jsx` | `/dw-survey` | `dw-openings`/`dw_surveys` (`server.py:4225`) | `DWOpening` | `test_project_tracking.py` |
| Stock | `pages/Inventory.jsx`, `InventoryAnalytics.jsx` | `/inventory`, `/inventory/analytics` | `/inventory` CRUD (`server.py:1870`, `module="inventory"`) | `InventoryItem` | via `test_purchase_orders.py` stock movement checks |
| Stock Ledger | `pages/StockLedger.jsx` | `/stock-ledger` | `stock_movements` reads | movement docs | via `test_purchase_orders.py` |
| Purchasing | `pages/PurchaseOrders.jsx`, `ManufacturerOrders.jsx` | `/purchase-orders`, `/manufacturer-orders` | `/purchase-orders` CRUD + `/approve`/`/receive` (`server.py:2003-2087`), `/manufacturer-orders` (`server.py:2264`) | `PurchaseOrderBase`, `ManufacturerOrder` | `test_purchase_orders.py`, `test_manufacturer_orders.py` |
| Tax Invoices | `pages/Invoices.jsx` | `/invoices` | `/invoices` CRUD (`server.py:2364`) | `InvoiceBase` (`models.py:735`) | `test_invoice_gst.py` |
| Outstanding Ageing | `pages/Outstanding.jsx` | `/outstanding` | invoice/payment aggregation | n/a | none dedicated |
| Petty Cash | `pages/PettyCash.jsx` | `/petty-cash` | `/petty-cash` CRUD + `/approve` (`server.py:2473-2489`) | `PettyCashBase` | `test_petty_cash.py`, `test_wallets.py`, `test_budgets.py` |
| Project P&L | `pages/ProjectPnL.jsx` | `/reports/project-pnl` | `csv_engine.compute_project_pnl` route | n/a (aggregation) | `test_project_pnl.py` |
| Financial Year Close | `pages/FinancialYear.jsx` | `/admin/financial-year` | FY close routes (`server.py`, `stamp_closure`) | n/a | none dedicated |
| Attendance | `pages/Attendance.jsx` | `/attendance` | `/attendance` + `api_hr.py` HR routes | `HrAttendanceLog` | `test_geofence_attendance.py`, `test_attendance_payroll*.py` |
| Incentives | `pages/Incentives.jsx` | `/incentives` | commission routes | `CommissionRule`, `commission_payouts` | `test_enterprise_crm.py` |
| Payroll | `pages/PayrollPage.jsx` | `/people/payroll` | `api_hr.py` payroll routes | `PayrollPeriod` (`models_hr.py`) | `test_hr_payroll.py`, `test_payroll_calculation.py` |
| Tasks | `pages/Tasks.jsx` | `/tasks` | `/tasks` CRUD (`server.py:2362`) | `Task` | none dedicated |
| Meet Planner | `pages/Meets.jsx` | `/meets` | `/meets` CRUD (`server.py:2366`) | `Meet` | none dedicated |
| Users | `pages/RoleManager.jsx` | `/admin/roles` | user/role admin routes | `Role` | `test_permissions.py` |
| Roles & Permissions | `pages/RolesPermissions.jsx` | `/admin/roles-permissions` | `/roles` CRUD (`server.py:4354`) | `Role`, `permissions.py` | `test_permissions.py` |
| Workflow Engine | `pages/Workflows.jsx` | `/admin/workflows` | tenant workflow routes | `tenancy.py` stage defs | `test_tenancy.py` |
| Audit Trail | `pages/AuditTrail.jsx` | `/audit` | `GET /activities` (`server.py:4243`) | `activities` collection | none dedicated |
| Data Centre | `pages/DataCentre.jsx`, `DataHealth.jsx` | `/data-centre`, `/admin/data-health` | tenant admin routes | n/a | `test_data_health.py` |
| Settings / Branding | `pages/BusinessSettings.jsx` | `/admin/business` | tenant branding routes (`server.py:896-936`) | tenant doc | `test_business_profile.py` |
| Custom Fields | `pages/CustomFields.jsx` | `/admin/custom-fields` | custom-field-def routes | `custom_field_defs` | `test_custom_fields.py` |

## Part 2 — Remediation plan for every PARTIAL / BACKEND_ONLY / UI_ONLY / MISSING item

### Vendors — BACKEND_ONLY
- **Files/routes**: backend `make_crud(api, "vendors", "vendors", VendorCreate, Vendor, ...)` at `backend/server.py:1546`, model `VendorBase`/`Vendor` in `models.py`. No frontend file; would be `frontend/src/pages/Vendors.jsx` + a `/vendors` route in `App.js` + a Clients-tab subnav entry in `baseplateNav.js`.
- **Smallest implementation**: one CRUD list/create/edit page mirroring `Architects.jsx` (simplest existing analog — flat list, no nested tabs).
- **Dependencies**: none — API already exists and is unauthenticated-by-role (no `module=` gate) besides tenant/login.
- **Safe to expose**: yes, once built — read/write already tenant-scoped by `make_crud`'s default behavior.
- **Acceptance test**: `test_vendors.py` — create a vendor, list it back tenant-scoped, confirm a `PurchaseOrder.vendor_id` referencing it resolves `vendor_name`/`vendor_code` (existing `normalize_purchase_order` behavior).

### Production — MISSING
- **Files/routes**: none exist. Would need a new `production_stages` (or similar) collection, model, and API under a project, plus a `Production.jsx` page.
- **Smallest implementation**: NOT a new model — extend `ProjectBase.stage`/`ProjectBase.log` (already a `List[dict]` free-form event log) with a production-specific sub-view in `Projects.jsx` rather than a parallel entity, to avoid a second "where is this project's real status" source.
- **Dependencies**: a decision on what "production" needs to track beyond `stage`/`log` (BOM consumption? shop-floor assignment?) — out of scope to guess; needs a short spec.
- **Safe to expose**: no — not built.
- **Acceptance test**: none yet; write one alongside the spec.

### Installation — PARTIAL
- **Files/routes**: same proxy as Production — `ProjectBase.stage`/`.log`.
- **Smallest implementation**: an "Installation" sub-tab on `Projects.jsx` reading/writing `log` entries tagged `kind: "installation"` (the `log` schema already supports a `kind` field) — no backend change needed.
- **Dependencies**: none technical; needs UX sign-off on what an install checklist should capture.
- **Safe to expose**: the read-only version (surfacing existing `log` entries) is safe today; a write UI needs the small `kind` convention agreed first.
- **Acceptance test**: `test_project_tracking.py` extension — post a `kind="installation"` log entry, confirm it round-trips and doesn't collide with other log kinds.

### Service Warranty — MISSING
- **Files/routes**: none.
- **Smallest implementation**: new `ServiceWarranty`/`WarrantyClaim` model + `api_warranty.py` (own router, mounted like `api_wallets.py`) — this is a genuinely new entity, not a proxy of `ProjectBase`, since a warranty claim outlives project closure.
- **Dependencies**: needs its own prompt/spec (claim states, SLA, linkage to `project_id`/`customer`).
- **Safe to expose**: no — not built.
- **Acceptance test**: none yet.

### Profit & Loss (company-wide) — PARTIAL
- **Files/routes**: `ProjectPnL.jsx`/`csv_engine.compute_project_pnl` exist per-project only.
- **Smallest implementation**: a `GET /reports/pnl?period=` aggregation summing `compute_project_pnl` across all of a tenant's projects for a period — reuses the existing per-project function, no new model.
- **Dependencies**: none.
- **Safe to expose**: yes once built, same RBAC/tenancy the per-project version already has.
- **Acceptance test**: `test_project_pnl.py` extension — two projects with known P&L, confirm the company total is their sum.

### Leaves — BACKEND_ONLY
- **Files/routes**: `POST/GET /api/v1/leave`, `POST /api/v1/leave/{id}/status` in `backend/api_hr.py:122-160`. No frontend file; would be `frontend/src/pages/Leaves.jsx` + `/people/leaves` route + People-tab subnav entry.
- **Smallest implementation**: a list+request-leave form calling the existing endpoints directly — no backend change.
- **Dependencies**: none — RBAC (`_can_hr(..., "leave", ...)`) and tenancy already enforced server-side.
- **Safe to expose**: yes, once built.
- **Acceptance test**: `test_leaves_ui` (frontend) or reuse `test_hr_payroll.py`'s existing leave-request coverage as the backend half; add a curl smoke test (below).

### Incentive Ledger — PARTIAL (by design)
- **Files/routes**: `commission_payouts` collection, read via existing commission routes.
- **Smallest implementation**: if wanted, a read-only "Ledger" sub-view on `Incentives.jsx` listing `commission_payouts` chronologically — not a new model, per `api_hr.py`'s own comment against building a parallel `IncentiveLedger`.
- **Dependencies**: none.
- **Safe to expose**: yes.
- **Acceptance test**: extend `test_enterprise_crm.py`'s commission coverage to assert the ledger view's ordering/totals match `commission_payouts`.

### Groups (naming only) — PARTIAL
- **Files/routes**: `Teams.jsx` already is this feature.
- **Smallest implementation**: none needed — optionally rename the nav label "Team & Access" to "Groups" if that's the reference UI's exact vocabulary; cosmetic only.
- **Dependencies**: none.
- **Safe to expose**: already exposed (admin-only).
- **Acceptance test**: n/a (no behavior change).

### Documents — BACKEND_ONLY
- **Files/routes**: `POST/GET /documents` (`backend/server.py:5882,5910`), `test_documents.py`. No frontend file; would be `frontend/src/pages/Documents.jsx` + `/documents` route + Control-tab subnav entry.
- **Smallest implementation**: list+upload page mirroring the existing evidence-photo upload pattern already used elsewhere (e.g. `PettyCash.jsx`'s `receipt_url`).
- **Dependencies**: confirm `storage.py`'s upload path (already used elsewhere) is what `/documents` expects.
- **Safe to expose**: yes, once built.
- **Acceptance test**: `test_documents.py` already exists backend-side; add a frontend smoke test once the page exists.

### Module Toggles — PARTIAL
- **Files/routes**: folded into `BusinessSettings.jsx` today.
- **Smallest implementation**: none required unless the reference UI specifically wants a *separate* screen — otherwise this is already the feature under a different label.
- **Dependencies**: a decision on whether "Module Toggles" must be its own screen or can stay inside Settings.
- **Safe to expose**: already exposed.
- **Acceptance test**: n/a unless split out.

### Installs Console / Provisioning / Plans-Billing / Industry Presets / Template Org — MISSING
- **Files/routes**: none anywhere in the repo.
- **Smallest implementation**: **not attempted in this pass.** These are multi-tenant SaaS platform-admin concepts (installing the product for a new business, billing that business, picking an industry preset at signup) that don't exist in this single-tenant-per-deploy CRM's architecture. Building them is a new subsystem, not a vertical-slice gap-fill — needs its own PRD before implementation, not a reconciliation-pass guess.
- **Dependencies**: product decision on whether this CRM becomes a self-serve SaaS platform at all.
- **Safe to expose**: no.
- **Acceptance test**: none — out of scope for this pass.

### Wallets — BACKEND_ONLY
- **Files/routes**: `backend/api_wallets.py` (`/api/v1/wallets*`), `models_wallet.py`. No frontend file.
- **Smallest implementation**: a read-only `Wallets.jsx` (list wallets + transactions per project, mirroring `StockLedger.jsx`'s read-only ledger layout) — write actions (top-up/adjustment) are Division-Head-only per `docs/WALLETS_DESIGN.md` and can stay API-only initially.
- **Dependencies**: resolve the Cashbook/PettyCash/Wallet overlap noted in `WALLETS_DESIGN.md` before promoting this to a primary nav item, or it will show a second, disagreeing cash-in-hand number next to Cashbook/PettyCash.
- **Safe to expose**: not yet — flagged `SHOW_WALLETS=false` until the overlap decision is made (this pass adds the flag, wired off).
- **Acceptance test**: `test_wallets.py` already covers the backend (10 tests); add a frontend smoke test once built.

### Budgets — BACKEND_ONLY
- **Files/routes**: `backend/api_budget.py` (`/api/v1/budgets*`), `models_budget.py`. No frontend file.
- **Smallest implementation**: a read-only `Budgets.jsx` (list budgets + utilization bar per line, mirroring `Outstanding.jsx`'s aggregation-table layout) plus the override-approve action for Division Heads.
- **Dependencies**: none blocking (unlike Wallets, Budgets doesn't double-count an existing ledger — it's a spend-ceiling check).
- **Safe to expose**: yes once built — flagged `SHOW_BUDGETS=false` until then (this pass adds the flag, wired off).
- **Acceptance test**: `test_budgets.py` already covers the backend (14 tests); add a frontend smoke test once built.
