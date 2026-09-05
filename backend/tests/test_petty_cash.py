"""Tests for the Cashbook-based petty cash / project wallet extension:
top-up, deferred-approval expenses, overdraft protection, tenant isolation,
and approve-permission gating. Calls the real server.py route functions
directly (FastAPI's Depends() default is simply overridden by passing an
explicit `user` argument), with server.db monkeypatched to mongomock —
same "genuine code under test, disposable storage" idea as
tests/run_local_server.py, scoped to a fast in-process unit test.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import CashbookTopUp, CashbookExpense, CashbookEntryApproval  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["petty_cash_test"])
    yield


async def _make_book(user=ADMIN, **overrides):
    doc = {"book_name": "Site A Wallet", "initial_balance": 1000, "current_balance": 1000,
           "status": "ACTIVE", "assigned_users": [], "project_id": "", "imprest_limit": 0,
           "strict_overdraft": False, "id": "b1", "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    from tenancy import stamp
    stamp(doc, "cashbooks", user)
    await server.db.cashbooks.insert_one(dict(doc))
    return doc


def test_top_up_atomically_increases_balance():
    async def run():
        await _make_book()
        result = await server.cashbook_top_up("b1", CashbookTopUp(amount=500), user=ADMIN)
        assert result["type"] == "CASH_IN"
        assert result["status"] == "Approved"
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 1500
    asyncio.run(run())


def test_expense_does_not_change_balance_until_approved():
    async def run():
        await _make_book()
        entry = await server.cashbook_expense("b1", CashbookExpense(amount=200, category="Fuel"), user=ADMIN)
        assert entry["status"] == "Pending"
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 1000  # untouched

        await server.cashbook_entry_approve(entry["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 800  # debited only now
    asyncio.run(run())


def test_rejected_expense_leaves_balance_untouched():
    async def run():
        await _make_book()
        entry = await server.cashbook_expense("b1", CashbookExpense(amount=200), user=ADMIN)
        result = await server.cashbook_entry_approve(entry["id"], CashbookEntryApproval(approved=False), user=ADMIN)
        assert result["status"] == "Rejected"
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 1000
    asyncio.run(run())


def test_strict_overdraft_blocks_approval_that_would_overdraw():
    async def run():
        await _make_book(current_balance=100, strict_overdraft=True)
        entry = await server.cashbook_expense("b1", CashbookExpense(amount=500), user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await server.cashbook_entry_approve(entry["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        assert exc.value.status_code == 400
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 100  # still untouched, approval was rejected
    asyncio.run(run())


def test_overdraft_allowed_when_strict_overdraft_is_off():
    async def run():
        await _make_book(current_balance=100, strict_overdraft=False)
        entry = await server.cashbook_expense("b1", CashbookExpense(amount=500), user=ADMIN)
        await server.cashbook_entry_approve(entry["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == -400
    asyncio.run(run())


def test_tenant_isolation_cannot_top_up_another_tenants_book():
    async def run():
        await _make_book(user=ADMIN)  # book belongs to "acme"
        with pytest.raises(HTTPException) as exc:
            await server.cashbook_top_up("b1", CashbookTopUp(amount=50), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404  # reads as not-found, never leaks existence
    asyncio.run(run())


def test_legacy_user_without_approve_grant_is_forbidden():
    async def run():
        await _make_book()
        entry = await server.cashbook_expense("b1", CashbookExpense(amount=100), user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await server.cashbook_entry_approve(entry["id"], CashbookEntryApproval(approved=True), user=LEGACY_USER)
        assert exc.value.status_code == 403  # "approve" is not a legacy-implicit action
    asyncio.run(run())


def test_project_petty_cash_summary_aggregates_across_a_projects_wallets():
    async def run():
        await _make_book(id="b1", project_id="P1", current_balance=300)
        await _make_book(id="b2", project_id="P1", current_balance=200)
        await _make_book(id="b3", project_id="P2", current_balance=999)  # different project — excluded

        e1 = await server.cashbook_expense("b1", CashbookExpense(amount=50), user=ADMIN)
        await server.cashbook_entry_approve(e1["id"], CashbookEntryApproval(approved=True), user=ADMIN)
        await server.cashbook_expense("b2", CashbookExpense(amount=20), user=ADMIN)  # left Pending

        summary = await server.project_petty_cash_summary("P1", user=ADMIN)
        assert summary["wallet_count"] == 2
        assert summary["balance_total"] == 300 + 200 - 50  # b1 debited by the approved expense
        assert summary["burn_total"] == 50
        assert summary["pending_total"] == 20
    asyncio.run(run())
