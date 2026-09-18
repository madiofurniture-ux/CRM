"""Attendance -> Payroll linkage (prompt_2_attendance_payroll_link.md).

Same direct-call + mongomock + SimpleNamespace-Request pattern as
tests/test_hr_payroll.py.
"""
import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402 — payroll_calculate lazily imports this
import api_hr  # noqa: E402
import tenancy  # noqa: E402
from models_hr import (  # noqa: E402
    AttendanceLogCreate, PayrollPeriodCreate, PayrollStatusUpdate,
    ImportAttendanceRequest, UnlockAttendanceRequest,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}

DIVISION_HEAD_ROLE = {"id": "r1", "name": "Division Head", "permissions": [
    {"module": "payroll", "view": True, "create": True, "edit": True, "delete": False,
     "approve": True, "export": False, "scope": "all"},
]}
DIVISION_HEAD = {"id": "u3", "tenant_id": "acme", "name": "Div Head", "role": "user", "role_id": "r1"}

# No role_id — legacy account. LEGACY_IMPLICIT_ACTIONS covers view/create/
# edit/delete, but never "approve" (permissions.py), so this user can
# calculate payroll but not approve/unlock it — the RBAC floor the tests
# below rely on.
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


@pytest.fixture()
def db(monkeypatch):
    mock_db = AsyncMongoMockClient()["attendance_payroll_link_test"]
    monkeypatch.setattr(server, "db", mock_db)
    return mock_db


async def _seed_employee(db, **overrides):
    doc = {"id": "e1", "tenant_id": "acme", "name": "Ravi Kumar", "role": "user",
           "pay_model": "monthly", "base_pay_rate": 30000.0,
           "overtime_eligible": False, "overtime_rate_multiplier": 1.0, "active": True}
    doc.update(overrides)
    await db.users.insert_one(dict(doc))
    return doc


async def _seed_role(db, role):
    doc = dict(role)
    tenancy.stamp(doc, "roles", ADMIN)
    await db.roles.insert_one(doc)


async def _log(db, employee_id, date, check_in="09:00:00", check_out="17:00:00"):
    return await api_hr.log_attendance(
        AttendanceLogCreate(employee_id=employee_id, date=date,
                            check_in=f"{date}T{check_in}+00:00" if check_in else None,
                            check_out=f"{date}T{check_out}+00:00" if check_out else None),
        _req(db), user=ADMIN)


# --------------------------------------------------------- 1/4. payable days
def test_import_calculates_payable_days_correctly(db):
    async def run():
        await _seed_employee(db)
        for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
            await _log(db, "e1", d)
        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-03"),
            _req(db), user=ADMIN)
        assert result["payable_days"] == 3.0
        assert result["lop_days"] == 0.0
        assert result["attendance_imported"] is True
        assert result["attendance_locked"] is True
    asyncio.run(run())


# ------------------------------------------------------------- 2. LOP days
def test_lop_days_calculated_from_unapproved_absences(db):
    async def run():
        await _seed_employee(db)
        await _log(db, "e1", "2026-09-01")  # only day 1 logged; 2 and 3 are unlogged -> Absent, no leave
        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-03"),
            _req(db), user=ADMIN)
        assert result["payable_days"] == 1.0
        assert result["lop_days"] == 2.0
        assert result["attendance_breakdown"]["LOP"] == 2
    asyncio.run(run())


# --------------------------------------------------------- 3. overtime sum
def test_overtime_hours_sum_correctly(db):
    async def run():
        await _seed_employee(db, overtime_eligible=True)
        await _log(db, "e1", "2026-09-01", check_out="20:00:00")  # 11h -> Overtime, 3h OT
        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-01"),
            _req(db), user=ADMIN)
        assert result["overtime_hours"] == 3.0
        assert result["attendance_breakdown"]["Overtime"] == 1
    asyncio.run(run())


# --------------------------------------------------------- 5. LOP deduction
def test_lop_deduction_calculated_correctly(db):
    async def run():
        await _seed_employee(db, base_pay_rate=30000.0)  # day_rate = 30000/3 = 10000 for a 3-day period
        await _log(db, "e1", "2026-09-01")
        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-03"),
            _req(db), user=ADMIN)
        assert result["lop_days"] == 2.0
        assert result["lop_deduction"] == 20000.0  # (30000/3) * 2
    asyncio.run(run())


