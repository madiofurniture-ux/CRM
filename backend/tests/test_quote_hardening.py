"""Quotations: discount sign-off can't be forged through a plain edit, and
offers carry a validity date."""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import QuoteCreate  # noqa: E402

REP = {"id": "u2", "tenant_id": "acme", "name": "Rep", "role": "sales", "username": "rep"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["quote_hardening"])


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


update_quote = _route("/api/quotes/{item_id}", "PUT")
create_quote = _route("/api/quotes", "POST")
BASE = {"quote_no": "Q-1", "date": "2026-09-01", "customer": "X", "by_user": "Rep"}


async def _seed(**extra):
    q = {"id": "Q1", **BASE, "subtotal": 100000, "discount": 50000, "approval": "pending", **extra}
    await server.db.quotes.insert_one(tenancy.stamp(dict(q), "quotes", REP))


def test_rep_cannot_self_approve_a_discount():
    async def go():
        await _seed()
        out = await update_quote("Q1", {"approval": "approved", "approved_by": "rep"}, user=REP)
        assert out["approval"] == "pending" and not out.get("approved_by")
    asyncio.run(go())


def test_raising_an_approved_discount_reopens_the_gate():
    async def go():
        await _seed(approval="approved", approved_by="admin")
        out = await update_quote("Q1", {"discount": 60000}, user=REP)
        assert out["approval"] == "pending" and out["approved_by"] == ""
    asyncio.run(go())


def test_unrelated_edit_keeps_an_approval():
    async def go():
        await _seed(approval="approved", approved_by="admin")
        out = await update_quote("Q1", {"remarks": "call Monday", "discount": 50000}, user=REP)
        assert out["approval"] == "approved" and out["approved_by"] == "admin"
    asyncio.run(go())


def test_create_with_big_discount_starts_pending_and_gets_validity():
    async def go():
        out = await create_quote(QuoteCreate(**BASE, subtotal=100000, discount=30000, approval="approved"), user=REP)
        assert out["approval"] == "pending"
        assert out["valid_until"] == "2026-10-01"
    asyncio.run(go())


def test_quote_expiry():
    assert lc.quote_expired({"stage": "Quoted", "valid_until": "2026-09-01"}, today="2026-09-02")
    assert not lc.quote_expired({"stage": "Quoted", "valid_until": "2026-09-05"}, today="2026-09-02")
    assert not lc.quote_expired({"status": "Won", "valid_until": "2026-09-01"}, today="2026-09-02")
    assert not lc.quote_expired({"stage": "Quoted", "valid_until": ""}, today="2026-09-02")
