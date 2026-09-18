# API Feature Matrix — Madio Business OS

Snapshot as of this pass. `Tenant` = enforced via `tenancy.scope`/`stamp`.
`RBAC` = enforced via `permissions.py` (`can()`/`_require_permission`),
not just a role-literal check. `Tested` = covered by an automated test
(`backend/tests/`) or a documented live smoke test in this repo's docs.

## Canonical CRM v1 (`backend/api_canonical.py`, prefix `/api/v1`)

| Endpoint | Method | Tenant | RBAC | Tested | Notes |
|---|---|---|---|---|---|
| `/leads` | GET/POST | Yes | No (`get_current_user` only) | Yes (smoke, `GO_LIVE_V1_CHECKLIST.md`) | No permission-module check at all |
| `/leads/{id}` | GET/PUT | Yes | No | Partial | |
| `/leads/{id}/move_stage` | POST | Yes | No | Yes | Validates against brand pipeline labels |
| `/leads/{id}/convert` | POST | Yes | No | Yes (idempotency confirmed) | |
| `/opportunities` | GET/POST | Yes | No | Partial | |
| `/opportunities/{id}` | GET/PUT | Yes | No | Partial | |
| `/opportunities/{id}/set_won` `/set_lost` | POST | Yes | No | Partial | |
| `/accounts` | GET/POST | Yes | No | Yes (Phase 2, isolation) | New this pass — model existed, no router before |
| `/accounts/{id}` | GET/PUT | Yes | No | Yes (Phase 2, isolation) | |
| `/contacts` | GET/POST | Yes | No | Yes (Phase 2, isolation + chain-integrity) | `account_id` validated same-tenant on create |
| `/contacts/{id}` | GET/PUT | Yes | No | Yes (Phase 2, isolation) | |
| `/activities` | GET/POST | Yes | No | Yes (Phase 2, chain-integrity) | Append-only (no PUT by design); `related_id` validated same-tenant on create |
| `/activities/{id}` | GET | Yes | No | Yes (Phase 2) | |
| `/brands`, `/brands/{id}/config` | GET | N/A (public config) | N/A | Yes | No auth required by design |

**Gap (unchanged from Phase 1):** none of the canonical CRM routes use
`permissions.py` — every signed-in user can read/write any Lead/
Opportunity/Account/Contact/Activity in their tenant regardless of role.
Lower severity than payroll (no salary data), but the same class of gap
Phase 1 fixed for HR; recommended as the next RBAC pass.

## HR: Attendance + Payroll (`backend/api_hr.py`, prefix `/api/v1`)

| Endpoint | Method | Tenant | RBAC | Tested | Notes |
|---|---|---|---|---|---|
| `/attendance` | POST | Yes | No (any signed-in user) | Yes (this pass, isolation) | Manual/backfill log, separate from legacy geofenced attendance |
| `/attendance` | GET | Yes | No | Yes (this pass, isolation) | |
| `/payroll` | GET | Yes | **Yes** (this pass) | Yes (this pass) | admin/accountant OR granted role |
| `/payroll/calculate` | POST | **Yes** (this pass — was the P0 bug) | **Yes** (this pass) | Yes (this pass, dedicated regression test) | |
| `/payroll/{id}` | GET | Yes | **Yes** (this pass — had none before) | Yes (this pass) | |
| `/payroll/{id}/status` | POST | Yes | **Yes** (this pass) | Yes (manual: legacy account correctly 403s) | Draft/Approved/Paid |

## Legacy attendance/payroll (`backend/server.py`, prefix `/api`)

| Endpoint | Method | Tenant | RBAC | Tested | Notes |
|---|---|---|---|---|---|
| `/attendance/check-in` `/check-out` | POST | Yes | No (any signed-in user, by design — self-punch) | Yes (`test_geofence_attendance.py`) | |
| `/attendance` | GET | Yes | Admin sees all, others see own | Yes | |
| `/attendance/{id}/regularize` | POST | Yes | `require_admin` | Yes | |
| `/attendance/{id}/mark-absent` | POST | Yes | `require_admin` | Yes | |
| `/attendance/payroll` | GET | Yes | Admin or self | Yes | Effective-days aggregation only, no pay-rate math |
| `/payroll/calculate` | POST | Yes (explicit hand-written filter, see code comment) | role literal (`admin`/`accountant`) | Yes (`test_payroll_calculation.py`) | Stateless, preserved unchanged per hard rule 1 |

## Legacy core CRM (`backend/server.py`, prefix `/api`, via `make_crud`)

| Endpoint family | Tenant | RBAC | Tested | Notes |
|---|---|---|---|---|
| `/leads`, `/quotes`, `/sales`, `/visitors`, `/projects`, `/inventory`, etc. | Yes | **Yes** — `make_crud` wires `_require_permission` | Yes (`test_tenant_isolation_api.py`, `test_permissions.py`) | The mature, working reference implementation for what the canonical routers should also do |
| `/analytics/commissions*` | Yes | Yes (`_require_permission("commissions", ...)`) | Not directly inspected this pass | Confirm actual behavior before Phase 4 builds a parallel incentive system |

## Operational

| Endpoint | Method | Auth | Tested | Notes |
|---|---|---|---|---|
| `/health` | GET | None | Yes (used throughout this session) | Liveness only |
| `/ready` | GET | None | Yes (this pass) | New — checks Mongo connectivity, 503 on failure |
| `/tenants` | POST | admin-only | Yes (exercised every isolation-test run) | Used by `test_tenant_isolation_api.py` to provision tenants |

## Summary

- **RBAC coverage gap, ranked by risk:** (1) canonical CRM routes have zero
  permission-module checks (flagged, not fixed, this pass; lower risk, no
  financial data) vs. (2) HR payroll routes, which DID expose salary data
  and are now fixed and tested.
- **Tenant-isolation coverage:** legacy core CRM is well-tested
  (`test_tenant_isolation_api.py` pre-existed this pass); canonical CRM
  and HR are now covered by the same harness as of this pass; the one
  concrete bug found (`payroll_calculate`'s unscoped `users` lookup) is
  fixed and has a dedicated regression test.
