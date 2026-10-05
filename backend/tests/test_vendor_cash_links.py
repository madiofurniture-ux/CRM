"""Vendor / cash / stock links: one sales order has many POs, a PO has one
vendor order, a payment against an invoice lands on its order, vendor payouts
name the PO they settle, a receipt banks to exactly one wallet entry, and stock
movements carry typed ids. Goes through the real routes."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_lineage as fl  # noqa: E402
import relations as rel  # noqa: E402
import server  # noqa: E402
from models import (  # noqa: E402
    CashbookEntryCreate, ManufacturerOrderCreate, PaymentCreate, PurchaseOrderCreate, StockMovementCreate,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin", "username": "g"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    mock = AsyncMongoMockClient()["vendor_cash_links"]
    monkeypatch.setattr(server, "db", mock)
    return mock


def run(coro):
    return asyncio.run(coro)


def _route(path, method="GET"):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route")


create_po = _route("/api/purchase-orders", "POST")
update_po = _route("/api/purchase-orders/{item_id}", "PUT")
delete_po = _route("/api/purchase-orders/{item_id}", "DELETE")
create_mo = _route("/api/manufacturer-orders", "POST")
update_mo = _route("/api/manufacturer-orders/{item_id}", "PUT")
delete_mo = _route("/api/manufacturer-orders/{item_id}", "DELETE")
create_payment = _route("/api/payments", "POST")
delete_payment = _route("/api/payments/{item_id}", "DELETE")
create_entry = _route("/api/cashbooks/{cashbook_id}/entries", "POST")
delete_entry = _route("/api/cashbook-entries/{entry_id}", "DELETE")
create_move = _route("/api/stock-movements", "POST")
po_payments = _route("/api/purchase-orders/{po_id}/payments", "GET")


async def seed(user=ADMIN):
    """customer c1 → project p1 with two sales orders s1/s2, vendor v1, a wallet w1, stock item."""
    db = server.db
    t = user["tenant_id"]
    await db.customers.insert_one({"id": "c1", "tenant_id": t, "name": "Ravi", "phone": "9876543210"})
    await db.projects.insert_one({"id": "p1", "tenant_id": t, "customer_id": "c1", "customer": "Ravi"})
    for sid, qid in (("s1", "q1"), ("s2", "q2")):
        await db.sales.insert_one({"id": sid, "tenant_id": t, "customer_id": "c1", "project_id": "p1",
                                   "quote_id": qid, "sale_no": sid.upper(), "value": 100000, "paid": 0})
    await db.vendors.insert_one({"id": "v1", "tenant_id": t, "name": "Sharma", "code": "VEN-1"})
    await db.cashbooks.insert_one({"id": "w1", "tenant_id": t, "book_name": "Site float", "status": "ACTIVE",
                                   "current_balance": 50000})
    await db.inventory.insert_one({"id": "i1", "tenant_id": t, "sku": "SKU1", "name": "Plywood", "qty": 10})


def po(**kw):
    line = {"description": "Ply", "qty": 1, "rate": 1000, "tax_pct": 18}
    return PurchaseOrderCreate(vendor_id="v1", status="Issued", line_items=[line], **kw)


def test_po_and_vendor_order_name_their_sales_order():
    async def go():
        await seed()
        a = await create_po(po(sale_id="s1"), user=ADMIN)
        assert (a["sale_id"], a["project_id"], a["customer_id"], a["quote_id"]) == ("s1", "p1", "c1", "q1")
        b = await create_po(po(sale_id="s2"), user=ADMIN)       # one order, many POs → each on its own order
        assert b["sale_id"] == "s2"
        with pytest.raises(HTTPException) as e:                 # a PO for another project's order is refused
            await create_po(po(sale_id="s1", project_id="p-other"), user=ADMIN)
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            await create_po(po(sale_id="nope"), user=ADMIN)
        assert e.value.status_code == 400
        m = await create_mo(ManufacturerOrderCreate(vendor_id="v1", po_id=a["id"], actual_amount=500), user=ADMIN)
        assert (m["sale_id"], m["project_id"]) == ("s1", "p1")  # inherits from its PO
    run(go())


def test_project_with_one_order_gives_it_to_the_po_but_two_orders_do_not_guess():
    async def go():
        await seed()
        await server.db.sales.delete_one({"id": "s2"})
        only = await create_po(po(project_id="p1"), user=ADMIN)
        assert only["sale_id"] == "s1"
        await server.db.sales.insert_one({"id": "s2", "tenant_id": "acme", "project_id": "p1", "customer_id": "c1"})
        two = await create_po(po(project_id="p1"), user=ADMIN)
        assert two["sale_id"] == ""
    run(go())


def test_one_vendor_order_per_po_and_back_pointer():
    async def go():
        await seed()
        p = await create_po(po(sale_id="s1"), user=ADMIN)
        m1 = await create_mo(ManufacturerOrderCreate(vendor_id="v1", po_id=p["id"], actual_amount=500), user=ADMIN)
        assert (await server.db.purchase_orders.find_one({"id": p["id"]}))["manufacturer_order_id"] == m1["id"]
        with pytest.raises(HTTPException) as e:
            await create_mo(ManufacturerOrderCreate(vendor_id="v1", po_id=p["id"], actual_amount=700), user=ADMIN)
        assert e.value.status_code == 409
        # a client can't point a PO at an order from the PO's side
        await update_po(p["id"], {"manufacturer_order_id": "forged"}, user=ADMIN)
        assert (await server.db.purchase_orders.find_one({"id": p["id"]}))["manufacturer_order_id"] == m1["id"]
        # moving the order to another PO frees the first
        p2 = await create_po(po(sale_id="s1"), user=ADMIN)
        await update_mo(m1["id"], {"po_id": p2["id"]}, user=ADMIN)
        assert (await server.db.purchase_orders.find_one({"id": p["id"]}))["manufacturer_order_id"] == ""
        assert (await server.db.purchase_orders.find_one({"id": p2["id"]}))["manufacturer_order_id"] == m1["id"]
        await delete_mo(m1["id"], user=ADMIN)
        assert (await server.db.purchase_orders.find_one({"id": p2["id"]}))["manufacturer_order_id"] == ""
        m2 = await create_mo(ManufacturerOrderCreate(vendor_id="v1", po_id=p["id"], actual_amount=1), user=ADMIN)
        await delete_po(p["id"], user=ADMIN)
        assert (await server.db.manufacturer_orders.find_one({"id": m2["id"]}))["po_id"] == ""
    run(go())


def test_payment_against_invoice_lands_on_its_order_and_invoice_follows():
    async def go():
        await seed()
        await server.db.invoices.insert_one({"id": "inv1", "tenant_id": "acme", "sale_id": "s1", "project_id": "p1",
                                             "customer_id": "c1", "total": 100000, "status": "Sent",
                                             "date": "2026-01-01", "paid": 0})
        pay = await create_payment(PaymentCreate(date="2026-01-02", amount=40000, against_invoice_id="inv1"),
                                   user=ADMIN)
        assert (pay["against_sale_id"], pay["project_id"], pay["customer_id"]) == ("s1", "p1", "c1")
        assert (await server.db.sales.find_one({"id": "s1"}))["paid"] == 40000
        inv = await server.db.invoices.find_one({"id": "inv1"})
        assert (inv["paid"], inv["balance"]) == (40000, 60000)
        with pytest.raises(HTTPException) as e:        # an invoice of another order contradicts
            await create_payment(PaymentCreate(date="2026-01-02", amount=1, against_invoice_id="inv1",
                                               against_sale_id="s2"), user=ADMIN)
        assert e.value.status_code == 400
    run(go())


def test_vendor_payout_names_its_po_and_is_not_double_counted():
    async def go():
        await seed()
        p = await create_po(po(sale_id="s1"), user=ADMIN)
        m = await create_mo(ManufacturerOrderCreate(vendor_id="v1", po_id=p["id"], actual_amount=500), user=ADMIN)
        e = await create_entry("w1", CashbookEntryCreate(cashbook_id="w1", type="CASH_OUT", amount=300,
                                                         purchase_order_id=p["id"]), user=ADMIN)
        assert (e["vendor_id"], e["sale_id"], e["project_id"], e["manufacturer_order_id"]) == ("v1", "s1", "p1", m["id"])
        assert fl.costed_elsewhere(e)
        out = await po_payments(p["id"], user=ADMIN)
        assert (out["paid"], out["balance"]) == (300, round(p["grand_total"] - 300, 2))
        with pytest.raises(HTTPException) as err:      # vendor of another order
            await create_entry("w1", CashbookEntryCreate(cashbook_id="w1", type="CASH_OUT", amount=1,
                                                         purchase_order_id=p["id"], vendor_id="zzz"), user=ADMIN)
        assert err.value.status_code == 400
        with pytest.raises(HTTPException) as err:      # money in against a PO makes no sense
            await create_entry("w1", CashbookEntryCreate(cashbook_id="w1", type="CASH_IN", amount=1,
                                                         purchase_order_id=p["id"]), user=ADMIN)
        assert err.value.status_code == 400
    run(go())


def test_vendor_links_never_cross_tenants():
    async def go():
        await seed()
        p = await create_po(po(sale_id="s1"), user=ADMIN)
        await server.db.cashbooks.insert_one({"id": "wg", "tenant_id": "globex", "book_name": "G", "status": "ACTIVE",
                                              "current_balance": 0})
        with pytest.raises(HTTPException) as err:
            await create_entry("wg", CashbookEntryCreate(cashbook_id="wg", type="CASH_OUT", amount=1,
                                                         purchase_order_id=p["id"]), user=OTHER)
        assert err.value.status_code == 400
    run(go())


def test_receipt_banks_to_exactly_one_wallet_entry():
    async def go():
        await seed()
        pay = await create_payment(PaymentCreate(date="2026-01-02", amount=5000, against_sale_id="s1",
                                                 wallet_id="w1", mode="UPI"), user=ADMIN)
        assert pay["cashbook_entry_id"]
        entry = await server.db.cashbook_entries.find_one({"id": pay["cashbook_entry_id"]})
        assert (entry["type"], entry["customer_payment_id"], entry["sale_id"], entry["project_id"]) == (
            "CASH_IN", pay["id"], "s1", "p1")
        assert (await server.db.cashbooks.find_one({"id": "w1"}))["current_balance"] == 55000
        assert "wallet_id" not in await server.db.payments.find_one({"id": pay["id"]})
        # a second entry for the same receipt is refused
        with pytest.raises(HTTPException) as err:
            await create_entry("w1", CashbookEntryCreate(cashbook_id="w1", type="CASH_IN", amount=5000,
                                                         customer_payment_id=pay["id"]), user=ADMIN)
        assert err.value.status_code == 409
        # the receipt can't be deleted out from under its wallet entry …
        with pytest.raises(HTTPException) as err:
            await delete_payment(pay["id"], user=ADMIN)
        assert err.value.status_code == 409
        # … but once the entry goes, the receipt is free again
        await delete_entry(entry["id"], user=ADMIN)
        assert (await server.db.payments.find_one({"id": pay["id"]}))["cashbook_entry_id"] == ""
        assert (await server.db.cashbooks.find_one({"id": "w1"}))["current_balance"] == 50000
    run(go())


def test_client_cannot_set_the_receipt_back_pointer_or_use_a_foreign_wallet():
    async def go():
        await seed()
        pay = await create_payment(PaymentCreate(date="2026-01-02", amount=1, cashbook_entry_id="forged"), user=ADMIN)
        assert pay["cashbook_entry_id"] == ""
        with pytest.raises(HTTPException) as err:
            await create_payment(PaymentCreate(date="2026-01-02", amount=1, wallet_id="nope"), user=ADMIN)
        assert err.value.status_code == 404
        assert await server.db.payments.count_documents({}) == 1      # nothing saved on the failed one
    run(go())


def test_stock_movements_carry_typed_ids():
    async def go():
        await seed()
        p = await create_po(po(sale_id="s1", project_id="p1"), user=ADMIN)
        mv = await create_move(StockMovementCreate(type="Receipt", product_id="SKU1", qty=3, purchase_order_id=p["id"]),
                               user=ADMIN)
        assert (mv["inventory_id"], mv["purchase_order_id"], mv["project_id"], mv["customer_id"]) == (
            "i1", p["id"], "p1", "c1")
        with pytest.raises(HTTPException) as err:
            await create_move(StockMovementCreate(type="Receipt", product_id="SKU1", qty=1, sale_id="nope"), user=ADMIN)
        assert err.value.status_code == 400
        # a reservation made through the engine gets the typed sale id from ref_sale_id
        mv2 = await server._post_stock_move({"type": "Reservation", "product_id": "SKU1", "qty": 1,
                                             "ref_sale_id": "s2"}, ADMIN)
        assert (mv2["sale_id"], mv2["inventory_id"], mv2["project_id"]) == ("s2", "i1", "p1")
    run(go())


def test_deal_pnl_counts_a_po_only_on_its_own_order():
    pos = [{"id": "a", "sale_id": "s1", "project_id": "p1"}, {"id": "b", "sale_id": "s2", "project_id": "p1"},
           {"id": "c", "sale_id": "", "project_id": "p1"}]
    assert [x["id"] for x in pos if server._on_deal(x, "p1", {"s1"})] == ["a", "c"]
    assert [x["id"] for x in pos if server._on_deal(x, "p1", {"s2"})] == ["b", "c"]


def test_backfill_links_vendor_stock_and_cash_rows_and_is_idempotent():
    async def go():
        await seed()
        db = server.db
        await db.sales.delete_one({"id": "s2"})
        await db.purchase_orders.insert_one({"id": "po1", "tenant_id": "acme", "po_no": "PO-1", "project_id": "p1",
                                             "vendor_id": "v1", "created_at": "1"})
        await db.manufacturer_orders.insert_many([
            {"id": "m1", "tenant_id": "acme", "po_id": "po1", "vendor_id": "v1", "created_at": "1"},
            {"id": "m2", "tenant_id": "acme", "po_id": "po1", "vendor_id": "v1", "created_at": "2"}])
        await db.cashbook_entries.insert_one({"id": "e1", "tenant_id": "acme", "type": "CASH_OUT", "amount": 5,
                                              "manufacturer_order_id": "m1"})
        await db.stock_movements.insert_one({"id": "mv1", "tenant_id": "acme", "type": "Receipt", "product_id": "SKU1",
                                             "source_doc": "PO-1", "ref_sale_id": "s1"})
        await db.invoices.insert_one({"id": "inv1", "tenant_id": "acme", "sale_id": "s1"})
        await db.payments.insert_one({"id": "pay1", "tenant_id": "acme", "against_invoice_id": "inv1"})
        await db.sales.insert_one({"id": "sx", "tenant_id": "globex", "project_id": "p1"})
        report = await rel.backfill(db, ADMIN)
        assert (await db.purchase_orders.find_one({"id": "po1"}))["sale_id"] == "s1"
        assert (await db.manufacturer_orders.find_one({"id": "m1"}))["sale_id"] == "s1"
        assert (await db.purchase_orders.find_one({"id": "po1"}))["manufacturer_order_id"] == "m1"
        assert report["vendor orders sharing a purchase order (review)"] == 1
        e = await db.cashbook_entries.find_one({"id": "e1"})
        assert (e["vendor_id"], e["purchase_order_id"]) == ("v1", "po1")
        mv = await db.stock_movements.find_one({"id": "mv1"})
        assert (mv["inventory_id"], mv["sale_id"], mv["purchase_order_id"], mv["project_id"]) == ("i1", "s1", "po1", "p1")
        assert (await db.payments.find_one({"id": "pay1"}))["customer_id"] == "c1"
        assert report["receipts on an invoice but not on its order (review)"] == 1
        assert (await db.sales.find_one({"id": "s1"}))["paid"] == 0          # money untouched
        second = await rel.backfill(db, ADMIN)
        assert not {k for k in second if "(review)" not in k}
    run(go())


def test_open_request_for_a_po_is_not_a_second_pending_cost():
    def lineage(requests):
        return fl.deal_lineage(visitor=None, lead=None, quotes=[], sales=[], project=None, pos=[], mos=[],
                               entries=[], petty=[], requests=requests, payments=[], payouts=[])
    plain = {"id": "r1", "amount": 700, "status": "Pending review", "title": "x"}
    vendor = {"id": "r2", "amount": 900, "status": "Pending review", "title": "y", "purchase_order_id": "po1"}
    assert lineage([plain, vendor])["pnl"]["pending_expenses"] == lineage([plain])["pnl"]["pending_expenses"] == 700
