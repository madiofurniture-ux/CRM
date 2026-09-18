# Phase 1 — Foundation and Controls: Plan + Result

## Plan (before implementation)

Phase 0's gap assessment found two concrete, high-priority (P0) issues in
code from this same engagement (the canonical HR payroll API) rather than
speculative future work:

1. `backend/api_hr.py`'s payroll endpoints checked `user.role in
   ("admin","accountant")` directly instead of using the app's existing,
   mature RBAC engine (`backend/permissions.py`, already wired into
   `server.py` via `_require_permission`/`_roles_for`).
2. (Found while wiring #1 in) `payroll_calculate`'s employee lookup
   (`db.users.find_one({"id": payload.employee_id})`) had **no tenant_id
   filter at all** — a real cross-tenant salary-data leak, since `users`
   is deliberately excluded from `tenancy.TENANT_COLLECTIONS` and needs an
   explicit filter (exactly the pattern `server.py`'s own legacy
   `/payroll/calculate` already uses for the same collection).

Given the size of the full 8-phase mission, this pass scoped Phase 1 to:
fix both findings, add the one clearly-missing operational primitive
(`/api/ready`), and prove all of it with an automated, live test — rather
than build speculative new models (`models_foundation.py`, general audit
records, stage-metadata graphs) with no concrete consumer yet. That
speculative work is listed as deferred below, not silently dropped.

## What was implemented

1. **`GET /api/ready`** (`backend/server.py`) — pings Mongo
   (`db.command("ping")`), returns `200 {"status":"ok","mongo":"ok",...}` or
   `503 {"status":"degraded","mongo":"unreachable",...}`. Distinguishes
   "process started" (`/api/health`, unchanged) from "can actually serve
   traffic."
2. **RBAC wired into `backend/api_hr.py`** — `payroll_list`/`payroll_get`/
   `payroll_calculate`/`payroll_set_status` now check `role in
   (admin, accountant)` (unchanged floor, never narrowed) **OR**
   `permissions.can(user, roles, "payroll", action)` (new — lets a tenant
   grant a custom role `view`/`create`/`approve` on the `payroll` module
   without needing the `accountant` literal role). `GET /payroll/{id}` had
   **no** gate at all before this pass; it now has one, matching the other
   three routes.
3. **Tenant-scoped employee lookup** in `payroll_calculate` — added the
   `tenant_id` filter that was missing, mirroring `server.py`'s own
   comment/pattern for the same `users`-collection edge case.
4. **Regression tests**, all live-HTTP against two freshly-provisioned
   tenants (`backend/tests/test_tenant_isolation_api.py`, extended):
   - `crm_leads` (`/api/v1/leads`) and `hr_attendance_logs`
     (`/api/v1/attendance`) added to the write-seed + read-isolation checks.
   - A dedicated cross-tenant payroll check: tenant B's admin attempts
     `POST /api/v1/payroll/calculate` using tenant A's real employee id —
     must get `404`, not `200` with tenant A's salary data. This is a
     direct regression test for finding #2 above.
   - Fixed a pre-existing flaky bug in the same test file, found while
     extending it: the random seed `tag` was hex (`uuid4().hex`), and the
     legacy-leads seed payload builds a phone number from it
     (`f"90000{tag[-5:]}"`) — a hex letter (a-f) made `normalize_indian_phone`
     reject it intermittently. Changed to a decimal tag.

## Verification run this pass

```
cd backend
python -m py_compile server.py api_hr.py api_canonical.py models_hr.py models_canonical.py tenancy.py permissions.py
python -m pytest tests/ -q --deselect tests/test_tenant_isolation_api.py   # 560 passed
python tests/test_tenant_isolation_api.py --base http://127.0.0.1:8000     # isolated 16, leaking 0, write-leaks 0
curl -s http://127.0.0.1:8000/api/ready                                    # {"status":"ok","mongo":"ok",...}
```

Manual confirmation that the permission change is additive, not narrowing:
a legacy `role="user"` account (no `role_id`) can still `GET /api/v1/payroll`
(the pre-existing `view` implicit grant), but correctly gets `403` on
`POST /api/v1/payroll/{id}/status` (the new `approve` gate) unless granted
explicitly or an admin/accountant.

## Explicitly deferred (not implemented this pass)

- `backend/models_foundation.py`/`backend/api_foundation.py` as named files
  — not created. The two concrete gaps they would have addressed (audit
  trail, stage metadata) have no consumer yet in this pass; building the
  scaffolding first risks the exact kind of unused abstraction the
  "keep changes minimal" constraint warns against. Recommended as the
  *next* Phase 1 slice once a concrete Phase 2/3 feature needs it.
- General-purpose audit/event record with before/after diff — real gap,
  P0 per the gap assessment (financial/payroll rule), but sizing it
  correctly needs a decision on where it lives (own collection vs. reusing
  `record_activity()`'s existing shape) — flagged for the next session
  rather than guessed at here.
- Stage metadata (sequence/owner role/SLA/gate/allowed-transition graph) —
  no code changed; `modules/*/manifest.json`'s existing `{key,label,
  terminal,won}` shape is unchanged.
- Feature flags for *backend* API surfaces (only the frontend nav flag,
  `SHOW_LEGACY_MENUS`, exists) — not built; nothing currently needs it,
  since no half-finished endpoint is reachable from the UI.
