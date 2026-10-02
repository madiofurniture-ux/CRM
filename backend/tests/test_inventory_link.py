"""Quotations and invoices linked to inventory: product lookup with live
stock, reservation when a quote becomes a sale, issue when the invoice is
issued, return when it is cancelled, and item qty kept in step with every
movement. CRM qty is the stock of record."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tenancy  # noqa: E402
from models import StockMovementCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "studio", "name": "S", "role": "admin", "username": "s"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["inv_link"])


def run(c):
    return asyncio.run(c)


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


update_inv = _route("/api/invoices/{item_id}", "PUT")
update_sale = _route("/api/sales/{item_id}", "PUT")
update_item = _route("/api/inventory/{item_id}", "PUT")


async def _item(sku="WR-1", qty=10, user=ADMIN, **kw):
    doc = {"id": f"i-{sku}", "sku": sku, "name": "Wardrobe 3-door", "model_no": "W3D", "qty": qty,
           "cost": 30000, "mrp": 50000, "hsn": "9403", "gst_pct": 18, "unit": "pcs", **kw}
    await server.db.inventory.insert_one(tenancy.stamp(doc, "inventory", user))


async def _item_qty(sku="WR-1"):
    return (await server.db.inventory.find_one({"sku": sku, "tenant_id": "madio"}))["qty"]


async def _quote_to_sale(qty=2):
    q = {"id": "Q1", "quote_no": "AF-1", "date": "2026-10-01", "customer": "Anita", "phone": "9876543210",
         "tax_pct": 18, "version": 1, "stage": "Quoted"}
    await server.db.quotes.insert_one(tenancy.stamp(dict(q), "quotes", ADMIN))
    await server.db.quote_lines.insert_one(tenancy.stamp(
        {"id": "L1", "quote_id": "Q1", "version": 1, "description": "Wardrobe 3-door", "qty": qty,
         "rate": 50000, "sku": "WR-1", "unit": "pcs", "hsn": "9403", "created_at": "2026-10-01T00"},
        "quote_lines", ADMIN))
    out = await server.quote_approve("Q1", {"approved": True}, user=ADMIN)
    return out["sales_order"]


def test_lookup_finds_by_name_sku_or_model_with_stock_and_no_cost():
    async def go():
        await _item()
        await _item(sku="TB-9", name="Dining table", model_no="DT6")
        rows = await server.inventory_lookup(q="w3d", user=ADMIN)
        assert [r["sku"] for r in rows] == ["WR-1"]
        r = rows[0]
        assert (r["on_hand"], r["reserved"], r["available"], r["hsn"], r["mrp"]) == (10, 0, 10, "9403", 50000)
        assert "cost" not in r
        assert await server.inventory_lookup(q="wardrobe", user=OTHER) == []      # other company sees nothing
        assert len(await server.inventory_lookup(q="", user=ADMIN)) == 2
        await server.inventory_lookup(q="(.*", user=ADMIN)                         # regex input is escaped
    run(go())


def test_sale_reserves_invoice_issues_and_cancel_returns():
    async def go():
        await _item()
        sale = await _quote_to_sale(qty=2)
        pos = (await server.inventory_lookup(q="WR-1", user=ADMIN))[0]
        assert (pos["on_hand"], pos["reserved"], pos["available"]) == (10, 2, 8)

        inv = await server.invoice_from_sale(sale["id"], user=ADMIN)
        assert inv["line_items"][0]["sku"] == "WR-1"
        assert await _item_qty() == 10                       # a draft takes nothing out
        sent = await update_inv(inv["id"], {"status": "Sent"}, user=ADMIN)
        assert sent["stock_warnings"] == []
        assert await _item_qty() == 8
        pos = (await server.inventory_lookup(q="WR-1", user=ADMIN))[0]
        assert (pos["reserved"], pos["available"]) == (0, 8)    # reservation converted into the issue

        await update_inv(inv["id"], {"notes": "x"}, user=ADMIN)   # re-saving never issues twice
        assert await _item_qty() == 8
        await update_inv(inv["id"], {"status": "Cancelled"}, user=ADMIN)
        assert await _item_qty() == 10
        types = sorted(m["type"] for m in await server.db.stock_movements.find(
            {"ref_invoice_id": inv["id"]}).to_list(10))
        assert types == ["Issue", "Return"]
    run(go())


def test_warning_when_invoicing_more_than_in_stock():
    async def go():
        await _item(qty=1)
        sale = await _quote_to_sale(qty=3)
        inv = await server.invoice_from_sale(sale["id"], user=ADMIN)
        sent = await update_inv(inv["id"], {"status": "Sent"}, user=ADMIN)
        assert sent["stock_warnings"] == ["WR-1: invoicing 3 but only 1 in stock"]
        assert await _item_qty() == -2                       # recorded, not hidden: stock goes negative
    run(go())


def test_cancelling_a_sale_releases_its_reservation():
    async def go():
        await _item()
        sale = await _quote_to_sale(qty=4)
        await update_sale(sale["id"], {"stage": "Cancelled"}, user=ADMIN)
        pos = (await server.inventory_lookup(q="WR-1", user=ADMIN))[0]
        assert (pos["reserved"], pos["available"]) == (0, 10)
    run(go())


def test_manual_movements_keep_item_qty_in_step():
    async def go():
        await _item()
        mv = await server.create_stock_movement(StockMovementCreate(type="Receipt", product_id="WR-1", qty=5),
                                                user=ADMIN)
        assert await _item_qty() == 15
        await server.create_stock_movement(StockMovementCreate(type="Reservation", product_id="WR-1", qty=3),
                                           user=ADMIN)
        assert await _item_qty() == 15                      # holding stock doesn't move it
        await server.delete_stock_movement(mv["id"], user=ADMIN)
        assert await _item_qty() == 10
    run(go())


def test_tally_fields_cannot_be_typed_in():
    async def go():
        await _item()
        out = await update_item("i-WR-1", {"tally_qty": 999, "name": "Wardrobe"}, user=ADMIN)
        assert out.get("tally_qty") is None and out["name"] == "Wardrobe"
    run(go())
