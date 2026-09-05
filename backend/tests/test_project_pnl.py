"""Tests for the Project Profitability / Petty Cash P&L aggregation
(csv_engine.compute_project_pnl) — revenue-vs-approved-spend margin math,
pending-exposure accounting, and cross-tenant isolation. Same pattern as
tests/test_petty_cash.py: real functions, server.db monkeypatched to
mongomock.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
from models import CashbookExpense, CashbookEntryApproval  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["project_pnl_test"])
    yield


async def _make_project(user=ADMIN, **overrides):
    doc = {"project_no": "PRJ-1", "customer": "Acme Co", "value": 100000, "paid": 0,
           "stage": "Execution", "id": "p1", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    from tenancy import stamp
    stamp(doc, "projects", user)
    await server.db.projects.insert_one(dict(doc))
    return doc


async def _make_book(user=ADMIN, **overrides):
    doc = {"book_name": "Site Wallet", "initial_balance": 20000, "current_balance": 20000,
           "status": "ACTIVE", "assigned_users": [], "project_id": "", "imprest_limit": 0,
           "strict_overdraft": False, "id": "b1", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    from tenancy import stamp
    stamp(doc, "cashbooks", user)
    await server.db.cashbooks.insert_one(dict(doc))
    return doc


def test_margin_uses_only_approved_spend():
    async def run():
        await _make_project(id="p1", value=100000)
        await _make_book(id="b1", project_id="p1", current_balance=20000)
        e1 = await server.cashbook_expense("b1", CashbookExpense(amount=15000, category="Materials"), user=ADMIN)
        await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        await server.cashbook_expense("b1", CashbookExpense(amount=9999, category="Labor"), user=ADMIN)  # left Pending

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["contract_value"] == 100000
        assert row["approved_petty_cash"] == 15000
        assert row["gross_profit"] == 85000
        assert row["margin_pct"] == 85.0
    asyncio.run(run())


def test_pending_excluded_from_margin_but_counted_in_exposure():
    async def run():
        await _make_project(id="p1", value=50000)
        await _make_book(id="b1", project_id="p1")
        await server.cashbook_expense("b1", CashbookExpense(amount=8000, category="Tools"), user=ADMIN)  # Pending

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["approved_petty_cash"] == 0
        assert row["gross_profit"] == 50000  # unaffected by the pending expense
        assert row["margin_pct"] == 100.0
        assert row["pending_petty_cash"] == 8000
        assert pnl["summary"]["pending_exposure"] == 8000
        assert pnl["summary"]["total_field_cash_spent"] == 0
    asyncio.run(run())


def test_category_breakdown_only_includes_approved_entries():
    async def run():
        await _make_project(id="p1", value=100000)
        await _make_book(id="b1", project_id="p1")
        e1 = await server.cashbook_expense("b1", CashbookExpense(amount=3000, category="Materials"), user=ADMIN)
        await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        await server.cashbook_expense("b1", CashbookExpense(amount=4000, category="Logistics"), user=ADMIN)  # Pending

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        breakdown = pnl["projects"][0]["category_breakdown"]
        assert breakdown == [{"category": "Materials", "amount": 3000}]
    asyncio.run(run())


def test_aggregate_summary_sums_across_projects():
    async def run():
        await _make_project(id="p1", value=100000)
        await _make_project(id="p2", value=50000, project_no="PRJ-2")
        await _make_book(id="b1", project_id="p1", current_balance=10000)
        await _make_book(id="b2", project_id="p2", current_balance=5000)
        e1 = await server.cashbook_expense("b1", CashbookExpense(amount=10000), user=ADMIN)
        await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        e2 = await server.cashbook_expense("b2", CashbookExpense(amount=5000), user=ADMIN)
        await server.cashbook_entry_approve(e2["id"], CashbookEntryApproval(approved=True), user=ADMIN)

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        summary = pnl["summary"]
        assert summary["total_contract_revenue"] == 150000
        assert summary["total_field_cash_spent"] == 15000
        assert summary["aggregate_margin_pct"] == 90.0
    asyncio.run(run())


def test_project_with_no_cashbook_has_full_margin():
    async def run():
        await _make_project(id="p1", value=75000)
        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["wallet_count"] == 0
        assert row["approved_petty_cash"] == 0
        assert row["margin_pct"] == 100.0
    asyncio.run(run())


def test_zero_revenue_project_does_not_divide_by_zero():
    async def run():
        await _make_project(id="p1", value=0)
        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["margin_pct"] == 0.0
        assert pnl["summary"]["aggregate_margin_pct"] == 0.0
    asyncio.run(run())


def test_tenant_isolation_cannot_see_another_tenants_projects_or_margins():
    async def run():
        await _make_project(user=ADMIN, id="p1", value=100000)  # tenant "acme"
        await _make_book(user=ADMIN, id="b1", project_id="p1")
        e1 = await server.cashbook_expense("b1", CashbookExpense(amount=20000), user=ADMIN)
        await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)

        await _make_project(user=OTHER_TENANT_ADMIN, id="p2", value=999999, project_no="PRJ-GLOBEX")

        pnl_acme = await csv_engine.compute_project_pnl(server.db, ADMIN)
        assert [p["project_id"] for p in pnl_acme["projects"]] == ["p1"]
        assert pnl_acme["summary"]["total_contract_revenue"] == 100000

        pnl_globex = await csv_engine.compute_project_pnl(server.db, OTHER_TENANT_ADMIN)
        assert [p["project_id"] for p in pnl_globex["projects"]] == ["p2"]
        assert pnl_globex["summary"]["total_contract_revenue"] == 999999
        assert pnl_globex["summary"]["total_field_cash_spent"] == 0  # never sees acme's spend
    asyncio.run(run())


def test_route_returns_summary_and_projects():
    async def run():
        await _make_project(id="p1", value=100000)
        result = await server.project_pnl_report(user=ADMIN)
        assert "summary" in result and "projects" in result
    asyncio.run(run())
