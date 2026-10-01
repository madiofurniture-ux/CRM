"""Inventory production hardening: server-side validation, write-side cost
security, audit trail, and cost leakage on the dashboard / stock ledger."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402
from models import InventoryCreate, StockMovementCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
SALES = {"id": "u3", "tenant_id": "acme", "name": "Sales Rep", "role": "user"}
OTHER = {"id": "u9", "tenant_id": "beta", "name": "Beta Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["inv_hardening"])
    yield


def _route(path, method):
    for r in list(server.api.routes) + list(server.app.routes):
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError(f"{method} {path} not registered")


def _item(**kw):
    base = dict(sku="SKU-1", name="Oak Sideboard", vendor_code="V-1", qty=3,
                cost=4000, mrp=5000, location="Warehouse")
    base.update(kw)
    return InventoryCreate(**base)


def run(coro):
    return asyncio.run(coro)


async def _create(user=ADMIN, **kw):
    return await _route("/api/inventory", "POST")(_item(**kw), user=user)


def test_margin_is_computed_server_side_not_trusted():
    async def body():
        out = await _create(margin=999)
        assert out["margin"] == 25.0  # (5000-4000)/4000
    run(body())


def test_non_admin_cannot_set_cost_on_create_or_update():
    async def body():
        made = await _create(user=SALES, cost=1, mrp=5000)
        stored = await server.db.inventory.find_one({"id": made["id"]})
        assert stored["cost"] == 0, "a floor user cannot write a landing price"
        assert "cost" not in made and "margin" not in made

        # Admin sets the real cost; a later sales edit must not overwrite it.
        await _route("/api/inventory/{item_id}", "PUT")(made["id"], {"cost": 4000}, user=ADMIN)
        await _route("/api/inventory/{item_id}", "PUT")(made["id"], {"cost": 1, "margin": 500, "mrp": 6000}, user=SALES)
        stored = await server.db.inventory.find_one({"id": made["id"]})
        assert stored["cost"] == 4000
        assert stored["mrp"] == 6000
        assert stored["margin"] == 50.0, "margin follows the new MRP against the real cost"
    run(body())


@pytest.mark.parametrize("bad", [
    dict(qty=-1), dict(mrp=-5), dict(cost=-5), dict(width_mm=0), dict(height_mm=-3),
    dict(depth_mm=200000), dict(status="Lost"), dict(sku="  "),
])
def test_invalid_values_rejected(bad):
    async def body():
        with pytest.raises(HTTPException) as e:
            await _create(**bad)
        assert e.value.status_code == 400
    run(body())


def test_duplicate_sku_rejected_case_insensitive_but_per_tenant():
    async def body():
        await _create(sku="ABC-1")
        with pytest.raises(HTTPException):
            await _create(sku="abc-1")
        # another tenant may reuse the same SKU
        await _create(user=OTHER, sku="ABC-1")
    run(body())


def test_inventory_changes_land_in_audit_trail_admin_only():
    async def body():
        made = await _create()
        await _route("/api/inventory/{item_id}", "PUT")(made["id"], {"qty": 9, "location": "Ground Floor"}, user=ADMIN)
        await _route("/api/inventory/{item_id}", "DELETE")(made["id"], user=ADMIN)
        rows = await server.list_activities(entity="inventory", entity_id=made["id"], user=ADMIN)
        assert {r["action"] for r in rows} == {"create", "update", "delete"}
        upd = next(r for r in rows if r["action"] == "update")
        assert upd["before"]["qty"] == 3 and upd["after"]["qty"] == 9
        other = await server.list_activities(entity="inventory", user=OTHER)
        assert other == []
    run(body())


def test_dashboard_stock_cost_hidden_from_non_admin():
    async def body():
        await _create()
        assert (await server.dashboard_stats(user=ADMIN))["stock_cost"] == 12000
        assert (await server.dashboard_stats(user=SALES))["stock_cost"] is None
    run(body())


def test_stock_movement_validation_and_audit():
    async def body():
        await _create(sku="MV-1")
        post = _route("/api/stock-movements", "POST")
        with pytest.raises(HTTPException):  # unknown SKU
            await post(StockMovementCreate(type="Receipt", product_id="NOPE", qty=1), user=ADMIN)
        with pytest.raises(HTTPException):  # zero qty
            await post(StockMovementCreate(type="Receipt", product_id="MV-1", qty=0), user=ADMIN)
        with pytest.raises(HTTPException):  # negative receipt
            await post(StockMovementCreate(type="Receipt", product_id="MV-1", qty=-2), user=ADMIN)
        with pytest.raises(HTTPException):  # adjustment without reason
            await post(StockMovementCreate(type="Adjustment", product_id="MV-1", qty=-1), user=ADMIN)
        with pytest.raises(HTTPException):  # bogus type
            await post(StockMovementCreate(type="Teleport", product_id="MV-1", qty=1), user=ADMIN)
        with pytest.raises(HTTPException):  # transfer to same place
            await post(StockMovementCreate(type="Transfer", product_id="MV-1", qty=1,
                                           warehouse="A", to_warehouse="A"), user=ADMIN)
        ok = await post(StockMovementCreate(type="Adjustment", product_id="MV-1", qty=-1,
                                            reason="Count correction"), user=ADMIN)
        await _route("/api/stock-movements/{item_id}", "DELETE")(ok["id"], user=ADMIN)
        rows = await server.list_activities(entity="stock_movement", entity_id=ok["id"], user=ADMIN)
        assert {r["action"] for r in rows} == {"create", "delete"}
    run(body())
