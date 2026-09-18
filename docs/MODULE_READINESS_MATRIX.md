# Module Readiness Matrix

Classification legend: **COMPLETE** (frontend + live API + persistence +
tenant/RBAC + tests + nav-visible today) · **HIDDEN_READY** (same as
COMPLETE but nav-gated off, usually by `SHOW_LEGACY_MENUS`) · **PARTIAL**
· **BACKEND_ONLY** · **UI_ONLY** · **MOCK_OR_STATIC** · **MISSING**.

Evidence for every row: `frontend/src/App.js` routes, `frontend/src/lib/
baseplateNav.js`, the page component's own `api.*` calls, `backend/
server.py`/`api_*.py` route definitions, `backend/models*.py`, `backend/
permissions.py` module grants, and `backend/tests/` filenames. This is a
route/file/test-presence audit, not a full per-endpoint functional QA pass
— see `docs/SCREEN_API_MODEL_MATRIX.md` for the exact file/route list
behind each row.

## Overview

| Module | Status | Notes |
|---|---|---|
| Command centre | **COMPLETE** | `CommandCentre.jsx` at `/`, `test_command_centre_overview.py`, visible today. |
| Reports | **HIDDEN_READY** | `Reports.jsx` → real `GET /reports`, route `/reports` exists in `App.js`, but nav item code `RP` is in `LEGACY_ITEM_CODES` — hidden even though "overview" isn't a legacy tab. |
| Record Chain | **HIDDEN_READY** | `RecordChain.jsx` → real `GET /journey/:phone`, route exists, nav code `RC` is legacy-hidden (lives under the "control" tab's subnav, not overview). |

## Sales

| Module | Status | Notes |
|---|---|---|
| Pipeline | **COMPLETE** | `Pipeline.jsx`, route `/pipeline`, visible. |
| Leads | **COMPLETE** | `Leads.jsx`, `module="leads"` RBAC, `test_leads.py`. |
| Quotations | **COMPLETE** | `Quotes.jsx`/`QuoteBuilder.jsx`/`QuoteWorkspace.jsx`, `module="quotes"`, `test_quote_builder.py`. |
| Sales Register | **COMPLETE** | `Sales.jsx`, `module="sales"`, visible. No dedicated `test_sales.py`; covered indirectly via `test_split_payments.py`/`test_enterprise_crm.py`. |
| Visitors | **COMPLETE** | `Visitors.jsx`, `module="visitors"`, `test_visitor_customer_linkage.py`. |

## Clients

| Module | Status | Notes |
|---|---|---|
| Customers | **COMPLETE** | `Customers.jsx`, `module="customers"`. |
| Architects Channel | **COMPLETE** | `Architects.jsx`, `module="architects"`. |
| Vendors | **BACKEND_ONLY** | Full CRUD exists (`make_crud(api, "vendors", "vendors", VendorCreate, Vendor, ...)` in `backend/server.py:1546`, no `module=` RBAC gate, no dedicated test file) — but there is no `Vendors.jsx`/route/nav entry at all, so a vendor today can only be created via API/seed, never through the UI. |

## Delivery

| Module | Status | Notes |
|---|---|---|
| Projects | **HIDDEN_READY** | `Projects.jsx`, route `/projects`, `test_project_tracking.py`+`test_project_pnl.py`, but the whole "delivery" tab is in `LEGACY_TABS`. |
| Survey/BOQ | **HIDDEN_READY** | `DWSurvey.jsx`, route `/dw-survey`, covered by `test_project_tracking.py`. Same tab, same gate. |
| Production | **MISSING** | No production-stage entity/page. `ProjectBase.stage` (Survey/Quoted/Execution/Review/Closure) is the closest proxy but isn't a dedicated production-tracking slice (no BOM consumption, no shop-floor status). |
| Installation | **PARTIAL** | No dedicated installation entity/page either — `ProjectBase.stage` again the only proxy (no install-date/checklist/photo-evidence fields). |
| Service Warranty | **MISSING** | No warranty entity, no claims workflow, no page. |

## Inventory

| Module | Status | Notes |
|---|---|---|
| Stock | **HIDDEN_READY** | `Inventory.jsx` + `InventoryAnalytics.jsx`, `module="inventory"` RBAC (the only `_require_permission`-gated module besides HR/wallets/budgets today), route `/inventory`. Tab is legacy-hidden. |
| Stock Ledger | **HIDDEN_READY** | `StockLedger.jsx`, route `/stock-ledger`, 6 live `api.*` calls. Same gate. |
| Purchasing | **HIDDEN_READY** | `PurchaseOrders.jsx` + `ManufacturerOrders.jsx`, `test_purchase_orders.py` + `test_manufacturer_orders.py`. Same gate. |

## Finance

| Module | Status | Notes |
|---|---|---|
| Tax Invoices | **HIDDEN_READY** | `Invoices.jsx`, `module="invoice-gen"`, `test_invoice_gst.py`. |
| Outstanding Ageing | **HIDDEN_READY** | `Outstanding.jsx`, route `/outstanding`, real API — but nav-classified under the **Delivery** subnav in `baseplateNav.js`, not Finance (mismatch vs. this prompt's grouping; still gated by the same `LEGACY_TABS`). |
| Petty Cash | **HIDDEN_READY** | `PettyCash.jsx`, `module="petty"`, `test_petty_cash.py` — plus this engagement's `test_wallets.py`/`test_budgets.py` extend the same posting path (see Budgets/Wallets below). |
| Profit & Loss | **PARTIAL** | `ProjectPnL.jsx` (`/reports/project-pnl`, `test_project_pnl.py`) covers **per-project** P&L only. No company-wide/period P&L statement page or endpoint exists. |
| Financial Year Close | **COMPLETE** | `FinancialYear.jsx`, route `/admin/financial-year`, lives under the **Control** tab (not a legacy tab) — already visible today, admin-gated only. |

## People

| Module | Status | Notes |
|---|---|---|
| Attendance | **COMPLETE** | `Attendance.jsx`, `module="attendance"`, `test_geofence_attendance.py`, `test_attendance_payroll*.py`. |
| Leaves | **BACKEND_ONLY** | `backend/api_hr.py`'s `/api/v1/leave` (create/list/status, RBAC via `_can_hr(..., "leave", ...)`), `LeaveRequestCreate`/`models_hr.py`, covered by `test_hr_payroll.py`/`test_attendance_payroll_link.py`. **No frontend page or route at all.** |
| Incentives | **HIDDEN_READY** | `Incentives.jsx`, route `/incentives`, real API, covered indirectly (`test_enterprise_crm.py`, `test_unified_lifecycle.py`'s commission/provisioning tests) — but its only nav entry (`baseplateNav.js` code `IN`) lives under the **Finance** subnav, which is a legacy-hidden tab, even though the prompt groups Incentives under People. Reachable by direct URL only today. |
| Incentive Ledger | **PARTIAL** | Per `backend/api_hr.py`'s own comment, ledger-style detail is deliberately folded into the existing commission pipeline ("per docs/FEATURE_ROADMAP.md Phase 4 rather than a parallel IncentiveLedger") — there is no separate ledger entity/page, by design, not by omission. If a dedicated running-ledger view is wanted, it reads from the existing `commission_payouts` collection rather than a new model. |
| Payroll | **COMPLETE** | `PayrollPage.jsx`, route `/people/payroll`, `module` gate via `api_hr.py`'s own RBAC, `test_hr_payroll.py`/`test_payroll_calculation.py`/`test_attendance_payroll_link.py`. |
| Groups | **PARTIAL** | No page literally named "Groups" — `Teams.jsx` ("Team & Access", admin-only, `/admin/teams`) is the equivalent entity (`TeamBase`/`Team` in `models.py`). Naming mismatch only. |
| Tasks | **COMPLETE** | `Tasks.jsx`, `module="tasks"`. |
| Meet Planner | **COMPLETE** | `Meets.jsx`, `module="meetplan"`, route `/meets`. |

## Control

| Module | Status | Notes |
|---|---|---|
| Users | **COMPLETE** | `RoleManager.jsx`, route `/admin/roles`. |
| Roles & Permissions | **COMPLETE** | `RolesPermissions.jsx`, route `/admin/roles-permissions`, backs onto `permissions.py`, `test_permissions.py`. |
| Workflow Engine | **COMPLETE** | `Workflows.jsx`, route `/admin/workflows`, backs onto `tenancy.py`'s per-tenant workflow stages, `test_tenancy.py`. |
| Audit Trail | **COMPLETE** | `AuditTrail.jsx`, route `/audit`, backs onto `server.py`'s `record_activity`/`/activities`. |
| Documents | **BACKEND_ONLY** | `backend/server.py`'s `POST/GET /documents` exist, `test_documents.py` exists — **no frontend page**. |
| Data Centre | **COMPLETE** | `DataCentre.jsx`, route `/data-centre`, plus `DataHealth.jsx` (`/admin/data-health`, `test_data_health.py`). |
| Settings | **COMPLETE** | `BusinessSettings.jsx`, route `/admin/business` (branding + enabled modules), `test_business_profile.py`. Also `CustomFields.jsx` (`/admin/custom-fields`, `test_custom_fields.py`). |

## Product

| Module | Status | Notes |
|---|---|---|
| Installs Console | **MISSING** | No entity, no page. Doesn't apply to a single-tenant-per-deploy CRM as currently architected. |
| Provisioning | **MISSING** | Same — "provisioning" in this codebase means deal-won project/commission provisioning (`test_unified_lifecycle.py`'s `test_deal_won_provisioning_is_idempotent_on_retry`), not tenant/SaaS provisioning. |
| Plans/Billing | **MISSING** | No billing/plan/subscription entity anywhere in `models*.py`. |
| Module Toggles | **PARTIAL** | `BusinessSettings.jsx` ("Branding and which modules this business uses") is the closest thing — per-tenant `enabled_modules` config exists (`backend/server.py` "Entity/branding config layered onto a tenant doc"), but there is no dedicated "Module Toggles" screen separate from Business Settings, and it isn't the same mechanism as this session's requested `SHOW_*` frontend build-time flags. |
| Branding | **COMPLETE** | Same `BusinessSettings.jsx` — branding fields are live and tested (`test_business_profile.py`). |
| Industry Presets | **MISSING** | No entity/page. `backend/modules/` (Lucente_kitchens, core_crm, madio_doors_windows, map_paints, navaki) is the closest concept — per-brand pipeline manifests loaded by `modules_loader.py` — but that's a deploy-time brand config, not a runtime "industry preset" picker. |
| Template Org | **MISSING** | No entity/page; "template org" only appears as static header copy in `Header.jsx`, not a real feature. |
| Custom Fields | **COMPLETE** | `CustomFields.jsx`, route `/admin/custom-fields`, `test_custom_fields.py`. |

## This engagement's own backend-only features (not in the prompt's list, but relevant)

| Module | Status | Notes |
|---|---|---|
| Wallets (`prompt_1_wallets.md`) | **BACKEND_ONLY** | `backend/api_wallets.py`/`models_wallet.py`, `test_wallets.py` (10 tests) — no frontend page, no nav entry. Posts automatically from every Petty Cash voucher; see `docs/WALLETS_DESIGN.md` for its documented overlap with Cashbook. |
| Budgets (`prompt_3_budgets.md`) | **BACKEND_ONLY** | `backend/api_budget.py`/`models_budget.py`, `test_budgets.py` (14 tests) — no frontend page, no nav entry. Wired into `normalize_petty_cash`/`purchase_order_approve`; see `docs/BUDGETS_DESIGN.md`. |

## Money-ledger ownership (per instruction: avoid duplicate ledgers / double-counting P&L)

Three systems now touch project cash position: **Cashbook**
(`CashbookBase`/`CashbookEntryBase`, feeds `csv_engine.compute_project_pnl`
— the real P&L), the **flat PettyCash ledger** (`PettyCashBase`, float
rupees), and **Wallets** (`models_wallet.py`, integer paise, posts
automatically from every PettyCash voucher). `docs/WALLETS_DESIGN.md`
already documents this and recommends picking one long-term system.
**Budgets adds a fourth read of the same PettyCash/PO events** (via
`apply_budget_transaction`) but does not feed P&L — it's a spend-ceiling
check, not a ledger, so it does not double-count. No change made here;
flagged for the same follow-up `WALLETS_DESIGN.md` already calls for.
