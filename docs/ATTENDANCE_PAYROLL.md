# Attendance -> Payroll (canonical /api/v1)

## Relationship to the existing attendance/payroll system

MADIO CRM already has a working, tenant-scoped attendance and payroll system
in `backend/server.py`/`backend/models.py`:

- `db.attendance` — geofenced check-in/check-out (`/api/attendance/check-in`,
  `/check-out`, `/regularize`, `/mark-absent`). Its `status` field means
  `"present"` / `"flagged_out_of_bounds"` / `"regularized"` / `"absent"`.
- `POST /api/payroll/calculate` — stateless: recomputes gross pay for every
  active employee for a calendar month, every call. Nothing is persisted, so
  there is no way to fetch a past run by id or approve/mark it paid.

**This doc covers a separate, new layer** (`backend/models_hr.py`,
`backend/api_hr.py`, mounted under `/api/v1`) that adds two things the
existing system doesn't have:

1. A manual/backfill attendance log with a `Present/Late/HalfDay/Overtime/
   Absent` status, in its **own** collection (`hr_attendance_logs`) — kept
   separate from `db.attendance` specifically so this status vocabulary never
   collides with the existing `"present"/"flagged_out_of_bounds"/
   "regularized"` one that `/regularize` and `/mark-absent` already depend on.
2. A **persisted, approvable** payroll run (`PayrollPeriod`, `Draft ->
   Approved -> Paid`) for an arbitrary date range per employee, reusing the
   existing pay arithmetic (`compute_gross_pay`, `_aggregate_effective_days`
   in `server.py`) rather than re-deriving it.

The existing check-in/check-out flow, `/attendance/payroll`, and
`/payroll/calculate` are unchanged.

## Data model

### AttendanceLog (`hr_attendance_logs`)

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `employee_id` | str | -> Users.id |
| `date` | str | `YYYY-MM-DD` |
| `check_in` / `check_out` | str \| null | ISO datetime |
| `total_hours` | float | computed from `check_in`/`check_out` at write time |
| `status` | str | `Present` \| `Late` \| `HalfDay` \| `Overtime` \| `Absent` — computed, see below |
| `brand_id` | str | optional, intra-tenant scope (Madio brand) |
| `tenant_id` | str | hard isolation boundary, stamped by `tenancy.py` |
| `created_at` / `updated_at` | str | ISO datetime |

Status derivation (`models_hr.attendance_status`), in priority order:
1. No `check_in` -> `Absent`
2. `total_hours > 8` -> `Overtime`
3. Has `check_out` and `total_hours < 4` -> `HalfDay`
4. Check-in time-of-day after `09:30` (hardcoded default, see the `ponytail`
   comment in `models_hr.py` for the upgrade path to a configurable shift
   start) -> `Late`
5. Otherwise -> `Present`

### PayrollPeriod (`payroll_periods`)

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `employee_id` | str | -> Users.id |
| `period_start` / `period_end` | str | `YYYY-MM-DD` |
| `total_working_hours` | float | sum of effective hours over the period |
| `total_overtime_hours` | float | |
| `late_count` | int | count of `AttendanceLog` rows with `status == "Late"` in the period |
| `deductions` / `bonuses` | float | from the request payload |
| `net_salary` | float | `gross_pay + bonuses - deductions` |
| `status` | str | `Draft` \| `Approved` \| `Paid` |
| `brand_id`, `tenant_id`, `created_at`, `updated_at` | | as above |

## How payroll is derived from attendance

1. `POST /api/v1/payroll/calculate` pulls every `hr_attendance_logs` row for
   `employee_id` between `period_start` and `period_end`.
2. Those rows are translated into the shape `server.py`'s
   `_aggregate_effective_days` already expects (`user_id`, `check_in_at`,
   `check_out_at`, `duration_min`) and passed to that same function — one
   definition of "what a worked day / overtime hour is worth" for the whole
   app, not a second one that could silently disagree.
3. `server.py`'s `compute_gross_pay` turns effective days + overtime hours
   into gross pay, using the employee's existing `pay_model` /
   `base_pay_rate` / `overtime_eligible` / `overtime_rate_multiplier` fields
   on `Users` (unchanged, already used by the legacy `/payroll/calculate`).
4. `net_salary = gross_pay + bonuses - deductions`, saved as a `Draft`
   `PayrollPeriod`.
5. `POST /api/v1/payroll/{id}/status` moves it to `Approved` or `Paid`
   (admin/accountant only, same role gate as the legacy payroll route).

## Example API calls

```bash
# Log a day's attendance
curl -X POST /api/v1/attendance -H "Authorization: Bearer $TOKEN" -d '{
  "employee_id": "u_123", "date": "2026-09-16",
  "check_in": "2026-09-16T10:15:00+00:00", "check_out": "2026-09-16T17:00:00+00:00"
}'
# -> {"status": "Late", "total_hours": 6.75, ...}

# List an employee's attendance for a range
curl "/api/v1/attendance?employee_id=u_123&from=2026-09-01&to=2026-09-30" -H "Authorization: Bearer $TOKEN"

# Run payroll for a period (admin/accountant only)
curl -X POST /api/v1/payroll/calculate -H "Authorization: Bearer $TOKEN" -d '{
  "employee_id": "u_123", "period_start": "2026-09-01", "period_end": "2026-09-30"
}'
# -> {"id": "p_1", "status": "Draft", "net_salary": 42000.0, "late_count": 1, ...}

# Fetch a persisted payroll run
curl /api/v1/payroll/p_1 -H "Authorization: Bearer $TOKEN"

# Approve it
curl -X POST /api/v1/payroll/p_1/status -H "Authorization: Bearer $TOKEN" -d '{"status": "Approved"}'
```

## Phase 4 additions — leave and incentives (see `docs/IMPLEMENTATION_PHASE_4.md`)

- `POST/GET /api/v1/leave`, `POST /api/v1/leave/{id}/status` — self-service
  leave requests (`leave_type: Paid|Unpaid`), admin/accountant/`leave.approve`
  gated. An **Approved Unpaid** leave day that falls inside a payroll
  period's date range reduces `effective_days` before `compute_gross_pay`
  runs (`PayrollPeriod.leave_days_deducted`).
- Earned `commission_payouts` for an employee (auto-created on deal-won,
  see `server.py`) are pulled into `payroll_calculate` automatically as
  `PayrollPeriod.incentive_bonus`, then flipped to `status: "Included"` with
  a `payroll_period_id` back-reference so they can't be counted twice.
- `POST /api/v1/payroll/bulk-calculate` — `{period_start, period_end,
  brand_id?, dry_run}` runs the same calculation for every active employee
  in the tenant; `dry_run: true` previews without persisting anything or
  touching commission payout status.
