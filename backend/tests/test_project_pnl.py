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
from models import CashbookExpense, CashbookEntryApproval, CashbookTopUp  # noqa: E402

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
        assert pnl["summary"]["total_field_settlement_spend"] == 0
    asyncio.run(run())


def test_recent_entries_include_both_cash_in_and_cash_out():
    async def run():
        await _make_project(id="p1", value=100000)
        await _make_book(id="b1", project_id="p1", current_balance=10000)
        await server.cashbook_top_up("b1", CashbookTopUp(amount=2000), user=ADMIN)
        await server.cashbook_expense("b1", CashbookExpense(amount=1500, category="Fuel", entry_person="Ravi"), user=ADMIN)

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        recent = pnl["projects"][0]["recent_entries"]
        assert len(recent) == 2
        types = {r["type"] for r in recent}
        assert types == {"CASH_IN", "CASH_OUT"}
        payout = next(r for r in recent if r["type"] == "CASH_OUT")
        assert payout["payee"] == "Ravi"
        assert payout["amount"] == 1500
    asyncio.run(run())


def test_imprest_limit_total_sums_across_project_wallets():
    async def run():
        await _make_project(id="p1", value=100000)
        await _make_book(id="b1", project_id="p1", imprest_limit=5000)
        await _make_book(id="b2", project_id="p1", imprest_limit=3000)

        pnl = await csv_engine.compute_project_pnl(server.db, ADMIN)
        row = pnl["projects"][0]
        assert row["imprest_limit_total"] == 8000
        assert set(row["wallet_ids"]) == {"b1", "b2"}
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
        assert summary["total_field_settlement_spend"] == 15000
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
        assert pnl_globex["summary"]["total_field_settlement_spend"] == 0  # never sees acme's spend
    asyncio.run(run())


def test_route_returns_summary_and_projects():
    async def run():
        await _make_project(id="p1", value=100000)
        result = await server.project_pnl_report(user=ADMIN)
        assert "summary" in result and "projects" in result
    asyncio.run(run())


async def _project_with_approved_spend(amount=15000):
    await _make_project(id="p1", value=100000)
    await _make_book(id="b1", project_id="p1", current_balance=20000, imprest_limit=50000)
    e1 = await server.cashbook_expense("b1", CashbookExpense(amount=amount, category="Materials"), user=ADMIN)
    await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)


def test_masked_pnl_leaves_no_arithmetic_path_back_to_the_spend_figure():
    """Same defect class as the masked payment total: blanking the headline
    figure is worthless while every sibling metric inverts to it.
    contract_value - gross_profit, contract_value * margin_pct, and the
    category breakdown each recover approved_petty_cash exactly.
    """
    async def run():
        await _project_with_approved_spend(15000)
        result = await server.project_pnl_report(mask_other=True, user=ADMIN)
        row = result["projects"][0]

        assert row["approved_petty_cash"] is None
        for leaky in ("gross_profit", "margin_pct", "net_margin"):
            assert row[leaky] is None, f"{leaky} still inverts to the masked spend"
        assert row["category_breakdown"] == []   # would have summed to 15000
        assert row["recent_entries"] == []       # would have itemised it
        assert "15000" not in str(row)

        # Revenue stays visible and correct — it is not the masked quantity.
        assert row["contract_value"] == 100000
    asyncio.run(run())


def test_masked_pnl_summary_hides_the_aggregate_and_its_margin():
    """The aggregate is the same leak one level up: total_contract_revenue
    is visible, so aggregate_margin_pct would give back total spend."""
    async def run():
        await _project_with_approved_spend(15000)
        summary = (await server.project_pnl_report(mask_other=True, user=ADMIN))["summary"]

        assert summary["total_field_settlement_spend"] is None
        assert summary["aggregate_margin_pct"] is None
        assert summary["total_contract_revenue"] == 100000  # not the masked quantity
    asyncio.run(run())


def test_pnl_masking_is_the_default_so_a_client_that_sends_no_flag_fails_closed():
    async def run():
        await _project_with_approved_spend(15000)
        result = await server.project_pnl_report(user=ADMIN)  # no flag at all
        assert result["projects"][0]["approved_petty_cash"] is None
        assert result["summary"]["total_field_settlement_spend"] is None
    asyncio.run(run())


def test_unmasked_pnl_still_reports_real_spend_and_margin():
    """Authorised, PIN-unlocked viewers must keep the true numbers."""
    async def run():
        await _project_with_approved_spend(15000)
        result = await server.project_pnl_report(mask_other=False, user=ADMIN)
        row = result["projects"][0]

        assert row["approved_petty_cash"] == 15000
        assert row["gross_profit"] == 85000
        assert row["margin_pct"] == 85.0
        assert row["category_breakdown"] == [{"category": "Materials", "amount": 15000}]
        assert result["summary"]["total_field_settlement_spend"] == 15000
        assert result["summary"]["aggregate_margin_pct"] == 85.0
    asyncio.run(run())


def test_has_approved_spend_survives_masking_for_the_lifecycle_pipeline():
    """Projects.jsx marks the P&L lifecycle step done from this flag. It has
    to keep working under the mask, which is why it is a boolean and not the
    amount the UI used to test with."""
    async def run():
        await _project_with_approved_spend(15000)
        masked = (await server.project_pnl_report(mask_other=True, user=ADMIN))["projects"][0]
        assert masked["has_approved_spend"] is True
        assert masked["approved_petty_cash"] is None  # ...without exposing how much
    asyncio.run(run())


def test_masked_csv_export_cannot_be_used_to_bypass_the_on_screen_mask():
    async def run():
        await _project_with_approved_spend(15000)
        masked = "".join([chunk async for chunk in
                          csv_engine.stream_project_pnl_csv(server.db, ADMIN, True)])
        assert "15000" not in masked
        assert "100000" in masked  # revenue column still exported

        unmasked = "".join([chunk async for chunk in
                            csv_engine.stream_project_pnl_csv(server.db, ADMIN, False)])
        assert "15000" in unmasked
    asyncio.run(run())
