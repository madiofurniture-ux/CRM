# v1.1 Release Notes

Scope: the roadmap work landed on top of the Madio Canonical CRM v1 base
(`docs/GO_LIVE_V1_CHECKLIST.md`) — `docs/FEATURE_ROADMAP.md` Phases 1
through 6, plus the two UI features that shipped alongside them. Each
phase's own scope decisions, what was built, and what was explicitly
deferred are in `docs/IMPLEMENTATION_PHASE_1.md` through `_6.md`; this
document is the release-facing summary.

## Backend

**Phase 1 — Foundation and controls**
- `GET /api/ready` — Mongo-backed liveness probe, distinct from
  `/api/health` ("process started" vs. "can actually serve traffic").
- HR payroll endpoints (`backend/api_hr.py`) now route through the app's
  RBAC engine (`permissions.py`) instead of a hardcoded role check, and a
  cross-tenant salary-data leak in `payroll_calculate`'s employee lookup was
  closed (`users` collection needs an explicit `tenant_id` filter — it's
  deliberately excluded from automatic tenant scoping).

**Phase 2 — Sales record chain**
- `/api/v1/accounts`, `/api/v1/contacts`, `/api/v1/activities` — canonical
  CRUD routers for models that already existed but had no HTTP surface.

**Phase 3 — Industry operations**
- D&W survey sign-off gate: a project can no longer advance to the
  `Production` milestone via the daily-log endpoint until its linked D&W
  survey has a recorded client sign-off.

**Phase 4 — Attendance, leave, payroll, incentives**
- `LeaveRequest` — an approved leave request now measurably reduces
  `effective_days` in payroll calculation.
- Bulk payroll run with a dry-run flag.
- Incentive ledger entries reach a payroll period without any
  manually-typed number.

**Phase 5 — Tally integration**
- `TallyConnection` (per-tenant settings, no secrets in documents/logs) and
  a `SyncRun`/`SyncItem` idempotency ledger keyed by
  `(tenant_id, entity_type, source_id, operation, content_hash)` — running
  the same sync twice produces zero duplicate vouchers.
- Fixed a pre-existing cross-tenant leak: `leave_requests` (added in
  Phase 4) was missing from `tenancy.TENANT_COLLECTIONS`.

**Phase 6 — Inventory, purchasing, finance read models**
- PO approval threshold (₹1,00,000) — a purchase order above it can't move
  to `Issued`/`Received` without admin/accountant sign-off
  (`POST /purchase-orders/{id}/approve`).
- GRN — `POST /purchase-orders/{id}/receive` reconciles received qty per
  line against a PO, writes linked stock-ledger `Receipt` movements, and
  only closes the PO once every line is fully received.
- `Reservation` stock-movement type — holds stock for a project without
  moving it, excluded from physical on-hand.
- Petty-cash receipt evidence + approval: an `Out` entry over ₹5,000 starts
  `Pending` and needs sign-off (`POST /petty-cash/{id}/approve`) before
  it's trusted.

## Frontend

- **Payroll page** (`/people/payroll`) — new screen wired into the route
  table.
- **Baseplate nav trimmed to v1 scope** — CRM (Leads/Opportunities/
  Accounts & Contacts/Quotations), HR (Attendance/Payroll), Admin
  (Users/Brands) shown by default. Nothing deleted: the full nav still
  exists as `ALL_BASEPLATE_SUBNAV`/`ALL_BASEPLATE_TABS`
  (`frontend/src/lib/baseplateNav.js`), gated behind the new
  `SHOW_LEGACY_MENUS` flag (`frontend/src/lib/featureFlags.js`).
- **Project-scoped petty cash ledger** — a project selector and
  in/out/balance stat cards added to the existing flat Petty Cash screen
  (`PettyCash.jsx`), distinct from the separate Cashbook wallet system.

## Verification

```
cd backend
python -m pytest tests/ -q   # 589/589 passing
```

No frontend build/lint run is recorded for this pass beyond the individual
UI commits' own verification (see `docs/GO_LIVE_V1_CHECKLIST.md`'s "UI
Cleanup" section and `PROJECT_PETTY_CASH_CUTOVER.md` for those results).

## Not in this release

- **Phase 7 (Reporting and operator console)** — blocked on having enough
  canonical-layer production data to report on; the canonical API is brand
  new this engagement.
- **Phase 8 (UI and navigation)** — blocked on
  `Business-OS-Product-UI-standalone.html`, referenced by the engagement
  brief but not present anywhere in this repository.
- **Tally-export P&L reconciliation** — Phase 6's literal exit test; no
  existing diff/reconciliation tooling to build on, scoped as its own
  follow-up.
- Frontend wiring for Phase 6's new PO-approval, GRN-receive, Reservation,
  and petty-cash-approval endpoints — all additive and unreachable from any
  screen today, so nothing is half-finished in the UI.
