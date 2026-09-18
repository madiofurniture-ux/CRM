# Prompt 2: Attendance → Payroll Linkage (2-3 hours)

You are an Autonomous ECC Engineering Agent. Work in `C:\Users\jagad\Projects\CRMNew`.

## Goal

Link attendance to payroll so payable days, LOP, and OT flow automatically from attendance to payroll calculation.

## Scope

### Entities

**PayrollPeriod (existing — add fields)**

Add to existing `PayrollPeriod` model:

- `attendance_imported` (boolean, default False — True after attendance data pulled)
- `attendance_imported_at` (ISO datetime, nullable)
- `attendance_imported_by` (string, user_id, nullable)
- `payable_days` (float, computed from attendance: Present + Approved Leave)
- `lop_days` (float, computed from attendance: Unapproved absences)
- `overtime_hours` (float, sum of OT from attendance)
- `attendance_breakdown` (JSON, e.g., `{"Present": 22, "Leave": 2, "LOP": 1, "Holiday": 1}`)
- `attendance_exceptions` (list of strings, e.g., `["Late on 2026-09-05", "Missing punch on 2026-09-10"]`)
- `attendance_locked` (boolean, default False — True when attendance can't be changed)

**AttendanceLog (existing — no changes needed)**
- Already has: `employee_id`, `date`, `check_in`, `check_out`, `total_hours`, `status` (Present/Late/Overtime/Absent), `overtime_hours`, `location`, `tenant_id`

### Business Logic

**Attendance import into payroll:**

- `POST /payroll/{period_id}/import-attendance`:
  - Validates period is in Draft status
  - Queries `AttendanceLog` for `employee_id` in `period_start` to `period_end`
  - Calculates:
    - `payable_days` = count of (Present + Approved Leave)
    - `lop_days` = count of (Absent without approved leave)
    - `overtime_hours` = sum of `overtime_hours` field
    - `attendance_breakdown` = status counts
    - `attendance_exceptions` = list of unresolved exceptions (late, missing punch, outside geofence)
  - Updates `PayrollPeriod` with computed values
  - Sets `attendance_imported = True`
  - Sets `attendance_locked = True` (prevents re-import without unlock)

**Payroll calculation uses attendance:**

- Update existing payroll calculation logic:
  - `payable_days` from attendance (not manual entry)
  - `lop_deduction` = `(basic_salary / working_days_in_month) * lop_days`
  - `overtime_pay` = `overtime_hours * OT_rate_per_hour`
  - Add line items to payroll register:
    - "Payable Days: {payable_days}"
    - "LOP Days: {lop_days}"
    - "OT Hours: {overtime_hours}"
    - "LOP Deduction: {lop_deduction}"
    - "OT Pay: {overtime_pay}"

**Attendance exceptions block payroll:**

- Payroll approval gate:
  - If `attendance_exceptions` list is non-empty:
    - Block approval with message: "{count} attendance exceptions must be resolved"
    - List exceptions in error response
  - Override requires Division Head approval (audited)

**Payroll register updates:**

- Add columns to payroll register response:
  - `payable_days`
  - `lop_days`
  - `overtime_hours`
  - `lop_deduction`
  - `overtime_pay`

**Attendance summary API:**

- `GET /payroll/{period_id}/attendance-summary`:
  - Returns breakdown by employee:
    - `employee_id`, `name`, `payable_days`, `lop_days`, `overtime_hours`, `exceptions`
  - Used by frontend to show preview before calculation

### APIs

**Under `/api/v1/payroll`:**

- `POST /payroll/{period_id}/import-attendance`
  - Body: `{ dry_run?: boolean }` (if dry_run, don't persist, just return preview)
  - Returns: `{ payable_days, lop_days, overtime_hours, attendance_breakdown, attendance_exceptions, affected_employees: [...] }`

- `GET /payroll/{period_id}/attendance-summary`
  - Returns: employee-wise breakdown

- `POST /payroll/{period_id}/unlock-attendance`
  - Requires Division Head role
  - Sets `attendance_locked = False` to allow re-import
  - Audited (who, when, why)

**Update existing `/payroll/{period_id}/calculate`:**

- Use `payable_days`, `lop_days`, `overtime_hours` from imported attendance
- Calculate LOP deduction and OT pay
- Add to payroll register response

### Tests

Create `tests/test_attendance_payroll_link.py`:

1. Attendance import calculates payable_days correctly
2. LOP days calculated from unapproved absences
3. Overtime hours sum correctly
4. Payroll uses attendance-derived payable_days
5. LOP deduction calculated correctly
6. OT pay calculated correctly
7. Payroll blocked when attendance exceptions exist
8. Override approval works (Division Head role)
9. Attendance unlock requires Division Head
10. Tenant isolation: can't see other tenant's attendance in payroll
11. Regression: existing payroll calculation still works without attendance import (backward compat)

### Files to Create/Modify

**Modify:**
- `backend/models_hr.py` — Add attendance fields to PayrollPeriod
- `backend/api_hr.py` — Add import-attendance, attendance-summary, unlock-attendance endpoints; update calculate endpoint
- `backend/lifecycle.py` — Add attendance exceptions check to payroll approval gate
- `tests/test_attendance_payroll_link.py` — Tests

**No new files needed** — all additive to existing HR models/APIs.

### Constraints

- Preserve existing payroll arithmetic (gross_pay, deductions, net)
- Attendance data is read-only in payroll (no editing attendance from payroll UI)
- Use existing `AttendanceLog` and `PayrollPeriod` entities
- No floating-point for money (use integer paise or Decimal)
- Add tests before exposing UI
- Backward compatible: existing payroll periods without attendance import still work

### Output

- All files modified
- Tests passing (run `python -m pytest tests/test_attendance_payroll_link.py -v`)
- `docs/ATTENDANCE_PAYROLL_LINK_DESIGN.md` — 1-page design summary
- Summary in chat:
  - Files modified
  - Tests passing
  - Smoke-test curl commands
  - Any deferrals or known issues

Begin with a 5-line plan, then implement autonomously.