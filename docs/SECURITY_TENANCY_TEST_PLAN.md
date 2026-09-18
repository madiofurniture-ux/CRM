# Security & Tenancy Test Plan — Madio Business OS

## Existing coverage (verified this pass)

| Test | What it proves | Status |
|---|---|---|
| `backend/tests/test_tenancy.py` | `tenancy.scope()`/`stamp()` unit-level correctness | Passing |
| `backend/tests/test_permissions.py` | `permissions.py`'s role/module/action/scope matrix, legacy-account backward compatibility | Passing |
| `backend/tests/test_tenant_isolation_api.py` | Live-HTTP, two real provisioned tenants: read isolation, cross-tenant PUT/DELETE rejection (404, not silent no-op), export isolation+admin-gating | Passing (extended this pass — see below) |
| `backend/tests/test_cost_price_security.py` | Cost-price field redaction by role | Passing |
| `backend/tests/test_personal_visibility.py` | Own/team/all scope enforcement | Passing |
| Full suite | `python -m pytest tests/ -q` | 560 passed, this pass |

## Extended this pass

`test_tenant_isolation_api.py` now also covers:
- `crm_leads` (`/api/v1/leads`) and `hr_attendance_logs` (`/api/v1/attendance`)
  in the standard seed + read-isolation + cross-tenant-write-rejection loop.
- A dedicated regression test for the payroll cross-tenant employee-lookup
  bug found and fixed this pass: tenant B's admin attempts
  `POST /api/v1/payroll/calculate` with tenant A's real employee id, must
  get `404`.

Run: `python backend/tests/test_tenant_isolation_api.py --base http://127.0.0.1:8000`
(requires `SEED_PINS` to include `admin=1234` or the dev default, and a
reachable Mongo).

## Gaps — recommended next tests, not yet written

1. **Canonical CRM RBAC.** `api_canonical.py` has no `permissions.py` check
   at all (see `API_FEATURE_MATRIX.md`). A test proving "a role without
   `edit` on `leads` cannot `PUT /api/v1/leads/{id}`" cannot pass today
   because the enforcement doesn't exist — write the enforcement first
   (recommended next Phase 1/2 slice), then the test.
2. **Payroll status-transition legality.** Today `POST /payroll/{id}/status`
   accepts any of Draft/Approved/Paid in any order (no state-machine check).
   A test should assert Paid -> Draft is rejected once that rule is decided
   and implemented.
3. **Brand-scope isolation** (distinct from tenant isolation): two brands
   *within the same tenant* — does `GET /api/v1/leads?brand_id=X` ever leak
   brand Y's records to a caller who only has X's manifest loaded? Not
   tested; `_require_brand` currently only validates the manifest exists,
   not that the caller is "allowed" that brand (there is no such concept
   yet — brands are intra-tenant, not access-controlled individually).
4. **Audit trail existence** — once a general audit/event record exists
   (Phase 1 deferred item), add a test asserting every payroll
   status-transition, quotation discount-approval, and Tally sync write
   produces exactly one audit record with correct before/after/actor.
5. **Secret handling in Tally integration** (Phase 5) — a test asserting no
   `TallyConnection` document or log line ever contains a raw secret value
   (grep-style assertion over serialized documents/log output in a test
   fixture, before that feature is built).
6. **Idempotency of financial writes** — per hard rule 5, add a test per
   Phase 5/6 write path (Tally sync, bulk payroll run) asserting a retried
   call with the same idempotency key produces zero duplicate records.

## How to run everything

```bash
cd backend
python -m pytest tests/ -q                                      # unit + component tests
python tests/test_tenant_isolation_api.py --base http://127.0.0.1:8000   # live tenant isolation
curl -s http://127.0.0.1:8000/api/ready                          # dependency health
```