# ---------------------------------------------------------- 6. OT pay
def test_overtime_pay_calculated_correctly(db):
    async def run():
        await _seed_employee(db, base_pay_rate=24000.0, overtime_eligible=True,
                             overtime_rate_multiplier=1.5)
        await _log(db, "e1", "2026-09-01", check_out="20:00:00")  # 3h OT
        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-01"),
            _req(db), user=ADMIN)
        day_rate = 24000.0 / 1  # single-day period
        hourly_rate = day_rate / 8.0
        expected_ot_pay = round(hourly_rate * 3.0 * 1.5, 2)
        assert result["overtime_pay"] == expected_ot_pay
    asyncio.run(run())


# ------------------------------------------------- 7/8. exceptions gate
async def _seed_period_with_late_exception(db):
    await _seed_employee(db)
    await _log(db, "e1", "2026-09-01", check_in="10:15:00", check_out="17:00:00")  # Late
    return await api_hr.payroll_calculate(
        PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-01"),
        _req(db), user=ADMIN)


def test_payroll_blocked_when_attendance_exceptions_exist(db):
    async def run():
        period = await _seed_period_with_late_exception(db)
        assert period["attendance_exceptions"]
        with pytest.raises(HTTPException) as exc:
            await api_hr.payroll_set_status(
                period["id"], PayrollStatusUpdate(status="Approved"), _req(db), user=ADMIN)
        assert exc.value.status_code == 400
        assert "exceptions" in exc.value.detail
    asyncio.run(run())


def test_override_approval_works_for_division_head_role(db):
    async def run():
        await _seed_role(db, DIVISION_HEAD_ROLE)
        period = await _seed_period_with_late_exception(db)
        out = await api_hr.payroll_set_status(
            period["id"],
            PayrollStatusUpdate(status="Approved", override_attendance_exceptions=True,
                                override_reason="Reviewed with employee"),
            _req(db), user=DIVISION_HEAD)
        assert out["status"] == "Approved"
    asyncio.run(run())


# ----------------------------------------------------- 9. unlock gating
def test_attendance_unlock_requires_division_head(db):
    async def run():
        await _seed_role(db, DIVISION_HEAD_ROLE)
        period = await _seed_period_with_late_exception(db)
        assert period["attendance_locked"] is True

        with pytest.raises(HTTPException) as exc:
            await api_hr.payroll_unlock_attendance(
                period["id"], UnlockAttendanceRequest(reason="test"), _req(db), user=LEGACY_USER)
        assert exc.value.status_code == 403

        out = await api_hr.payroll_unlock_attendance(
            period["id"], UnlockAttendanceRequest(reason="Attendance corrected"), _req(db), user=DIVISION_HEAD)
        assert out["attendance_locked"] is False
    asyncio.run(run())


# ---------------------------------------------------- 10. tenant isolation
def test_tenant_isolation_cannot_see_other_tenants_attendance_in_payroll(db):
    async def run():
        period = await _seed_period_with_late_exception(db)
        with pytest.raises(HTTPException) as exc:
            await api_hr.payroll_get(period["id"], _req(db), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await api_hr.payroll_attendance_summary(period["id"], _req(db), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


# ------------------------------------------------------ 11. backward compat
def test_existing_payroll_period_without_attendance_import_still_reads(db):
    """A period persisted before this feature existed has none of the new
    keys at all — payroll_get must not KeyError/validate-fail on it, and
    its pre-existing gross_pay/net_salary/status fields must round-trip
    unchanged (no response_model reshaping on this route)."""
    async def run():
        legacy_doc = {
            "id": "legacy1", "employee_id": "e1", "period_start": "2026-01-01",
            "period_end": "2026-01-31", "gross_pay": 30000.0, "net_salary": 30000.0,
            "status": "Paid", "tenant_id": "acme",
            "created_at": "2026-01-31T00:00:00+00:00", "updated_at": "2026-01-31T00:00:00+00:00",
        }
        await db.payroll_periods.insert_one(dict(legacy_doc))
        out = await api_hr.payroll_get("legacy1", _req(db), user=ADMIN)
        assert out["gross_pay"] == 30000.0
        assert out["net_salary"] == 30000.0
        assert out["status"] == "Paid"
        assert "payable_days" not in out  # never backfilled — additive fields, not retrofit
    asyncio.run(run())
