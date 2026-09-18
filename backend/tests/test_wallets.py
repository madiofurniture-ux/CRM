"""Wallets (prompt_1_wallets.md): petty cash -> project wallet linkage.

api_wallets.py's handlers take a FastAPI `Request` (they read the db off
`request.app.state.db`), so a tiny stand-in object is used instead of a
real Request/TestClient — same pattern as tests/test_hr_payroll.py.
normalize_petty_cash lives in server.py and reads the module-level `db`
global, so that one test monkeypatches `server.db` instead.
"""
import asyncio
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import api_wallets  # noqa: E402
import tenancy  # noqa: E402
from models_wallet import WalletCreate, WalletTopUp, WalletAdjustment  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u9", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}

DIVISION_HEAD_ROLE = {"id": "r1", "name": "Division Head", "permissions": [
    {"module": "wallets", "view": True, "create": True, "edit": True, "delete": False,
     "approve": True, "export": False, "scope": "all"},
]}
DIVISION_HEAD = {"id": "u3", "tenant_id": "acme", "name": "Div Head", "role": "user", "role_id": "r1"}

VIEW_ONLY_ROLE = {"id": "r2", "name": "View Only", "permissions": [
    {"module": "wallets", "view": True, "create": False, "edit": False, "delete": False,
     "approve": False, "export": False, "scope": "all"},
]}
VIEW_ONLY = {"id": "u4", "tenant_id": "acme", "name": "Viewer", "role": "user", "role_id": "r2"}


def _req(db):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))


@pytest.fixture()
def db(monkeypatch):
    import server  # payroll-style lazy import — normalize_petty_cash reads server.db
    mock_db = AsyncMongoMockClient()["wallets_test"]
    monkeypatch.setattr(server, "db", mock_db)
    return mock_db


async def _seed_roles(db, *roles):
    for r in roles:
        doc = dict(r)
        tenancy.stamp(doc, "roles", ADMIN)  # every seeded role belongs to the "acme" tenant
        await db.roles.insert_one(doc)


# ------------------------------------------------------------- 1. creation
def test_wallet_creation_with_opening_balance(db):
    async def run():
        wallet = await api_wallets.create_wallet(
            WalletCreate(name="Kothari Residence Wallet", opening_balance=50000), _req(db), user=ADMIN)
        assert wallet["current_balance"] == 50000
        txns = await db.wallet_transactions.find({"wallet_id": wallet["id"]}, {"_id": 0}).to_list(10)
        assert len(txns) == 1 and txns[0]["type"] == "Opening" and txns[0]["amount"] == 50000
    asyncio.run(run())


# --------------------------------------------------- 2. petty cash linkage
def test_petty_cash_voucher_creates_wallet_transaction(db):
    async def run():
        import server
        doc = {"date": "2026-01-01", "kind": "Out", "amount": 500.0,
               "description": "Site tea/snacks", "project_id": "p1"}
        await server.normalize_petty_cash(doc, None, ADMIN)
        assert doc["wallet_id"]
        txns = await db.wallet_transactions.find({"wallet_id": doc["wallet_id"]}, {"_id": 0}).to_list(10)
        assert len(txns) == 1
        assert txns[0]["type"] == "Voucher" and txns[0]["direction"] == "Out" and txns[0]["amount"] == 50000
    asyncio.run(run())


# ----------------------------------------------------- 3. balance updates
def test_wallet_balance_updates_correctly(db):
    async def run():
        wallet = await api_wallets.create_wallet(
            WalletCreate(name="Overhead", opening_balance=100000), _req(db), user=ADMIN)
        await api_wallets.wallet_adjustment(
            wallet["id"], WalletAdjustment(amount=20000, direction="Out", reason="test spend"),
            _req(db), user=ADMIN)
        out = await api_wallets.get_wallet(wallet["id"], _req(db), user=ADMIN)
        assert out["current_balance"] == 80000
    asyncio.run(run())


