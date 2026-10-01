<!-- Updated: 2026-09-30 | Scanned: backend/*.py, backend/tests/ -->
# Backend: MADIO CRM API

FastAPI + Motor (async MongoDB). Most routes live in `backend/server.py`
(~6,900 lines) under `api = APIRouter(prefix="/api")`, with pure domain logic
split into small modules that are unit-tested without Mongo. There's no
service or repository layer: routes call `db[collection]` directly, always
scoped through `tenancy.py`. Line numbers drift fast in `server.py`, so
grep for the route string rather than trusting a line reference.

## Key files
| File | What it owns |
|---|---|
| `server.py` | App, routes, the `make_crud` factory, reports, integrations |
| `models.py` | Pydantic Base/Create/full models per entity (~2,100 lines) |
| `auth.py` | PIN login, JWT, `get_current_user`, `require_admin` |
| `tenancy.py` | Tenant scoping (fail-closed), `TENANT_COLLECTIONS`, workflow stage schema, defaults, locked system stages, `ENTITY_COLLECTION`/`STAGE_FIELD` |
| `permissions.py` | Role/permission matrix: `can()`, `scope_for()` (own/team/all) |
| `workflow_rules.py` | Stage gates (required fields, allowed next stages), field catalog, automation rules (create task / set field / notify customer) |
| `lifecycle.py` | Pure helpers: date/money/phone parsing, numbering, journey and 9-stage pipeline bar |
| `analytics.py` | Analytics hub aggregations: sales, leads, calls, attendance, vendors & projects |
| `expenses.py` | Money-request flow: approval chain, policy, decisions, visibility |
| `finance_lineage.py` | Visitor-to-profit deal lineage, Deal P&L, Company P&L, privacy masking |
| `csv_engine.py` | Project P&L (`compute_project_pnl`), masking, CSV import/export |
| `notifications.py` | `EVENTS` templates (single copy source for automated and click-to-chat); WhatsApp Cloud API send when `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` are set, else a log-only stub |
| `storage.py` | Local/S3 file storage for `documents` (`STORAGE_BACKEND=local\|s3`) |
| `tally.py` | Tally voucher XML, sync of reviewed cashbook transactions |
| `quotation_templates.py` | One quotation engine, per-division templates |
| `api_hr.py`, `api_canonical.py`, `api_budget.py`, `api_wallets.py` | Satellite routers (HR/payroll, canonical CRM v1, budgets, legacy wallet mirror) mounted on the app |
| `seed.py` | `seed_all()` sample data; PINs from `SEED_PINS` |

## Generic CRUD (`make_crud`)
One factory registers list/create/update/delete per collection. Every
operation is tenant-scoped (a foreign `id` reads as 404). Optional hooks:
`module`/`owner_field` (role permission + own/team scope), `normalize`,
`after_write`, `on_create`, `redact`, `mask` (privacy mode), `personal`,
`list_filters`, `entity` (audit trail). It also runs **workflow gates**
(`validate_stage`) before writes and **stage history + automations**
(`run_stage_automation`) after them, for any collection in
`tenancy.COLLECTION_ENTITY`.

Registered collections include: visitors, leads, calls, architects, quotes,
sales, inventory, purchase-orders, manufacturer-orders, tasks, invoices,
meets, petty-cash, cashbooks, customers, commission-rules, teams, roles,
quote-lines, dw-openings, vendors, floors, sites.

## Bespoke routes (by area)
```
Auth & tenants   POST /auth/login · /auth/users (admin; reports_to validated, no loops)
                 GET /users/directory · GET /tenants/me (effective_enabled_modules)
                 PUT /tenants/me/config (drops retired module ids)
Flows            GET /flows/meta · GET/POST /flows · PUT/DELETE /flows/{id} · /flows/{id}/toggle|test
                 POST /flows/run-scheduled · GET /flow-runs (flows.py; scheduler on the dispatch loop)
Workflows        GET /workflows[/{entity}] · PUT /workflows/{entity} {stages, rules, enforce}
                 POST /workflows/{entity}/adopt|reset
Projects         POST/PUT /projects · PUT /projects/{id}/stage (gates + automations)
Quotes           /quotes/{id}/workspace · save-total · approve · revise (approval fields locked on plain PUT)
Invoices         POST /invoices/from-sale/{id} · CRUD numbers, totals and paid server-side
Payroll (HR)     /v1/payroll[/calculate|/bulk-calculate|/policy|/{id}/status] (api_hr.py)
Calls            POST /calls/{id}/convert (lead from a call; dedupes by phone)
Analytics        GET /analytics/hub/{sales|leads|calls|attendance|vendors}?start&end&division
                 (older: /analytics/pipeline|revenue|commissions|inventory, /reports)
Money requests   GET/POST /money-requests · PUT /money-requests/{id} · GET /money-requests/summary
                 POST /money-requests/{id}/approve|reject|cancel|transfer
                 GET/PUT /finance/expense-policy
P&L & lineage    GET /finance/deal-pnl?project_id|sale_id|quote_id|lead_id
                 GET /finance/deals · GET /finance/pnl?start&end&division
                 GET /reports/project-pnl (+ export.csv) — all privacy-masked by default
Cashbook         /cashbooks/{id}/entries|top-up|expense · /cashbook-entries/{id}/approve
                 /finance/cashbook + /finance/tally/* (Tally sync of reviewed transactions)
Attendance       /attendance/check-in|check-out|today · /attendance/payroll · regularize
Payments         GET/POST/DELETE /payments (updates sale/invoice balance)
Journey          GET /journey/{phone} (timeline + pipeline bar + whatsapp_messages)
Documents        POST/GET/DELETE /documents (attachments, storage.py)
WhatsApp         GET /notifications/templates · POST /notifications/whatsapp-click
                 GET/POST /webhooks/whatsapp (Meta verify + inbound)
Discussions      GET/POST /discussions · /discussions/channels · /{id}/reply · /dm/{user}
Data centre      /data-centre/collections · export · import · /convert/* helpers
```

## Visibility rules worth knowing
- **Tenant:** `tenancy.scope()`/`stamp()` everywhere. No tenant means match nothing.
- **Role scope:** `_scope_owners(user, roles, module)` returns `None` (all) or
  owner names (own/team). Used by `make_crud` and the sales/leads/calls analytics.
- **Finance:** `_is_finance(user)` = admin or `cashbook:approve`. Finance sees
  every money request and records transfers.
- **Privacy mode:** `mask_other=true` (the default) hides field-settlement
  spend and everything derived from it: P&L, deal P&L, wallet balances.
- **Modules:** a tenant's saved `enabled_modules` is combined with
  `MODULES_ADDED_AFTER_TRACKING`, so newly added modules appear switched on.
  Add every new module id there.

## Auth chain
`get_current_user` (auth.py) decodes the bearer JWT and loads the user, which
carries `tenant_id` into `tenancy.scope()`. `require_admin` adds a role check.
`_require_permission(module, action, user)` enforces the role matrix.

## Tests
`backend/tests/` (~640 tests, run `python -m pytest tests -q` from `backend/`,
with Mongo faked by `mongomock_motor`). Route handlers are called directly as
functions. The newest suites to model new work on: `test_workflow_engine.py`,
`test_calls.py`, `test_analytics.py`, `test_money_requests.py`,
`test_finance_lineage.py`. Tenant isolation: `test_tenancy.py`,
`test_tenant_isolation_api.py`. In-memory live server for browser checks:
`tests/run_local_server.py`.
