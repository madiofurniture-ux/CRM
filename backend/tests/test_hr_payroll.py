"""Phase 4 (docs/FEATURE_ROADMAP.md): LeaveRequest reducing effective_days,
commission_payouts auto-reaching a payroll period, and bulk payroll dry-run.

Same direct-call + mongomock pattern as tests/test_project_tracking.py, but
api_hr.py's handlers take a FastAPI `Request` (they read the db off
`request.app.state.db`), so a tiny stand-in object is used instead of a real
Request/TestClient.
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
from models_hr import (  # noqa: E402
    AttendanceLogCreate, PayrollPeriodCreate, LeaveRequestCreate,
    LeaveStatusUpdate, BulkPayrollCreate,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
EMP = {"id": "e1", "tenant_id": "acme", "name": "Ravi Kumar", "role": "user"}
OTHER_TENANT_ADMIN = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


@pytest.fixture()
def db(monkeypatch):
    mock_db = AsyncMongoMockClient()["hr_payroll_test"]
    monkeypatch.setattr(server, "db", mock_db)
    return mock_db


async def _seed_employee(db, **overrides):
    doc = {"id": "e1", "tenant_id": "acme", "name": "Ravi Kumar", "role": "user",
           "pay_model": "monthly", "base_pay_rate": 30000.0,
           "overtime_eligible": False, "overtime_rate_multiplier": 1.0, "active": True}
    doc.update(overrides)
    await db.users.insert_one(dict(doc))
    return doc


async def _log_attendance(db, employee_id, date, check_in="09:00:00", check_out="17:00:00"):
    return await api_hr.log_attendance(
        AttendanceLogCreate(employee_id=employee_id, date=date,
                             check_in=f"{date}T{check_in}+00:00",
                             check_out=f"{date}T{check_out}+00:00"),
        _req(db), user=ADMIN)


def test_leave_request_self_service_create_and_others_forbidden(db):
    async def run():
        leave = await api_hr.create_leave_request(
            LeaveRequestCreate(employee_id="e1", date_from="2026-09-10", date_to="2026-09-12"),
            _req(db), user=EMP)
        assert leave["status"] == "Pending"

        with pytest.raises(HTTPException) as exc:
            await api_hr.create_leave_request(
                LeaveRequestCreate(employee_id="someone-else", date_from="2026-09-10", date_to="2026-09-12"),
                _req(db), user=EMP)
        assert exc.value.status_code == 403
    asyncio.run(run())


def test_leave_requests_do_not_cross_a_tenant_boundary(db):
    """Regression guard: leave_requests was missing from
    tenancy.TENANT_COLLECTIONS when first added — scope()/stamp() silently
    skipped tenant filtering for it entirely (found and fixed this pass)."""
    async def run():
        await api_hr.create_leave_request(
            LeaveRequestCreate(employee_id="e1", date_from="2026-09-10", date_to="2026-09-12"),
            _req(db), user=ADMIN)
        globex_view = await api_hr.list_leave_requests(request=_req(db), user=OTHER_TENANT_ADMIN)
        assert globex_view == []

        stored = await db.leave_requests.find_one({}, {"_id": 0})
        assert stored["tenant_id"] == "acme"
    asyncio.run(run())


def test_approved_unpaid_leave_reduces_payroll_effective_days(db):
    async def run():
        await _seed_employee(db)
        for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
            await _log_attendance(db, "e1", d)

        no_leave = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-30"),
            _req(db), user=ADMIN)
        assert no_leave["leave_days_deducted"] == 0.0

        leave = await api_hr.create_leave_request(
            LeaveRequestCreate(employee_id="e1", date_from="2026-09-02", date_to="2026-09-03",
                                leave_type="Unpaid"),
            _req(db), user=ADMIN)
        await api_hr.set_leave_status(leave["id"], LeaveStatusUpdate(status="Approved"), _req(db), user=ADMIN)

        with_leave = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-30"),
            _req(db), user=ADMIN)
        assert with_leave["leave_days_deducted"] == 2.0
        assert with_leave["gross_pay"] < no_leave["gross_pay"]
    asyncio.run(run())


def test_earned_commission_payout_reaches_payroll_without_manual_entry(db):
    async def run():
        await _seed_employee(db)
        await _log_attendance(db, "e1", "2026-09-01")
        await db.commission_payouts.insert_one({
            "id": "cp1", "tenant_id": "acme", "payee": "Ravi Kumar", "payee_type": "user",
            "commission_amount": 1500.0, "status": "Earned", "project_id": "p1",
        })

        result = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-30"),
            _req(db), user=ADMIN)
        assert result["incentive_bonus"] == 1500.0
        assert result["net_salary"] == round(result["gross_pay"] + 1500.0, 2)

        payout = await db.commission_payouts.find_one({"id": "cp1"}, {"_id": 0})
        assert payout["status"] == "Included"
        assert payout["payroll_period_id"] == result["id"]

        # a second run must not double-count the now-Included payout
        again = await api_hr.payroll_calculate(
            PayrollPeriodCreate(employee_id="e1", period_start="2026-09-01", period_end="2026-09-30"),
            _req(db), user=ADMIN)
        assert again["incentive_bonus"] == 0.0
    asyncio.run(run())


def test_bulk_calculate_dry_run_previews_without_persisting(db):
    async def run():
        await _seed_employee(db, id="e1", name="Ravi Kumar")
        await _seed_employee(db, id="e2", name="Meena")
        await _log_attendance(db, "e1", "2026-09-01")
        await _log_attendance(db, "e2", "2026-09-01")

        preview = await api_hr.payroll_bulk_calculate(
            BulkPayrollCreate(period_start="2026-09-01", period_end="2026-09-30", dry_run=True),
            _req(db), user=ADMIN)
        assert preview["dry_run"] is True
        assert preview["count"] == 2
        assert await db.payroll_periods.count_documents({}) == 0

        real = await api_hr.payroll_bulk_calculate(
            BulkPayrollCreate(period_start="2026-09-01", period_end="2026-09-30", dry_run=False),
            _req(db), user=ADMIN)
        assert real["count"] == 2
        assert await db.payroll_periods.count_documents({}) == 2
    asyncio.run(run())