# --------------------------------------------------- 4/5. negative balance
def test_negative_balance_blocked_without_override(db):
    async def run():
        wallet = await api_wallets.create_wallet(
            WalletCreate(name="Overhead", opening_balance=1000), _req(db), user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await api_wallets.wallet_adjustment(
                wallet["id"], WalletAdjustment(amount=5000, direction="Out", reason="overspend"),
                _req(db), user=LEGACY_USER)
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_override_approval_works_for_division_head_role(db):
    async def run():
        await _seed_roles(db, DIVISION_HEAD_ROLE)
        wallet = await api_wallets.create_wallet(
            WalletCreate(name="Overhead", opening_balance=1000), _req(db), user=ADMIN)
        out = await api_wallets.wallet_adjustment(
            wallet["id"], WalletAdjustment(amount=5000, direction="Out", reason="approved overspend"),
            _req(db), user=DIVISION_HEAD)
        assert out["current_balance"] == -4000
        txns = await db.wallet_transactions.find({"wallet_id": wallet["id"]}, {"_id": 0}).to_list(10)
        adj = next(t for t in txns if t["type"] == "Adjustment")
        assert adj["approved_by"] == "Div Head"
    asyncio.run(run())


# ------------------------------------------------------------- 6. top-up
def test_wallet_topup_from_invoice_receipt(db):
    async def run():
        wallet = await api_wallets.create_wallet(WalletCreate(name="Overhead"), _req(db), user=ADMIN)
        out = await api_wallets.wallet_topup(
            wallet["id"], WalletTopUp(amount=30000, narration="Advance receipt", linked_invoice_id="inv1"),
            _req(db), user=ADMIN)
        assert out["current_balance"] == 30000
        txns = await db.wallet_transactions.find({"wallet_id": wallet["id"]}, {"_id": 0}).to_list(10)
        topup = next(t for t in txns if t["type"] == "Invoice_Receipt")
        assert topup["linked_invoice_id"] == "inv1" and topup["direction"] == "In"
    asyncio.run(run())


# --------------------------------------------------------- 7. pagination
def test_wallet_transactions_paginate_correctly(db):
    async def run():
        wallet = await api_wallets.create_wallet(
            WalletCreate(name="Overhead", opening_balance=100000), _req(db), user=ADMIN)
        for _ in range(4):
            await api_wallets.wallet_topup(wallet["id"], WalletTopUp(amount=100), _req(db), user=ADMIN)
        page1 = await api_wallets.wallet_transactions(wallet["id"], limit=2, offset=0, request=_req(db), user=ADMIN)
        page2 = await api_wallets.wallet_transactions(wallet["id"], limit=2, offset=2, request=_req(db), user=ADMIN)
        assert len(page1) == 2 and len(page2) == 2
        assert {t["id"] for t in page1}.isdisjoint({t["id"] for t in page2})
    asyncio.run(run())


# ------------------------------------------------------------ 8. P&L
def test_project_pnl_includes_wallet_activity(db):
    async def run():
        wallet = await api_wallets.get_or_create_wallet(db, ADMIN, project_id="p1")
        await api_wallets._apply_delta(db, ADMIN, wallet, -20000, type_="Voucher", narration="Material")
        wallet = await api_wallets._get_wallet_or_404(db, wallet["id"], ADMIN)
        await api_wallets._apply_delta(db, ADMIN, wallet, 50000, type_="Topup")

        pnl = await api_wallets.project_wallet_pnl(db, ADMIN, "p1")
        assert pnl["wallet_count"] == 1
        assert pnl["petty_cash_out_paise"] == 20000
        assert pnl["wallet_topups_paise"] == 50000
        assert pnl["closing_cash_in_hand_paise"] == 30000
    asyncio.run(run())


# ----------------------------------------------------- 9. tenant isolation
def test_tenant_isolation_cannot_see_other_tenants_wallets(db):
    async def run():
        wallet = await api_wallets.create_wallet(WalletCreate(name="Acme Wallet"), _req(db), user=ADMIN)
        others = await api_wallets.list_wallets(request=_req(db), user=OTHER_TENANT_ADMIN)
        assert others == []
        with pytest.raises(HTTPException) as exc:
            await api_wallets.get_wallet(wallet["id"], _req(db), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


# ------------------------------------------------------------- 10. RBAC
def test_view_only_role_can_view_but_not_create_or_adjust(db):
    async def run():
        await _seed_roles(db, VIEW_ONLY_ROLE)
        wallet = await api_wallets.create_wallet(WalletCreate(name="Overhead"), _req(db), user=ADMIN)

        seen = await api_wallets.list_wallets(request=_req(db), user=VIEW_ONLY)
        assert any(w["id"] == wallet["id"] for w in seen)

        with pytest.raises(HTTPException) as exc:
            await api_wallets.create_wallet(WalletCreate(name="New"), _req(db), user=VIEW_ONLY)
        assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            await api_wallets.wallet_adjustment(
                wallet["id"], WalletAdjustment(amount=100, direction="In"), _req(db), user=VIEW_ONLY)
        assert exc.value.status_code == 403
    asyncio.run(run())
