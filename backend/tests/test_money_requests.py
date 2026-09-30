"""Money requests: approval chain, visibility, links, transfer into a Cashbook wallet."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import expenses as ex  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import MoneyRequestCreate, MoneyRequestTransfer, UserUpdate  # noqa: E402

T = "acme"
ADMIN = {"id": "u-admin", "tenant_id": T, "name": "Admin", "role": "admin"}
REP = {"id": "u-rep", "tenant_id": T, "name": "Amritanshu", "role": "user", "role_id": "r-staff",
       "reports_to": "u-mgr"}
MGR = {"id": "u-mgr", "tenant_id": T, "name": "Ashutosh", "role": "user", "role_id": "r-staff"}
FIN = {"id": "u-fin", "tenant_id": T, "name": "Finance Lead", "role": "user", "role_id": "r-finance"}
PEER = {"id": "u-peer", "tenant_id": T, "name": "Peer", "role": "user", "role_id": "r-staff"}
OTHER = {"id": "u-x", "tenant_id": "globex", "name": "Globex", "role": "admin"}
ROLES = [
    {"id": "r-staff", "permissions": []},
    {"id": "r-finance", "permissions": [{"module": "cashbook", "view": True, "approve": True, "scope": "all"}]},
]
PHOTO = "data:image/jpeg;base64,AAAA"


@pytest.fixture(autouse=True)
def db(monkeypatch):
    mock = AsyncMongoMockClient()["mr_test"]
    monkeypatch.setattr(server, "db", mock)

    async def roles_for(user):
        return ROLES
    monkeypatch.setattr(server, "_roles_for", roles_for)

    async def seed():
        for u in (ADMIN, REP, MGR, FIN, PEER):
            await mock.users.insert_one(dict(u))
    asyncio.run(seed())
    return mock


def run(c):
    return asyncio.run(c)


def req(**kw):
    base = {"title": "Mobile recharge", "amount": 351, "category": "Internet & Mobile",
            "receipt_url": PHOTO}
    return MoneyRequestCreate(**{**base, **kw})


async def _insert(db, coll, doc, user=ADMIN):
    await db[coll].insert_one(tenancy.stamp(dict(doc), coll, user))


# ── pure chain ─────────────────────────────────────────────────────────────
def test_approval_chain_rules():
    pol = ex.DEFAULT_POLICY
    mgr = {"id": "m", "name": "M"}
    assert [s["level"] for s in ex.build_approval_chain({"id": "r"}, 100, mgr, pol)] == ["manager"]
    assert [s["level"] for s in ex.build_approval_chain({"id": "r"}, 5000, mgr, pol)] == ["manager", "finance"]
    assert [s["level"] for s in ex.build_approval_chain({"id": "r"}, 100, None, pol)] == ["finance"]
    assert [s["level"] for s in ex.build_approval_chain({"id": "m"}, 100, mgr, pol)] == ["finance"]  # self
    assert [s["level"] for s in ex.build_approval_chain({"id": "r"}, 100, {**mgr, "active": False}, pol)] == ["finance"]


def test_policy_and_receipt_validation():
    with pytest.raises(ValueError):
        ex.validate_policy({"finance_threshold": -1})
    with pytest.raises(ValueError):
        ex.validate_policy({"categories": []})
    pol = ex.validate_policy({"finance_threshold": "2000", "categories": ["Travel", "Travel", " Food "]})
    assert pol["finance_threshold"] == 2000 and pol["categories"] == ["Travel", "Food"]
    with pytest.raises(ValueError):
        ex.validate_receipt("", 600, ex.DEFAULT_POLICY)
    ex.validate_receipt("", 100, ex.DEFAULT_POLICY)        # small amounts need no receipt
    with pytest.raises(ValueError):
        ex.validate_receipt("https://evil.example/x.png", 100, ex.DEFAULT_POLICY)
    with pytest.raises(ValidationError):
        MoneyRequestCreate(title=" ", amount=10)
    with pytest.raises(ValidationError):
        MoneyRequestCreate(title="x", amount=0)


# ── create + links ─────────────────────────────────────────────────────────
def test_create_derives_lineage_from_a_sale_and_routes_to_manager(db):
    async def go():
        await _insert(db, "leads", {"id": "L1", "name": "Anita", "division": "Furniture"})
        await _insert(db, "quotes", {"id": "Q1", "quote_no": "Q-1", "lead_id": "L1", "customer": "Anita"})
        await _insert(db, "sales", {"id": "S1", "sale_no": "S-1", "quote_id": "Q1", "lead_id": "L1",
                                    "customer": "Anita", "division": "Furniture"})
        await _insert(db, "projects", {"id": "P1", "project_no": "PM-1", "sale_id": "S1", "customer": "Anita"})
        out = await server.create_money_request(req(sale_id="S1", category="Material", amount=1200), user=REP)
        assert (out["project_id"], out["quote_id"], out["lead_id"]) == ("P1", "Q1", "L1")
        assert out["cost_type"] == "project" and out["division"] == "Furniture"
        assert out["link_label"] == "Anita · PM-1"
        assert out["status"] == "Pending review" and out["request_no"].startswith("MR-")
        assert out["waiting_on"]["level"] == "manager" and out["waiting_on"]["approver_name"] == "Ashutosh"
        assert out["tenant_id"] == T and out["raised_by"] == "Amritanshu"
        assert out["can_decide"] is False and out["can_cancel"] is True

        overhead = await server.create_money_request(req(), user=REP)
        assert overhead["cost_type"] == "overhead" and overhead["project_id"] == ""

        with pytest.raises(HTTPException) as e:
            await server.create_money_request(req(project_id="nope"), user=REP)
        assert e.value.status_code == 400
        with pytest.raises(HTTPException):
            await server.create_money_request(req(category="Yacht"), user=REP)
        with pytest.raises(HTTPException):
            await server.create_money_request(req(amount=900, receipt_url=""), user=REP)
    run(go())


def test_a_project_from_another_tenant_cannot_be_linked(db):
    async def go():
        await _insert(db, "projects", {"id": "PX", "customer": "Globex"}, user=OTHER)
        with pytest.raises(HTTPException) as e:
            await server.create_money_request(req(project_id="PX"), user=REP)
        assert e.value.status_code == 400
    run(go())


# ── approvals + visibility ─────────────────────────────────────────────────
def test_manager_then_finance_then_transfer_into_a_wallet(db):
    async def go():
        await _insert(db, "projects", {"id": "P1", "project_no": "PM-1", "customer": "Anita"})
        await _insert(db, "cashbooks", {"id": "W1", "book_name": "HDFC Current", "status": "ACTIVE",
                                        "current_balance": 20000, "strict_overdraft": True})
        r = await server.create_money_request(req(amount=8000, project_id="P1", category="Material"), user=REP)
        assert [s["level"] for s in r["approvals"]] == ["manager", "finance"]

        # Visibility: a peer can't see it; the manager and finance can.
        assert await server.list_money_requests(user=PEER) == []
        assert [x["id"] for x in await server.list_money_requests(user=MGR)] == [r["id"]]
        assert [x["id"] for x in await server.list_money_requests(assigned=True, user=MGR)] == [r["id"]]
        assert await server.list_money_requests(assigned=True, user=FIN) == []   # not finance's turn yet
        with pytest.raises(HTTPException) as e:
            await server.approve_money_request(r["id"], {}, user=PEER)
        assert e.value.status_code == 404
        with pytest.raises(HTTPException) as e:
            await server.approve_money_request(r["id"], {}, user=FIN)
        assert e.value.status_code == 403

        r = await server.approve_money_request(r["id"], {"note": "ok"}, user=MGR)
        assert r["status"] == "Pending review" and r["waiting_on"]["level"] == "finance"
        r = await server.approve_money_request(r["id"], {}, user=FIN)
        assert r["status"] == "Pending transfer" and r["can_transfer"] is True

        with pytest.raises(HTTPException) as e:
            await server.transfer_money_request(r["id"], MoneyRequestTransfer(cashbook_id="W1"), user=FIN)
        assert e.value.status_code == 400                                  # UTR missing
        with pytest.raises(HTTPException) as e:
            await server.transfer_money_request(r["id"], MoneyRequestTransfer(cashbook_id="W1", utr="U1"), user=MGR)
        assert e.value.status_code == 403
        r = await server.transfer_money_request(
            r["id"], MoneyRequestTransfer(cashbook_id="W1", utr="618348670368"), user=FIN)
        assert r["status"] == "Transferred" and r["transfer"]["utr"] == "618348670368"
        book = await db.cashbooks.find_one({"id": "W1"})
        assert book["current_balance"] == 12000
        entry = await db.cashbook_entries.find_one({"money_request_id": r["id"]}, {"_id": 0})
        assert entry["type"] == "CASH_OUT" and entry["status"] == "Approved" and entry["amount"] == 8000
        assert entry["project_id"] == "P1" and entry["tenant_id"] == T and entry["receipt_url"] == PHOTO
        assert [e["action"] for e in r["log"]] == ["raised", "approved", "approved", "transferred"]

        with pytest.raises(HTTPException):          # can't pay twice
            await server.transfer_money_request(
                r["id"], MoneyRequestTransfer(cashbook_id="W1", utr="again"), user=FIN)
        assert (await db.cashbooks.find_one({"id": "W1"}))["current_balance"] == 12000
    run(go())


def test_overdraft_rejection_and_cancel(db):
    async def go():
        await _insert(db, "cashbooks", {"id": "W1", "book_name": "Site cash", "status": "ACTIVE",
                                        "current_balance": 100, "strict_overdraft": True})
        r = await server.create_money_request(req(amount=300, receipt_url=""), user=PEER)   # no manager
        assert [s["level"] for s in r["approvals"]] == ["finance"]
        r = await server.approve_money_request(r["id"], {}, user=FIN)
        with pytest.raises(HTTPException) as e:
            await server.transfer_money_request(
                r["id"], MoneyRequestTransfer(cashbook_id="W1", payment_mode="OTHER"), user=FIN)
        assert "balance" in e.value.detail
        assert (await db.money_requests.find_one({"id": r["id"]}))["status"] == "Pending transfer"

        r2 = await server.create_money_request(req(), user=REP)
        with pytest.raises(HTTPException) as e:
            await server.reject_money_request(r2["id"], {}, user=MGR)
        assert e.value.status_code == 400                                   # a reason is required
        r2 = await server.reject_money_request(r2["id"], {"note": "Duplicate"}, user=MGR)
        assert r2["status"] == "Rejected"

        r3 = await server.create_money_request(req(), user=REP)
        with pytest.raises(HTTPException):
            await server.cancel_money_request(r3["id"], user=MGR)
        r3 = await server.cancel_money_request(r3["id"], user=REP)
        assert r3["status"] == "Cancelled"

        s = await server.money_requests_summary(user=FIN)
        assert s["counts"]["Pending transfer"] == 1 and s["counts"]["Rejected"] == 1
        assert s["assigned_to_me"] == 1 and s["is_finance"] is True
    run(go())


def test_raiser_can_edit_only_before_anyone_acts(db):
    async def go():
        r = await server.create_money_request(req(), user=REP)
        r = await server.update_money_request(r["id"], req(amount=400), user=REP)
        assert r["amount"] == 400
        with pytest.raises(HTTPException):
            await server.update_money_request(r["id"], req(amount=1), user=MGR)
        await server.approve_money_request(r["id"], {}, user=MGR)
    run(go())


def test_other_tenant_never_sees_requests(db):
    async def go():
        r = await server.create_money_request(req(), user=REP)
        assert await server.list_money_requests(user=OTHER) == []
        with pytest.raises(HTTPException):
            await server.approve_money_request(r["id"], {}, user=OTHER)
    run(go())


def test_reporting_lines_cannot_loop(db):
    async def go():
        with pytest.raises(HTTPException):
            await server.update_user("u-mgr", UserUpdate(reports_to="u-rep"), user=ADMIN)   # rep -> mgr -> rep
        with pytest.raises(HTTPException):
            await server.update_user("u-mgr", UserUpdate(reports_to="u-mgr"), user=ADMIN)
        with pytest.raises(HTTPException):
            await server.update_user("u-mgr", UserUpdate(reports_to="u-x"), user=ADMIN)     # other tenant
        await server.update_user("u-mgr", UserUpdate(reports_to="u-fin"), user=ADMIN)
        assert (await db.users.find_one({"id": "u-mgr"}))["reports_to"] == "u-fin"
    run(go())


def test_policy_endpoint_is_admin_only_and_applies(db):
    async def go():
        await server.set_expense_policy({"finance_threshold": 100}, user=ADMIN)
        r = await server.create_money_request(req(amount=150), user=REP)
        assert [s["level"] for s in r["approvals"]] == ["manager", "finance"]
        assert (await server.get_expense_policy(user=OTHER))["finance_threshold"] == 5000
    run(go())
