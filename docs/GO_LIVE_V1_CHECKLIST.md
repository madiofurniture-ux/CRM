# Go-Live Checklist — Canonical CRM v1

Working directory for every command below: `C:\Users\jagad\Projects\CRMNew`.

## Pre-Deploy

- [ ] Confirm the new files are present:
  ```
  Get-ChildItem backend\models_canonical.py, backend\api_canonical.py, backend\modules_loader.py
  Get-ChildItem backend\modules -Recurse -Filter manifest.json
  ```
- [ ] Sanity-check every manifest parses and merges cleanly:
  ```
  cd backend
  python -c "import modules_loader as ml; [print(b, ml.load_for_brand(b)['pipelines'].keys()) for b in ml.list_brands()]"
  ```
- [ ] Confirm the app still imports and both routers are mounted:
  ```
  python -c "import server; print(len(server.api.routes), len(server.api_canonical.router.routes))"
  ```
- [ ] Run the existing test suite — this change must not regress it:
  ```
  python -m pytest tests -q
  ```
- [ ] Create the new indexes from `docs/MONGO_INDEXES.md` against the target Mongo instance (staging first, always).

## Deploy

- [ ] Standard deploy path for this repo (no new dependencies were added — `requirements.txt`/`requirements-prod.txt` unchanged, `pydantic`/`fastapi`/`pymongo` already present).
- [ ] Restart the backend process (`modules_loader`'s manifest cache is per-process — a running process will not pick up a manifest edited after it started).

## Post-Deploy Smoke Test

```
# replace <TOKEN> with a real login token from POST /api/auth/login
curl -s https://<host>/api/v1/brands
curl -s -H "Authorization: Bearer <TOKEN>" "https://<host>/api/v1/leads?brand_id=madio_doors_windows"
curl -s -X POST -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"brand_id":"madio_doors_windows","name":"Smoke Test Lead","phone":"9999999999"}' \
  https://<host>/api/v1/leads
```
- [ ] `/api/v1/brands` returns `["madio_doors_windows","map_paints","navaki"]`.
- [ ] The created lead round-trips with `id`, `tenant_id`, `created_at`, `updated_at` populated.
- [ ] Existing `/api/*` routes (e.g. `/api/leads`, `/api/quotes`) still respond normally — this deploy must not have touched their behavior.

## Operator Checks — Multi-Tenancy and Brand Isolation

- [ ] **Brand isolation**: create a lead with `brand_id=madio_doors_windows`, then `GET /api/v1/leads?brand_id=map_paints` — it must NOT appear.
- [ ] **Unknown brand rejected**: `GET /api/v1/leads?brand_id=not_a_real_brand` must return `400`, never an empty-but-successful list (an unregistered brand silently returning "no results" would look like a working brand with zero data).
- [ ] **Tenant isolation** (unchanged mechanism, still worth re-checking after this deploy): a user from a different `tenant_id` must get `404` reading another tenant's lead by `id`, not the record.
- [ ] **Convert idempotency**: call `/leads/{id}/convert` twice on the same lead; the second call must return the same `opportunity_id` as the first, not create a second Opportunity.

## UI Cleanup

The Baseplate header nav (`frontend/src/lib/baseplateNav.js`, consumed by
`frontend/src/components/Header.jsx`) was trimmed to the Madio Canonical CRM
v1 scope — CRM (Leads/Opportunities/Accounts & Contacts/Quotations), HR
(Attendance/Payroll), Admin (Users/Brands) — behind a new feature flag,
`SHOW_LEGACY_MENUS` in `frontend/src/lib/featureFlags.js`. Nothing was
deleted: the full nav definitions still exist as `ALL_BASEPLATE_SUBNAV`/
`ALL_BASEPLATE_TABS` in the same file; `BASEPLATE_SUBNAV`/`BASEPLATE_TABS`
(what `Header.jsx` actually renders) are a filtered view over them.

**Hidden by default (`SHOW_LEGACY_MENUS = false`):**
- Whole tabs: **Delivery** (Projects, D&W Survey, Outstanding), **Inventory**
  (Stock, Stock Ledger, Inv. Analytics, Purchase Orders, Manufacturer
  Orders), **Finance** (Tax Invoices, Petty Cash, Cashbooks, Cashbook & Tally
  Sync, Project P&L, Incentives, Payments) — this is general finance/
  invoicing, distinct from HR Payroll.
- Individual items: **Reports** and **Executive Analytics** (Overview tab —
  "advanced analytics"), **Record Chain** and **Team Board/Discussions**
  (Control tab — outside CRM/HR/Admin v1 scope).

**Kept visible (ambiguous, not explicitly in v1 scope, but "if unsure, keep
it" per the brief)** — see the `TODO(v1-scope)` comment above
`ALL_BASEPLATE_SUBNAV` in `baseplateNav.js`: Requirements, Configurator,
Visitors, Sales register (Sales tab); Architects, Meet Planner (Clients
tab); Tasks, Daily Planner, Team & Access (People tab); every admin-settings
page under Control (Data Centre, Data Health, Financial Year, Workflows,
Business Settings, Custom Fields, Roles & Permissions, Audit Trail); Master
Data (Product tab).

**Note on HR Payroll:** the new `/api/v1/payroll/*` endpoints
(`docs/ATTENDANCE_PAYROLL.md`) have no dedicated frontend page yet — there is
nothing to show/hide for Payroll in the nav today. Attendance's existing
page (`/attendance`, People tab) is unaffected and stays visible.

**Nothing was removed from `App.js`** — every hidden route still works if
navigated to directly (e.g. a bookmark), and `frontend/src/lib/nav.js`'s
`ALL_PAGES` (used by Role Manager's permission grid) is untouched, so an
admin can still grant/revoke access to a hidden page.

**To re-enable everything:** set `REACT_APP_SHOW_LEGACY_MENUS=true` in
`frontend/.env` and restart the dev server / rebuild — no code changes
required. To re-enable a single item instead, remove its tab from
`LEGACY_TABS` or its code from `LEGACY_ITEM_CODES` in `baseplateNav.js`.

**To verify:** log in and confirm the header shows only Overview, Sales,
Clients, People, Control, Product pills (Delivery/Inventory/Finance pills
gone); within Overview, Reports/Executive Analytics are gone; within
Control, Record Chain/Team Board are gone. Then set
`REACT_APP_SHOW_LEGACY_MENUS=true`, restart, and confirm all pills/items
return.

## Payroll UI

A minimal read-only Payroll page fills the gap noted above: `/people/payroll`
(`frontend/src/pages/PayrollPage.jsx`), linked from the **People** pill in
the header nav (`frontend/src/lib/baseplateNav.js`'s `people` tab, code
`PR2`) — not behind `SHOW_LEGACY_MENUS`, since Payroll is in v1 scope.

- `CalculatePayrollButton` — employee picker (from `GET /api/users/directory`)
  + period start/end dates, calls `POST /api/v1/payroll/calculate`.
- `PayrollList` — renders `GET /api/v1/payroll` (new list endpoint, added to
  `backend/api_hr.py` alongside the existing `GET /api/v1/payroll/{id}` —
  registered *before* `/payroll/{period_id}` in the router, same route-
  ordering fix as `/quotes/followups` earlier, so `/payroll` itself is never
  swallowed by the `{period_id}` path param).
- `PayrollStatusBadge` — Draft (amber) / Approved (blue) / Paid (green).
- `backend/models_hr.py`'s `PayrollPeriod` gained a `gross_pay` field (was
  computed and discarded) so the "Gross Pay" column doesn't need to reverse-
  engineer it from `net_salary`. Existing rows created before this change
  simply have no `gross_pay` (frontend falls back to 0 for those).

**Access:** gated the same way as every other page (`page="payroll"` on the
route, `payroll` added to `frontend/src/lib/nav.js`'s `NAV` so Role Manager
can grant/revoke it per role) and, on the backend, the same admin/accountant
gate as `/payroll/calculate` (payroll exposes salary figures).

**To verify:** log in as admin, open People > Payroll, pick an employee and
a date range, click Calculate Payroll — a new row appears with Gross Pay/
Deductions/Net Pay/Status populated.

## Feature Readiness (ECC Phase 0/1/2 pass)

Full detail in `docs/DIFFERENTIAL_GAP_ASSESSMENT.md`,
`docs/API_FEATURE_MATRIX.md`, `docs/FEATURE_ROADMAP.md`. Status as of this
pass:

| Area | Status | Notes |
|---|---|---|
| Canonical CRM (Leads, Opportunities) | **Ready** | Tested, tenant-isolated. No per-role RBAC yet (any signed-in user can edit any record in-tenant) — acceptable for v1 single-tenant-team use, flagged as the recommended next pass. |
| Canonical Accounts/Contacts | **Ready** (Phase 2) | Routers added this pass, tenant-isolated + chain-integrity tested (a Contact can't be created against another tenant's Account). Same RBAC gap as Leads/Opportunities above. |
| Canonical Activities | **Ready** (Phase 2) | Append-only timeline against Account/Contact/Lead/Opportunity/Quotation; `related_id` validated same-tenant on create. |
| Canonical Quotations | **Not ready for production use** | Schema stub only; the real, tested quotation engine is still the legacy `quotes` collection. See `docs/ODOO_MADIO_DECISION.md`. Deliberately deferred in Phase 2 — see `docs/IMPLEMENTATION_PHASE_2.md`. |
| Teams / assignment / routing | **Not started** | Deliberately deferred in Phase 2 — needs its own scoping conversation. |
| HR Attendance (legacy, geofenced) | **Ready** | Unchanged, mature, tested. |
| HR Attendance (canonical log) | **Ready** | Tenant-isolated (verified this pass), no RBAC gate (any signed-in user) — lower risk, no financial data. |
| HR Payroll (canonical, persisted) | **Ready** (Phase 4) | Bulk run with `dry_run`, approved-Unpaid-leave deduction, and earned-commission auto-bonus added and tested — see `docs/IMPLEMENTATION_PHASE_4.md`. |
| HR Payroll (legacy, stateless) | **Ready** | Unchanged, preserved per hard rule. |
| HR Leave requests | **Ready** (Phase 4) | Self-service create + admin/`leave.approve`-gated status; wired into payroll's `effective_days`. No frontend page yet (backend-only pass, same as Payroll before its UI landed). |
| D&W release-to-production gate | **Ready** (Phase 3) | `client_sign_off` on `DWSurvey`; `create_project_daily_log` blocks `current_milestone: "Production"` for a project with any unsigned linked survey. See `docs/IMPLEMENTATION_PHASE_3.md`. |
| Paints / Furniture domain models | **Not started** | Still manifest `custom_fields` only — deliberately deferred, needs its own scoping session (see Phase 3 doc). |
| Readiness/health | **Ready** | `/api/health` (existing) + `/api/ready` (new this pass, Mongo ping). |
| Tally sync — cashbook vouchers | **Ready** | Unchanged, mature, tested. |
| Tally sync — customers, idempotency ledger | **Ready** (Phase 5) | `TallyConnection` (per-tenant, no secrets), `SyncRun`/`SyncItem` content-hash ledger; customer-ledger sync proven idempotent by the ledger itself. See `docs/IMPLEMENTATION_PHASE_5.md`. |
| Tally sync — products, invoices, receipts | **Not started** | Ledger infrastructure exists and is tested; each entity still needs its own Tally master/voucher mapping (deferred, see Phase 5 doc). |
| Incentive scheme/ledger | **Ready, reused** (Phase 4) | `commission_rules`/`commission_payouts` (already working, auto-generated on deal-won) wired into payroll rather than duplicated into a new `IncentiveLedger`. |
| Team/routing | **Not started** | Deliberately deferred in Phase 2 — needs its own scoping conversation. |
| UI nav scope (v1) | **Ready** | `SHOW_LEGACY_MENUS` flag, documented above. |
| Phase 8 UI-vs-target comparison | **Blocked** | `Business-OS-Product-UI-standalone.html` referenced but not present in the repo. |

**Since this table was first written**, Phases 3-5 landed — see
`docs/IMPLEMENTATION_PHASE_3.md`, `_4.md`, `_5.md`, and the updated rows
above. `python -m pytest tests -q --deselect tests/test_tenant_isolation_api.py`
now passes 573 (was 560).

## Rollback

This deploy is purely additive at the code level (new files + two small edits to `tenancy.py`'s `TENANT_COLLECTIONS` set and `server.py`'s router mounting). Rollback is a straight revert of the commit(s):

```
git log --oneline -5                       # find the commit(s) to revert
git revert <commit-sha>                    # or: git checkout <previous-sha> -- backend/server.py backend/tenancy.py
```

No data migration ran, so there is nothing to roll back at the database level — the `crm_*` collections simply stop being written to once the code reverts. Deleting them is optional cleanup, never required for rollback safety:
```
# optional, only if you want to remove the test data these smoke tests created
mongosh $env:MONGO_URL --eval "db.getSiblingDB('madio_crm').crm_leads.drop(); db.getSiblingDB('madio_crm').crm_opportunities.drop(); db.getSiblingDB('madio_crm').crm_accounts.drop();"
```
