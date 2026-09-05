<!-- Generated: 2026-08-26 | Files scanned: 6 | Token estimate: ~700 -->
# Backend — MADIO CRM API

FastAPI app, single file `backend/server.py` (1735 lines), all routes under
`api = APIRouter(prefix="/api")`. Async MongoDB via Motor. No service/repo
layering — routes call `db[collection]` directly, scoped through `tenancy.py`.

## Key files
- `backend/server.py` — app, routes, generic CRUD factory, reports/analytics.
- `backend/models.py` (549 lines) — Pydantic Base/Create/full models per entity.
- `backend/auth.py` — PIN login, JWT issue/verify, `get_current_user`, `require_admin`.
- `backend/tenancy.py` (183 lines) — tenant scoping (fail-closed) + per-tenant
  configurable workflow stages.
- `backend/lifecycle.py` (715 lines) — cross-entity stage transitions / rollups.
- `backend/seed.py` — `seed_all()` demo data.

## Generic CRUD (make_crud, server.py:368)
One factory registers GET (list) / POST (create) / PUT (update) / DELETE per
collection. Every op runs through `tenancy.scope()`; update/delete look up the
record scoped to the caller's tenant first, so a foreign `id` reads as 404,
never as someone else's record.

```
make_crud(api, "visitors",   "visitors",    VisitorCreate,   Visitor)    server.py:807
make_crud(api, "leads",      "leads",       LeadCreate,      Lead)       server.py:808
make_crud(api, "architects", "architects",  ArchitectCreate, Architect)  server.py:809
make_crud(api, "quotes",     "quotes",      QuoteCreate,     Quote)      server.py:810
make_crud(api, "sales",      "sales",       SaleCreate,      Sale)       server.py:811
make_crud(api, "inventory",  "inventory",   InventoryCreate, InventoryItem) server.py:812
make_crud(api, "tasks",      "tasks",       TaskCreate,      Task)       server.py:813
make_crud(api, "invoices",   "invoices",    InvoiceCreate,   Invoice)    server.py:814
make_crud(api, "meets",      "meets",       MeetCreate,      Meet)       server.py:815
make_crud(api, "petty-cash", "petty_cash",  PettyCashCreate, PettyCash)  server.py:817
make_crud(api, "quote-lines","quote_lines", QuoteLineCreate, QuoteLine)  server.py:1179
make_crud(api, "dw-openings","dw_openings", DWOpeningCreate, DWOpening)  server.py:1180
```
NOTE (server.py:1373-1376): a manual `GET /leads` handler exists further down
the file but is dead code — the `make_crud` registration above wins because
FastAPI dispatches to the first matching route. Left in place with a comment;
harmless but a trap if someone edits the wrong handler expecting it to run.

## Bespoke routes (non-CRUD)
```
POST /api/auth/login                        auth.py: verify_pin + create_token
GET  /api/auth/me | /auth/roles | /auth/users
POST/PUT/DELETE /api/auth/users/{id}         admin user management
GET  /api/tenants/me | /tenants  POST /tenants
POST /api/workflows/{entity}/adopt|reset     tenancy.py stage config
GET/PUT /api/workflows | /workflows/{entity}
GET  /api/fy/options              PUT /api/fy/settings          financial-year filters
GET/PUT /api/visibility/settings  PUT /api/records/{coll}/{id}/hidden
GET  /api/outstanding                        balance-due rollup
GET/PUT /api/settings/office
GET  /api/attendance | /attendance/today   POST /attendance/check-in|check-out
GET  /api/dashboard/stats
GET  /api/analytics/inventory
GET/POST/PUT/DELETE /api/projects            + PUT /projects/{id}/stage
GET  /api/quotes/{id}/workspace   POST /quotes/{id}/save-total|approve|revise
GET/POST/PUT/DELETE /api/dw-surveys
GET/POST/DELETE /api/payments                create_payment: writes payment +
                                              updates sale/invoice balance (see
                                              recent fix for a race condition here)
GET/POST/DELETE /api/stock-movements  GET /stock-movements/summary
GET  /api/data-centre/collections  GET .../export/{name}  POST .../import/{name}
GET  /api/reports    GET /api/alerts
GET  /api/journey/{phone}                    cross-entity timeline by phone
POST /api/convert/lead-to-quote/{lead_id}
POST /api/convert/quote-to-sale/{quote_id}
POST /api/convert/survey-to-quote/{survey_id}
```

## Auth chain
`get_current_user` (auth.py) reads `Authorization: Bearer <jwt>`, decodes with
`pyjwt`, loads the user; `require_admin` layers a role check on top. Almost
every route depends on `get_current_user` — it is the injection point that
carries `tenant_id` into `tenancy.scope()`.

## Tests
`backend/tests/`: `backend_test.py`, `test_api_e2e.py`, `test_lifecycle.py`,
`test_tenancy.py`, `test_tenant_isolation_api.py` — tenant isolation has a
dedicated end-to-end test file, matching tenancy.py's fail-closed design intent.
