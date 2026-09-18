# Attendance -> Payroll Linkage — Design Summary

Built from `prompt_2_attendance_payroll_link.md`. One page, per that
prompt's own Output requirement.

## What this is

`PayrollPeriod` (`backend/models_hr.py`) gains `payable_days`, `lop_days`,
`overtime_hours`, `attendance_breakdown`, `attendance_exceptions`,
`attendance_imported`/`_at`/`_by`, `attendance_locked`, `lop_deduction`,
`overtime_pay` — all additive, defaulted, backward compatible.

`api_hr.py`'s `_attendance_breakdown()` reconciles `hr_attendance_logs` +
approved `leave_requests` **per calendar date** across a period (a date
with no log row is `Absent`, same convention `attendance_status(None, ...)`
already uses): worked days (`Present`/`Late`/`HalfDay`/`Overtime`) and
approved-leave-covered `Absent` days are payable; everything else is `LOP`.
`Late` and check-in-without-check-out ("Missing punch") days become
`attendance_exceptions`.

`lop_deduction`/`overtime_pay` reuse `compute_gross_pay`'s own
`day_rate`/`hourly_rate` (server.py) rather than a second formula — the
same rate, not a parallel one that could quietly disagree.

## Deviation from the prompt's assumed lifecycle

The prompt assumes a two-phase flow: create an empty Draft `PayrollPeriod`,
then `POST .../import-attendance` into it, then `POST .../calculate`. This
codebase's actual `/payroll/calculate` (`api_hr.py`) **creates and computes
a period in one call** — there's no separate "create an empty draft" step,
and a period is scoped to exactly one employee (not a batch of employees).

Rather than reshape that into a new multi-step lifecycle (a much larger,
riskier change, and the existing one-shot flow is what `test_hr_payroll.py`
and the rest of this engagement already build on), attendance import was
**folded into `/payroll/calculate` itself** — every period is created with
attendance already imported and locked. `POST
/payroll/{id}/import-attendance` still exists exactly as specified, scoped
to its real, useful job: **re-importing** an existing Draft period after
attendance data changed post-calculation (blocked while
`attendance_locked`, per the prompt's own "prevents re-import without
unlock" rule — `POST .../unlock-attendance` clears it, Division-Head-gated
and audited via `record_activity`).

`GET .../attendance-summary` returns the prompt's declared
`[{employee_id, name, payable_days, lop_days, overtime_hours,
exceptions}]` shape as a **one-row list**, since a period here is always
one employee — not because the endpoint is wrong, but because this
codebase's `PayrollPeriod` doesn't model a multi-employee batch run
(`payroll_bulk_calculate` runs *one period per employee*, not one period
covering many).

## Approval gate

`lifecycle.py` gets one new pure predicate,
`payroll_approval_blocked(attendance_exceptions)`, consistent with that
module's existing "pure functions, no DB, no FastAPI" contract (its own
docstring) — it can't own the DB read the prompt's file list implied.
`api_hr.py`'s `payroll_set_status` calls it: a period with unresolved
exceptions can't move to `Approved` without
`PayrollStatusUpdate.override_attendance_exceptions=True`, which still
requires the same `payroll:approve` grant every status change already
needs (no separate "Division Head" role literal exists in
`permissions.py` — grants are role-configured, not role-named, same
pattern this session's wallets work used) and is audited.

## What was NOT changed

Per the prompt's own Constraints — **gross_pay/net_salary arithmetic is
untouched**. `lop_deduction`/`overtime_pay` are informational register
lines computed alongside the existing `compute_gross_pay` call, never fed
back into it — `compute_gross_pay` already prices effective days and
overtime more precisely (fractional half-days, an `overtime_eligible`
gate) than the prompt's flat `(day_rate) * lop_days` formula would if it
replaced the real calculation.

## Files

**Modified:** `backend/models_hr.py` (new `PayrollPeriod` fields,
`PayrollStatusUpdate`/new `ImportAttendanceRequest`/`UnlockAttendanceRequest`
models), `backend/api_hr.py` (`_attendance_breakdown`, updated
`_calculate_payroll`, new `import-attendance`/`attendance-summary`/
`unlock-attendance` routes, exceptions gate in `payroll_set_status`),
`backend/lifecycle.py` (`payroll_approval_blocked`), `backend/tests/
test_attendance_payroll_link.py` (new — the prompt's own top-level `tests/`
path doesn't exist in this repo; tests live in `backend/tests/`).

**No new files** — matches the prompt's own "No new files needed."

## Verification

```
cd backend
python -m pytest tests/test_attendance_payroll_link.py -v   # 10/10 passing
python -m pytest tests/ -q                                  # 609/609 passing (599 baseline + 10 new)
```

## Deferrals / known issues

- **No UI** — backend only, matching every other phase's sequencing.
- **No holiday bucket** in `attendance_breakdown` — this codebase has no
  holiday-calendar concept to derive one from; the prompt's illustrative
  example included one, this implementation doesn't invent the data source.
- **`attendance-summary`'s per-employee list shape** is a structural
  adaptation (see above), not a UI-level choice — a true multi-employee
  batch-period model would be a separate, larger change to `PayrollPeriod`
  itself.
