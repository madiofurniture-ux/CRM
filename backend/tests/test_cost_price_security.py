"""Role-gated landing/cost-price visibility on Inventory.

Treated as a real security boundary, the same standard as the privacy-mask
fix in test_split_payments.py: the check is that a non-privileged response
does not CONTAIN the figure, not that the UI hides it. That includes the
arithmetic back-doors — `margin` inverts to `cost` given `mrp`, so a test
that only asserted `"cost" not in row` would pass while the number remained
trivially recoverable.

Same harness as the other API tests: real functions, server.db on mongomock.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
ACCOUNTANT = {"id": "u2", "tenant_id": "acme", "name": "Accounts", "role": "accountant"}
SALES = {"id": "u3", "tenant_id": "acme", "name": "Sales Rep", "role": "user"}

# cost 4000, mrp 5000 -> margin 25%. Chosen so the inversion is exact:
# 5000 / (1 + 25/100) == 4000, i.e. leaking `margin` leaks `cost` outright.
COST = 4000.0
MRP = 5000.0
MARGIN = 25.0


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["cost_security_test"])
    yield


async def _make_item(**overrides):
    doc = {"id": "i1", "created_at": "2026-01-01T00:00:00+00:00", "sku": "SKU-1",
           "name": "Oak Sideboard", "category": "Storage", "vendor": "Acme Timber",
           "vendor_id": "v1", "vendor_code": "VEN-001", "qty": 3,
           "cost": COST, "mrp": MRP, "margin": MARGIN, "status": "In Stock",
           "location": "Warehouse"}
    doc.update(overrides)
    tenancy.stamp(doc, "inventory", ADMIN)
    await server.db.inventory.insert_one(dict(doc))
    return doc


# ---------------------------------------------------------------- redaction
def test_admin_sees_real_cost_and_margin():
    item = {"sku": "S", "cost": COST, "mrp": MRP, "margin": MARGIN, "vendor": "Acme"}
    out = server.redact_inventory(item, ADMIN)
    assert out["cost"] == COST
    assert out["margin"] == MARGIN


def test_accountant_sees_real_cost():
    """Accountants are the other half of the existing _can_see_vendor_names
    pair; cost is purchase-side commercial data they legitimately reconcile."""
    out = server.redact_inventory({"sku": "S", "cost": COST, "margin": MARGIN}, ACCOUNTANT)
    assert out["cost"] == COST


def test_non_admin_response_has_no_cost_field_at_all():
    """Absent, not zeroed and not blanked — a 0 would read as a real price."""
    out = server.redact_inventory({"sku": "S", "cost": COST, "mrp": MRP, "margin": MARGIN}, SALES)
    assert "cost" not in out
    assert out["mrp"] == MRP, "MRP is the selling price and stays visible"


def test_non_admin_cannot_invert_cost_from_margin():
    """The leak that makes stripping `cost` alone useless."""
    out = server.redact_inventory({"sku": "S", "cost": COST, "mrp": MRP, "margin": MARGIN}, SALES)
    assert "margin" not in out
    # Belt and braces: nothing left in the payload reconstructs COST.
    assert COST not in [v for v in out.values() if isinstance(v, (int, float))]


def test_redaction_does_not_mutate_the_caller_s_dict():
    """make_crud reuses list entries; an in-place pop would corrupt them."""
    item = {"sku": "S", "cost": COST, "margin": MARGIN}
    server.redact_inventory(item, SALES)
    assert item["cost"] == COST


# ------------------------------------------------------------ list endpoint
def _route(path: str, method: str = "GET"):
    """The real registered endpoint function, so this exercises the wiring
    (make_crud's redact= hook) and not just the redactor in isolation — the
    bug class here is forgetting to wire a redactor up, which a direct unit
    call on redact_inventory could never catch."""
    for r in list(server.api.routes) + list(server.app.routes):
        if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
            return r.endpoint
    raise AssertionError(f"route {method} {path} is not registered")


def test_inventory_list_endpoint_strips_cost_for_non_admin():
    async def run():
        await _make_item()
        listing = _route("/api/inventory")

        admin_rows = await listing(user=ADMIN)
        assert admin_rows[0]["cost"] == COST
        assert admin_rows[0]["margin"] == MARGIN

        sales_rows = await listing(user=SALES)
        assert len(sales_rows) == 1, "the row is still listed — only the price is gated"
        assert "cost" not in sales_rows[0]
        assert "margin" not in sales_rows[0]
        assert sales_rows[0]["sku"] == "SKU-1"
    asyncio.run(run())

def test_inventory_list_still_gates_vendor_name_independently():
    async def run():
        """Cost and vendor-name gating are separate concerns on the same row;
        adding the cost redactor must not have dropped the vendor one."""
        await _make_item()
        sales_rows = await _route("/api/inventory")(user=SALES)
        assert "vendor" not in sales_rows[0]
        assert sales_rows[0]["vendor_code"] == "VEN-001", "the code stays visible to everyone"
    asyncio.run(run())

def test_analytics_total_cost_is_none_for_non_admin():
    async def run():
        await _make_item()
        admin_view = await server.inventory_analytics(user=ADMIN)
        assert admin_view["total_cost"] == COST * 3

        sales_view = await server.inventory_analytics(user=SALES)
        assert sales_view["total_cost"] is None, "a 0 would read as 'this stock cost nothing'"
    asyncio.run(run())

def test_analytics_top_items_carry_no_cost_for_non_admin():
    async def run():
        """top_items are whole inventory rows — the route that forgot to redact
        them would hand back everything the list route strips."""
        await _make_item()
        sales_view = await server.inventory_analytics(user=SALES)
        assert sales_view["top_items"], "fixture should produce a top item"
        for row in sales_view["top_items"]:
            assert "cost" not in row
            assert "margin" not in row

        admin_view = await server.inventory_analytics(user=ADMIN)
        assert admin_view["top_items"][0]["cost"] == COST
    asyncio.run(run())
