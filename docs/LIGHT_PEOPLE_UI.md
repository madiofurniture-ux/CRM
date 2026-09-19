# Light Theme — Attendance & Payroll

People-experience follow-up to `docs/LIGHT_SALES_UI.md`: Attendance and
Payroll migrated to the light design tokens/components. Same rule as
every prior page: one file per page, token-driven, correct under both
`baseplate` and `light` — no per-theme fork.

## Routes / files / APIs / permissions

| Page | Route (unchanged) | File | Backend API | Gate |
|---|---|---|---|---|
| Attendance | `/attendance` | `frontend/src/pages/Attendance.jsx` | `GET/POST /attendance`, `GET /attendance/geofence`, `POST /attendance/check-in`, `POST /attendance/check-out` | any authenticated user (own rows); `user_id` cross-query is `role === "admin"` only, literal backend check (`server.py:3475`) |
| Attendance exception detail | side drawer | `frontend/src/components/AttendanceExceptionDrawer.jsx` | `GET /attendance/{id}/raw` (admin), `POST /attendance/{id}/regularize` (admin), `POST /attendance/{id}/mark-absent` (admin) | `require_admin` (backend, unchanged) — drawer already gated this correctly before this pass |
| Payroll | `/people/payroll` | `frontend/src/pages/PayrollPage.jsx` | `GET /v1/payroll`, `POST /v1/payroll/calculate`, `POST /v1/payroll/{id}/status`, `POST /v1/payroll/{id}/unlock-attendance`, `GET /v1/payroll/{id}/attendance-summary` | `api_hr.py`'s `_require_payroll(action)` — role-configured `payroll` module grant, or `role in ("admin","accountant")` literal bypass |

No route URLs changed. No payroll arithmetic, approval rule, attendance
semantics, or regularization behavior was touched — every number shown
comes straight from the existing API response fields
(`payable_days`/`lop_days`/`overtime_hours`/`lop_deduction`/
`overtime_pay`/`net_salary`/`status`/`attendance_exceptions`/
`attendance_locked`), computed exactly as before by `api_hr.py`'s
`_calculate_payroll`/`_attendance_breakdown`.

## Two attendance systems — not merged, per "preserve existing semantics"

This codebase has **two separate attendance collections** that were never
unified, and this pass didn't unify them either:

1. **`attendance`** (`server.py`) — the geofenced punch-clock system
   `Attendance.jsx` has always used (`check_in_at`/`check_out_at`/
   `check_in_within`/`status` of `present`/`flagged_out_of_bounds`/
   `regularized`/`absent`). No "Late" or per-row "LOP" concept exists here.
2. **`hr_attendance_logs`** (`api_hr.py`) — a distinct collection feeding
   `payable_days`/`lop_days`/`overtime_hours` into Payroll, with its own
   `status` enum (`Present`/`Late`/`HalfDay`/`Overtime`/`Absent`).

`Attendance.jsx` was left reading `attendance` (unchanged data source);
`PayrollPage.jsx` was left reading `hr_attendance_logs` via the existing
`/v1/payroll*` endpoints (unchanged data source). Neither was switched to
the other — doing so would be a semantics change the brief explicitly
forbids ("preserve existing legacy attendance status meanings").

## Attendance — what's real, what's honestly omitted

Summary cards (`Present`/`Absent`/`Overtime`/`Open exceptions`) are
computed client-side from the same rows the page already fetches for the
selected range — no new endpoint, no fabricated number:

- **Present**: rows with a `check_in_at` and `status !== "absent"`.
- **Absent**: rows with `status === "absent"` (explicitly marked, not a
  calendar-inferred absence — there's no roster/calendar in this system to
  infer against).
- **Overtime**: `sum(max(0, duration_min - 480)) / 60` across rows with a
  completed check-out, mirroring `server.py`'s own
  `_aggregate_effective_days` formula for the same collection.
- **Open exceptions**: rows flagged `flagged_out_of_bounds` or missing a
  checkout on a past day, not yet `regularized`/`absent`.

