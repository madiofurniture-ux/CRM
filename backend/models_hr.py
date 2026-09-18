"""
HR: Attendance -> Payroll models for the canonical /api/v1 surface.

This is a NEW, separate layer — it does not touch `backend/server.py`'s
existing `attendance` collection or its geofenced check-in/check-out flow.
That collection's `status` field already carries a different, actively-used
vocabulary ("present" / "flagged_out_of_bounds" / "regularized", consumed by
/attendance/{id}/regularize and /attendance/{id}/mark-absent) — writing this
module's Present/Late/HalfDay/Overtime/Absent into the same field would
silently corrupt it. So this module's attendance log lives in its own
collection (hr_attendance_logs, see api_hr.py), for manual/backfill HR entry
rather than field geofence punches.

PayrollPeriod is the genuinely new piece: server.py's /payroll/calculate is
stateless (recomputed every call, nothing to fetch by id or approve). This
adds a persisted, approvable run (Draft -> Approved -> Paid) built with the
SAME pay arithmetic server.py already uses (compute_gross_pay,
_aggregate_effective_days), imported lazily at call time in api_hr.py to
avoid a circular import with server.py.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal
from datetime import datetime

from models_canonical import new_id, now_iso  # reuse — identical helpers already exist there

ATTENDANCE_STATUSES = ["Present", "Late", "HalfDay", "Overtime", "Absent"]
PAYROLL_STATUSES = ["Draft", "Approved", "Paid"]
LEAVE_STATUSES = ["Pending", "Approved", "Rejected"]
LEAVE_TYPES = ["Paid", "Unpaid"]

# ponytail: no per-employee/OfficeSettings shift config yet — one default for
# every employee. Add a configurable shift_start when a brand actually needs one.
DEFAULT_SHIFT_START = "09:30"
FULL_DAY_HOURS = 4.0       # mirrors server.py's PAYROLL_FULL_DAY_MIN (4h)
STANDARD_DAY_HOURS = 8.0   # mirrors server.py's STANDARD_WORKDAY_MIN (8h)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def attendance_status(
    check_in: Optional[str], check_out: Optional[str], total_hours: float,
    *, shift_start: str = DEFAULT_SHIFT_START,
    full_day_hours: float = FULL_DAY_HOURS, standard_day_hours: float = STANDARD_DAY_HOURS,
) -> str:
    """One of ATTENDANCE_STATUSES for a single day's log.

    Overtime beats HalfDay beats Late beats Present — a day worked past the
    standard day is Overtime even if the person also arrived late; a day
    short of a full day is HalfDay regardless of arrival time.
    """
    t_in = _parse_iso(check_in)
    if not t_in:
        return "Absent"
    if total_hours > standard_day_hours:
        return "Overtime"
    if check_out and total_hours < full_day_hours:
        return "HalfDay"
    hh, mm = (int(x) for x in shift_start.split(":"))
    if (t_in.hour, t_in.minute) > (hh, mm):
        return "Late"
    return "Present"


# ------- Attendance log (manual/backfill entry, hr_attendance_logs) -------
class AttendanceLogCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str
    date: str                          # YYYY-MM-DD
    check_in: Optional[str] = None     # ISO datetime
    check_out: Optional[str] = None    # ISO datetime
    brand_id: Optional[str] = ""
    note: Optional[str] = ""


class AttendanceLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    employee_id: str
    date: str
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    total_hours: float = 0.0
    status: str = "Absent"
    brand_id: Optional[str] = ""
    note: Optional[str] = ""
    tenant_id: str
    created_at: str
    updated_at: str


# ------- Leave request (leave_requests) -------
class LeaveRequestCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str
    date_from: str                     # YYYY-MM-DD, inclusive
    date_to: str                       # YYYY-MM-DD, inclusive
    leave_type: Literal["Paid", "Unpaid"] = "Unpaid"
    reason: Optional[str] = ""


class LeaveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    employee_id: str
    date_from: str
    date_to: str
    leave_type: Literal["Paid", "Unpaid"] = "Unpaid"
    status: Literal["Pending", "Approved", "Rejected"] = "Pending"
    reason: Optional[str] = ""
    tenant_id: str
    created_at: str
    updated_at: str


class LeaveStatusUpdate(BaseModel):
    status: Literal["Approved", "Rejected"]


def overlap_days(a_start: str, a_end: str, b_start: str, b_end: str) -> int:
    """Inclusive day count where [a_start, a_end] and [b_start, b_end] overlap.
    Used to find how many days of a leave request fall inside a payroll period."""
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    if lo > hi:
        return 0
    return (datetime.fromisoformat(hi).date() - datetime.fromisoformat(lo).date()).days + 1


# ------- Payroll period (persisted payroll run, payroll_periods) -------
class PayrollPeriodCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    employee_id: str
    period_start: str                  # YYYY-MM-DD
    period_end: str                    # YYYY-MM-DD
    brand_id: Optional[str] = ""
    working_days_in_period: Optional[int] = None  # None -> calendar days in the range
    deductions: float = 0.0
    bonuses: float = 0.0


class BulkPayrollCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    period_start: str
    period_end: str
    brand_id: Optional[str] = ""
    dry_run: bool = False


class PayrollPeriod(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    employee_id: str
    period_start: str
    period_end: str
    brand_id: Optional[str] = ""
    total_working_hours: float = 0.0
    total_overtime_hours: float = 0.0
    late_count: int = 0
    gross_pay: float = 0.0
    deductions: float = 0.0
    bonuses: float = 0.0
    leave_days_deducted: float = 0.0
    incentive_bonus: float = 0.0
    net_salary: float = 0.0
    status: Literal["Draft", "Approved", "Paid"] = "Draft"
    tenant_id: str
    created_at: str
    updated_at: str


class PayrollStatusUpdate(BaseModel):
    status: Literal["Draft", "Approved", "Paid"]


def demo() -> None:
    """ponytail self-check — run `python models_hr.py`."""
    assert attendance_status(None, None, 0.0) == "Absent"
    assert attendance_status("2026-09-18T09:00:00+00:00", "2026-09-18T17:00:00+00:00", 8.0) == "Present"
    assert attendance_status("2026-09-18T10:15:00+00:00", "2026-09-18T17:00:00+00:00", 6.75) == "Late"
    assert attendance_status("2026-09-18T09:00:00+00:00", "2026-09-18T11:00:00+00:00", 2.0) == "HalfDay"
    assert attendance_status("2026-09-18T09:00:00+00:00", "2026-09-18T20:00:00+00:00", 11.0) == "Overtime"
    assert overlap_days("2026-09-10", "2026-09-15", "2026-09-01", "2026-09-30") == 6
    assert overlap_days("2026-08-25", "2026-09-02", "2026-09-01", "2026-09-30") == 2
    assert overlap_days("2026-10-01", "2026-10-05", "2026-09-01", "2026-09-30") == 0
    print("models_hr.demo: all assertions passed")


if __name__ == "__main__":
    demo()
