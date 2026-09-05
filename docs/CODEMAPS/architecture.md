<!-- Generated: 2026-08-26 | Files scanned: ~90 | Token estimate: ~450 -->
# Architecture — MADIO CRM

Single-tenant-capable multi-tenant CRM. SPA frontend talks to a FastAPI JSON
API over `/api`; API reads/writes MongoDB directly (no ORM).

```
+--------------+   axios (frontend/src/lib/api.js)   +--------------------+
| React 19 SPA | -----------------------------------> | FastAPI /api/*     |
| (Netlify)    | <----------------------------------- | backend/server.py  |
+--------------+         JSON + JWT bearer             | (Render)           |
                                                        +---------+----------+
                                                                  | motor (async)
                                                                  v
                                                        +--------------------+
                                                        | MongoDB             |
                                                        | one DB, tenant_id   |
                                                        | on every document   |
                                                        +--------------------+
```

## Service boundaries
- `frontend/` — React 19 + CRACO SPA, shadcn/Radix UI, no server-side rendering.
- `backend/` — one FastAPI process, all routes under `backend/server.py`, no
  microservices, no message queue.
- `db/migrations/*.sql` — **aspirational** contract for a future SQL backend
  that does not exist yet. The live datastore is MongoDB. Do not treat these
  files as the current schema.

## Data flow (core business pipeline)
```
Visitor -> Lead -> Quote -> Sale -> Project
                     |        |
                     v        v
                QuoteLine   Payment / Invoice / StockMovement
```
Architect referrals attach to Leads/Quotes. DWSurvey (door/window survey)
feeds Quotes via `POST /convert/survey-to-quote/{id}`. Attendance and
PettyCash are operational modules, not part of the sales pipeline.

## Multi-tenancy
Every document carries `tenant_id`. `backend/tenancy.py::scope()` is the sole
chokepoint for read/write scoping and is **fail-closed**: a user with no
tenant matches nothing, never everything. See [data.md](data.md) and
[backend.md](backend.md).

## Auth
JWT bearer tokens, PIN-based login (`backend/auth.py`). No default
`JWT_SECRET` — missing env var must fail startup, not silently fall back to a
public value baked into this repo.

## Cross-refs
- Routes and CRUD pattern -> [backend.md](backend.md)
- Page tree and component layout -> [frontend.md](frontend.md)
- Collections and entity relationships -> [data.md](data.md)
- External services and libraries -> [dependencies.md](dependencies.md)
