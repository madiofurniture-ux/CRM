# Phase 4 — Attendance, Leave, Payroll, Incentives: Plan + Result

## Scope decision (before implementation)

Most of Phase 4's foundation already existed before this pass — Phase 1
built `backend/models_hr.py`/`api_hr.py`'s manual attendance log and
persisted, approvable `PayrollPeriod` (Draft -> Approved -> Paid), reusing
`server.py`'s `compute_gross_pay`/`_aggregate_effective_days`. What was
still missing, per the roadmap:

1. `LeaveRequest` — and specifically the exit test: an approved leave
   request must *measurably reduce* `effective_days` in a payroll
   calculation, not just exist as a record.
2. Bulk payroll run with a dry-run flag (today only per-employee
   `POST /payroll/calculate` existed).
3. A decision on `commission_rules`/`commission_payouts` vs. a new
   `IncentiveScheme`/`IncentiveLedger`, and — per the exit test — a way for
   an incentive ledger entry to reach a payroll period "without any
   manually-typed number."

**Verified this pass, before writing anything:** `server.py` already
auto-generates `commission_payouts` rows (`status: "Earned"`) on deal-won,
computed from `commission_rules` (`_match_commission_rule`) — this is a
complete, working incentive engine, just never wired into payroll. Building
a parallel `IncentiveScheme` would have duplicated it, exactly the risk the
roadmap called out. So: reuse `commission_payouts` as-is, wire it into
payroll instead of replacing it.

**Explicitly deferred, not implemented this pass:**
- **`ShiftRule`** (generalizing `models_hr.py`'s hardcoded
  `DEFAULT_SHIFT_START = "09:30"`, already flagged there with a `ponytail`
  comment) — no concrete consumer needs a configurable shift start yet
  (single default works for every tenant so far); add it when a brand
  actually asks for a different shift time, per that comment's own upgrade
  path.
- Leave-request UI (`frontend/src/pages/PayrollPage.jsx` is untouched) —
  Phase 4 here, like Phase 1/2, stays backend-only; UI/nav is Phase 8's
  concern.
- Paid leave does not reduce pay (see below) — deliberately out of scope;
  only unpaid leave has a pay effect, which is the case the exit test names.

## What was implemented

### `backend/models_hr.py`
- `LeaveRequestCreate`/`LeaveRequest`/`LeaveStatusUpdate` — `leave_type`
  (`Paid`/`Unpaid`), `status` (`Pending`/`Approved`/`Rejected`).
- `overlap_days(a_start, a_end, b_start, b_end)` — inclusive day-range
  overlap, used to find how many days of an approved leave fall inside a
  given payroll period (a leave spanning a month boundary is only counted
  for the days that actually land in that period).
- `BulkPayrollCreate` — `period_start`/`period_end`/`brand_id`/`dry_run`.
- `PayrollPeriod` gained `leave_days_deducted` and `incentive_bonus` fields
  so a payroll run's composition is visible, not just its final number.

### `backend/api_hr.py`
- `POST/GET /api/v1/leave`, `POST /api/v1/leave/{id}/status` — self-service
  create (an employee can only file leave for themselves unless they hold
  `leave.approve`), admin/accountant/`leave.approve`-gated status changes.
  Generalized the existing payroll-only `_can_payroll`/`_require_payroll`
  into `_can_hr`/`_require_hr(db, user, module, action)` so both `"payroll"`
  and `"leave"` modules share one admin/accountant-floor-plus-permissions.py
  check (`_can_payroll`/`_require_payroll` kept as thin wrappers — no
  external caller needed to change).
- `payroll_calculate`'s body was extracted into `_calculate_payroll(db,
  user, payload, *, persist)` so both the single-employee and new bulk
  endpoint share one code path:
  - Subtracts `_approved_unpaid_leave_days(...)` (via `overlap_days`) from
    `effective_days` before `compute_gross_pay` — this is what makes leave
    *measurably* reduce pay, not just get recorded.
  - `_earned_commission_bonus(db, employee_name, user)` sums every
    `commission_payouts` row for that employee (matched by name, same field
    `server.py`'s deal-won writer already populates) with `status ==
    "Earned"`, adds it to `bonuses` as `incentive_bonus`. On persist, those
    rows are flipped to `status: "Included"` with a `payroll_period_id`
    back-reference, so a second run for the same employee can never
    double-count them — the concrete form of "reaches payroll without a
    manually-typed number."
- `POST /api/v1/payroll/bulk-calculate` — runs `_calculate_payroll` for
  every active (`active != False`) employee in the tenant (optionally
  filtered by `brand_id`). `dry_run: true` computes and returns the same
  per-employee rows without inserting a `PayrollPeriod` or touching
  commission payout status — a safe preview before committing a real run.
  An employee missing pay data (`404` inside `_calculate_payroll`) is
  skipped rather than failing the whole batch.

### Tests
New `backend/tests/test_hr_payroll.py` (direct-call + `mongomock`, same
style as `test_project_tracking.py`; `api_hr.py`'s handlers take a FastAPI
`Request`, so a minimal `SimpleNamespace` stands in for
`request.app.state.db`):
- Self-service leave create + 403 on filing for someone else.
- Approved Unpaid leave measurably lowers `gross_pay` via
  `leave_days_deducted` (the exact roadmap exit test).
- An `Earned` commission payout reaches `incentive_bonus`/`net_salary`
  automatically, flips to `Included`, and is never double-counted on a
  second run (the other exit test).
- Bulk `dry_run=True` computes but writes zero `payroll_periods` rows;
  `dry_run=False` persists one per employee.

## Verification run this pass

```
cd backend
python models_hr.py                                                        # self-check: attendance_status + overlap_days
python -m py_compile server.py api_hr.py models_hr.py
python -m pytest tests/test_hr_payroll.py -q                               # 4 passed
python -m pytest tests/ -q --deselect tests/test_tenant_isolation_api.py   # 566 passed
```
