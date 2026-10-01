"""Invoicing: server numbering per FY, money from payments not the form,
sale-linked invoices mirror the sale, IGST from place of supply."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc  # noqa: E402
import server  # noqa: E402
import tenancy  # noqa: E402
from models import InvoiceCreate, PaymentCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "globex", "name": "G", "role": "admin", "username": "g"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["invoicing"])


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


create_inv = _route("/api/invoices", "POST")
update_inv = _route("/api/invoices/{item_id}", "PUT")
LINE = {"description": "Wardrobe", "qty": 1, "rate": 100000, "tax_pct": 18}


def run(c):
    return asyncio.run(c)


async def _get(inv_id, user=ADMIN):
    return await server.db.invoices.find_one(tenancy.scope({"id": inv_id}, "invoices", user), {"_id": 0})


def test_numbers_are_server_side_per_fy_and_unique():
    async def go():
        a = await create_inv(InvoiceCreate(date="2026-10-01", customer="A", line_items=[LINE]), user=ADMIN)
        b = await create_inv(InvoiceCreate(date="2026-10-02", customer="B", line_items=[LINE]), user=ADMIN)
        assert a["invoice_no"] == "MAD/26-27/0001" and b["invoice_no"] == "MAD/26-27/0002"
        with pytest.raises(HTTPException) as e:
            await create_inv(InvoiceCreate(invoice_no=a["invoice_no"], date="2026-10-03", customer="C"), user=ADMIN)
        assert e.value.status_code == 409
        # Another tenant starts its own series.
        c = await create_inv(InvoiceCreate(date="2026-10-01", customer="X", line_items=[LINE]), user=OTHER)
        assert c["invoice_no"] == "MAD/26-27/0001"
    run(go())


def test_paid_comes_from_payments_and_survives_edits():
    async def go():
        inv = await create_inv(InvoiceCreate(date="2026-10-01", customer="A", line_items=[LINE], paid=99999),
                               user=ADMIN)
        assert inv["paid"] == 0 and inv["balance"] == 118000
        pay = await server.create_payment(PaymentCreate(date="2026-10-02", amount=18000,
                                                        against_invoice_id=inv["id"]), user=ADMIN)
        assert (await _get(inv["id"]))["balance"] == 100000
        # An edit from a stale form can't wipe the payment or fake "Paid".
        out = await update_inv(inv["id"], {"notes": "x", "paid": 0, "balance": 0, "status": "Paid"}, user=ADMIN)
        assert out["paid"] == 18000 and out["balance"] == 100000 and out["status"] == "Sent"
        await server.create_payment(PaymentCreate(date="2026-10-03", amount=100000,
                                                  against_invoice_id=inv["id"]), user=ADMIN)
        assert (await _get(inv["id"]))["status"] == "Paid"
        await server.delete_payment(pay["id"], user=ADMIN)   # deleting reverses it on the invoice too
        after = await _get(inv["id"])
        assert after["paid"] == 100000 and after["balance"] == 18000 and after["status"] == "Sent"
    run(go())


def test_igst_follows_place_of_supply():
    async def go():
        inv = await create_inv(InvoiceCreate(date="2026-10-01", customer="A", place_of_supply="Karnataka",
                                             line_items=[LINE]), user=ADMIN)
        assert inv["is_igst"] and inv["igst"] == 18000 and inv["cgst"] == 0
        inv = await update_inv(inv["id"], {"place_of_supply": "Telangana"}, user=ADMIN)
        assert not inv["is_igst"] and inv["cgst"] == 9000 and inv["sgst"] == 9000
    run(go())


async def _sale_with_quote():
    db = server.db
    q = {"id": "Q1", "quote_no": "AF-1", "date": "2026-09-01", "customer": "Anita", "phone": "9876543210",
         "tax_pct": 18, "discount": 10000, "version": 1, "subtotal": 100000}
    await db.quotes.insert_one(tenancy.stamp(dict(q), "quotes", ADMIN))
    for i, (desc, w, h, rate) in enumerate((("Wardrobe", 10, 8, 1000), ("Loft", 5, 4, 1000))):
        await db.quote_lines.insert_one(tenancy.stamp(
            {"id": f"L{i}", "quote_id": "Q1", "version": 1, "description": desc, "w": w, "h": h,
             "qty": 1, "rate": rate, "created_at": f"2026-09-01T0{i}"}, "quote_lines", ADMIN))
    sale = {"id": "S1", "sale_no": "MF 001", "quote_id": "Q1", "customer": "Anita", "phone": "9876543210",
            "value": 118000, "paid": 0, "balance": 118000, "date": "2026-09-05"}
    await db.sales.insert_one(tenancy.stamp(dict(sale), "sales", ADMIN))
    await db.projects.insert_one(tenancy.stamp({"id": "P1", "sale_id": "S1", "site_address": "Kondapur"},
                                               "projects", ADMIN))


def test_invoice_from_sale_matches_the_quote_and_mirrors_sale_payments():
    async def go():
        await _sale_with_quote()
        inv = await server.invoice_from_sale("S1", user=ADMIN)
        # 100 sqft x 1000 = 1,00,000 less 10,000 discount = 90,000 + 18% GST = 1,06,200
        assert inv["subtotal"] == 90000 and inv["total"] == 106200
        assert inv["line_items"][0]["unit"] == "sqft" and inv["line_items"][0]["qty"] == 80
        assert (inv["sale_id"], inv["project_id"], inv["quote_id"]) == ("S1", "P1", "Q1")
        assert inv["billing_address"] == "Kondapur"
        assert (await server.invoice_from_sale("S1", user=ADMIN))["id"] == inv["id"]  # idempotent
        await server.create_payment(PaymentCreate(date="2026-10-01", amount=50000, against_sale_id="S1"), user=ADMIN)
        got = await _get(inv["id"])
        assert got["paid"] == 50000 and got["balance"] == 56200
        with pytest.raises(HTTPException):
            await server.invoice_from_sale("S1", user=OTHER)
    run(go())


def test_sale_linked_invoice_is_not_counted_twice_in_receivables():
    async def go():
        await _sale_with_quote()
        await server.invoice_from_sale("S1", user=ADMIN)
        out = await server.outstanding_report(user=ADMIN)
        assert out["invoice_outstanding"] == 0
    run(go())


def test_payment_state_rules():
    assert lc.invoice_payment_state(1000, 1000, "Draft")["status"] == "Paid"
    assert lc.invoice_payment_state(1000, 0, "Paid")["status"] == "Sent"
    assert lc.invoice_payment_state(1000, 1000, "Cancelled")["status"] == "Cancelled"
    assert lc.invoice_payment_state(1000, 5000, "Sent")["balance"] == 0
    assert lc.next_invoice_no([{"invoice_no": "MAD/26-27/0009"}, {"invoice_no": "MAD/25-26/0040"}],
                              "MAD", "2026-27") == "MAD/26-27/0010"
