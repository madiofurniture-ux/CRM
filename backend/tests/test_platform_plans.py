"""Plans for companies on the platform: trial expiry is read-only, a
suspended company is locked out, seats are capped, and only the platform
owner manages plans."""
import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402
import plans  # noqa: E402
import server  # noqa: E402
from models import UserCreate  # noqa: E402

OWNER = {"id": "o", "tenant_id": server.DEFAULT_TENANT, "role": "admin", "name": "Owner"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["plans_test"])
    yield


def run(c):
    return asyncio.run(c)


def test_trial_state():
    t = {"plan": "trial", "trial_ends_at": "2026-10-10"}
    assert plans.state(t, date(2026, 10, 4))["trial_days_left"] == 6
    assert plans.state(t, date(2026, 10, 10))["can_write"]
    ended = plans.state(t, date(2026, 10, 11))
    assert ended["can_read"] and not ended["can_write"] and "trial has ended" in ended["reason"]


def test_suspended_and_legacy_state():
    assert not plans.state({"plan": "growth", "status": "suspended"})["can_read"]
    legacy = plans.state({})
    assert legacy["can_write"] and legacy["max_users"] is None


def test_seats():
    assert plans.seats_left({"plan": "starter"}, 3) == 2
    assert plans.seats_left({"plan": "starter", "max_users": 10}, 3) == 7
    assert plans.seats_left({"plan": "enterprise"}, 300) is None


def test_enforcement_at_the_auth_choke_point():
    async def go():
        db = server.db
        await db.tenants.insert_many([
            {"id": "old", "plan": "trial", "trial_ends_at": "2020-01-01"},
            {"id": "off", "plan": "growth", "status": "suspended"},
            {"id": "ok", "plan": "growth"},
        ])
        await auth.enforce_subscription(db, {"tenant_id": "old"}, "GET")
        with pytest.raises(HTTPException) as e:
            await auth.enforce_subscription(db, {"tenant_id": "old"}, "POST")
        assert e.value.status_code == 402
        with pytest.raises(HTTPException) as e:
            await auth.enforce_subscription(db, {"tenant_id": "off"}, "GET")
        assert e.value.status_code == 403
        await auth.enforce_subscription(db, {"tenant_id": "ok"}, "DELETE")
    run(go())


def test_new_customer_starts_on_a_dated_trial_and_seats_are_capped():
    async def go():
        res = await server.tenant_create({"name": "Pixel Clinic", "industry": "healthcare",
                                          "admin_pin": "1234"}, user=OWNER)
        tid = res["tenant"]["id"]
        t = await server.db.tenants.find_one({"id": tid})
        assert t["plan"] == "trial" and t["trial_ends_at"] > date.today().isoformat()
        admin = {"id": "x", "tenant_id": tid, "role": "admin", "name": "A"}
        await server.platform_update_tenant(tid, {"max_users": 2}, user=OWNER)
        await server.create_user(UserCreate(username="doc1", name="Doc", pin="1111", role="sales"), user=admin)
        with pytest.raises(HTTPException) as e:
            await server.create_user(UserCreate(username="doc2", name="Doc 2", pin="1111", role="sales"), user=admin)
        assert e.value.status_code == 402
        me = await server.tenant_me(user=admin)
        assert me["subscription"]["plan"] == "trial" and me["is_platform_owner"] is False
    run(go())


def test_only_the_owner_manages_plans():
    async def go():
        await server.db.tenants.insert_one({"id": "acme", "plan": "trial"})
        acme_admin = {"id": "a", "tenant_id": "acme", "role": "admin", "name": "A"}
        with pytest.raises(HTTPException) as e:
            await server.platform_update_tenant("acme", {"plan": "enterprise"}, user=acme_admin)
        assert e.value.status_code == 403
        out = await server.platform_update_tenant("acme", {"plan": "growth", "status": "suspended"}, user=OWNER)
        assert out["subscription"]["status"] == "suspended" and out["subscription"]["max_users"] == 25
        with pytest.raises(HTTPException):
            await server.platform_update_tenant(server.DEFAULT_TENANT, {"status": "suspended"}, user=OWNER)
        with pytest.raises(HTTPException):
            await server.platform_update_tenant("acme", {"plan": "owner"}, user=OWNER)
    run(go())


def test_login_tiles_can_be_switched_off(monkeypatch):
    async def go():
        await server.db.users.insert_one({"username": "admin", "name": "Admin", "tenant_id": server.DEFAULT_TENANT})
        assert len(await server.login_roles()) == 1
        monkeypatch.setenv("LOGIN_PROFILE_TILES", "false")
        assert await server.login_roles() == []
    run(go())