**"Late" and "LOP" cards were not added** — this attendance system (the
`attendance` collection) has no late-detection logic and no LOP concept at
all (LOP only exists in the *other* collection, `hr_attendance_logs`,
surfaced instead on the Payroll page where it's actually computed). Adding
either here would be inventing data, which the brief explicitly forbids.

**Filters**: `days` (7/30/90) and admin-only `user_id` are the two real
query params `GET /attendance` supports (`server.py:3460`) — there is no
`date_from`/`date_to` range on this endpoint, so "date range" in the UI is
the *days* selector, not a fabricated two-date picker.

**No Holiday data** — confirmed no holiday-calendar concept exists
anywhere in `server.py`/`api_hr.py`; none was added or implied.

## Payroll — what's real, what's permission-gated

- **Calculate Payroll** — only rendered when `canDo("payroll", "create")`.
- **Approve / Mark Paid** — only rendered when `canDo("payroll", "approve")`,
  and only for the status transition the backend actually allows next
  (`Draft` → `Approved` → `Paid`, matching `PAYROLL_STATUSES` exactly — no
  status this UI can produce that the backend doesn't already accept).
- **Attendance exceptions** — shown as an inline warning strip on every
  `Draft` row with a non-empty `attendance_exceptions` array, **never
  hidden**. The plain "Approve" button only appears when there are zero
  exceptions; with exceptions present, only an "Override and approve
  anyway" flow appears (still `payroll:approve`-gated), which requires a
  typed reason and sends `override_attendance_exceptions: true` +
  `override_reason` to the existing `POST /status` endpoint — the exact
  override mechanism `api_hr.py` already implements
  (`lc.payroll_approval_blocked`), not a new one.
- **Unlock attendance** — only rendered when `payroll:approve` **and** the
  row is `Draft` **and** `attendance_locked`, calling the existing
  `POST /unlock-attendance`.
- **"Live attendance summary"** expand-per-row calls the existing
  `GET /payroll/{id}/attendance-summary` on demand — a fresh re-check
  against current attendance state, distinct from the `payable_days`/
  `lop_days`/`overtime_hours` already persisted on the period (which is
  what the main row's columns show). Both are labeled distinctly so
  neither is mistaken for the other.
- **No bulk-calculate UI** — `POST /v1/payroll/bulk-calculate` exists
  backend-side, but the pre-existing frontend never exposed it and this
  pass didn't add it either, per the brief's "do not expose a bulk payroll
  action if the backend remains per-employee" — the *existing* UI flow is
  per-employee, and introducing a new bulk-run workflow is a feature
  addition outside a styling/states migration's scope.

## A real defect found and fixed (backend, one line)

**`"payroll"` was never in `server.py`'s `ALL_MODULE_IDS`** — the list
`TENANT_CONFIG_DEFAULTS["enabled_modules"]` falls back to for every tenant
without a custom override (confirmed: no tenant in the real database has
one). `AuthContext.canAccess()` checks `tenant.enabled_modules` **before**
its `role === "admin"` bypass, so `/people/payroll` returned "No access"
for every single user on every tenant, including admins — found live
during this task's own required admin smoke test. Fixed by adding
`"payroll"` to that one list (`server.py:834`) — no payroll arithmetic,
approval rule, or any other logic touched; 623 backend tests still pass
unchanged.

## Frontend RBAC fix: `payroll`/`leave` added to `AuthContext.GATED_MODULES`

Before this pass, `canDo("payroll", action)` couldn't consult a role's
actual configured `payroll` permission grant at all — `"payroll"` wasn't
in `GATED_MODULES`, so it fell straight to the legacy
"non-approve/export-is-implicit" branch regardless of what a role_id
account was actually granted. Added `"payroll"`/`"leave"` to
`GATED_MODULES`, plus an `admin`/`accountant`-literal bypass mirroring
`api_hr.py`'s own `_can_hr()` exactly (the one HR-specific role floor this
codebase has always had). Verified live: a role granted only
`payroll:view` sees the list but no Calculate/Approve/Paid/Unlock controls;
the backend independently rejects a direct `POST /status`/`POST
/calculate` attempt from that same account with `403`, proving the UI gate
isn't the only thing standing between a restricted user and those actions.

## Manual test checklist (what was actually run this pass)

Environment: one backend (port 8001 turned out to be an unkillable
pre-existing process from outside this session, same as the port-8000
situation in an earlier pass — moved to port **8002** for a verifiably
clean process instead, exactly as documented in
`docs/LIGHT_SALES_UI.md`'s own "Manual test checklist"), one frontend dev
server, `REACT_APP_UI_THEME` toggled between runs.

- [x] `CI=true npm run build` (baseplate) — Compiled successfully
- [x] `CI=true REACT_APP_UI_THEME=light npm run build` — Compiled successfully
- [x] `python -m pytest tests/ -q` — 623 passed, unchanged
- [x] `python -m pytest tests/test_tenant_isolation_api.py tests/test_tenancy.py -q` — 26 passed
- [x] Login → Attendance (light theme): real Present/Absent/Overtime/Open-exceptions counts, real 4-row history table with correct Worked-hours/Status columns, exception row opens the drawer with real GPS-distance/selfie outcome data
- [x] Calculate Payroll (admin, light theme) → real Gross Pay/Payable Days/LOP Days/OT Hours/LOP Deduction/OT Pay/Net Pay for a seeded employee, `Draft` status with lock icon
- [x] Approve → `Approved` badge; Mark Paid → `Paid` badge — full status lifecycle against the real backend
- [x] "Live attendance summary" row-expand → real `GET .../attendance-summary` call, correct payable/LOP/OT figures
- [x] **Restricted (view-only `payroll:view` only) role** → Payroll list visible, **no** Calculate/Approve/Paid/Unlock controls rendered; direct `POST /v1/payroll/{id}/status` and `POST /v1/payroll/calculate` from that account's own token → backend `403` both times
- [x] **Empty tenant** → Attendance all-zero summary + empty state, Payroll "No payroll runs yet" — no leakage of the populated tenant's data
- [x] Logout → redirected to `/login`, `localStorage` cleared
- [x] Browser console checked after every navigation — 0 errors
- [x] Baseplate fallback re-verified after the People-page changes — pixel-identical dark header/pill nav, same data, same layout underneath (token aliasing working as designed)

All QA fixtures (2 tenants, 4 users, 1 role, 4 attendance rows, 2
`hr_attendance_logs` rows, 1 payroll period) seeded directly into the real
local dev database for this test were deleted afterward — nothing
pre-existing was modified.

## Rollback

Same as every prior light-theme pass: unset `REACT_APP_UI_THEME` (or set
it to anything but `light`) and rebuild — `Header.jsx`/`baseplateNav.js`
untouched, every `--color-*` token these two pages reference resolves to
the exact baseplate-equivalent value in `:root`. The `ALL_MODULE_IDS`
defect fix and the `GATED_MODULES`/`canDo` permission work are
correctness fixes, not visual ones, and apply under **both** themes — no
rollback path un-does them, nor should one need to.
