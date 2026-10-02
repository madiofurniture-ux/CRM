"""Tally → CRM import through the connector endpoint: key auth and revocation,
stock items (CRM qty stays the stock of record), ledgers, sales vouchers as
read-only invoices, receipts per bill, idempotent re-imports, company isolation."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tally_import as ti  # noqa: E402
import tenancy  # noqa: E402
from models import InvoiceCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "madio", "name": "Admin", "role": "admin", "username": "admin"}
OTHER = {"id": "u9", "tenant_id": "studio", "name": "S", "role": "admin", "username": "s"}


@pytest.fixture(autouse=True)
def _db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["tally_import"])


def run(c):
    return asyncio.run(c)


def _route(path, method):
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in r.methods:
            return r.endpoint
    raise AssertionError(path)


async def _key(user=ADMIN):
    return (await server.tally_connector_key_create(user=user))["key"]


async def ingest(key, kind, items):
    return await server.tally_ingest({"kind": kind, "items": items, "company": "MADIO Furniture"}, x_tally_key=key)


VOUCHER = {"guid": "g-1", "voucher_no": "MF/101", "date": "20261001", "party": "Anita Rao",
           "party_gstin": "36AAAPA1234A1Z5", "place_of_supply": "Telangana",
           "lines": [{"item": "Wardrobe 3 Door", "qty": "2", "rate": "50,000.00", "amount": "1,00,000.00",
                      "hsn": "9403", "gst_pct": "18"}],
           "subtotal": "1,00,000.00", "cgst": "9,000.00", "sgst": "9,000.00", "total": "1,18,000.00"}


def test_keys_are_per_company_shown_once_and_revocable():
    async def go():
        with pytest.raises(HTTPException) as e:
            await ingest("mtc_nope", "ledgers", [])
        assert e.value.status_code == 401
        k1 = await _key()
        assert (await ingest(k1, "ledgers", []))["received"] == 0
        k2 = await _key()                                  # issuing a new key revokes the old one
        with pytest.raises(HTTPException):
            await ingest(k1, "ledgers", [])
        await ingest(k2, "ledgers", [{"name": "Anita Rao"}])
        assert await server.db.customers.count_documents({"tenant_id": "madio"}) == 1
        assert await server.db.customers.count_documents({"tenant_id": "studio"}) == 0
        status = await server.tally_connector_status(user=ADMIN)
        assert status["key"]["prefix"] == k2[:10] and "key_hash" not in status["key"]
        assert (await server.tally_connector_status(user=OTHER))["key"] is None
    run(go())


def test_stock_items_sit_alongside_crm_stock_and_can_be_reconciled():
    async def go():
        k = await _key()
        await server.db.inventory.insert_one(tenancy.stamp(
            {"id": "i1", "sku": "WR-1", "name": "Wardrobe 3 Door", "qty": 5, "mrp": 50000}, "inventory", ADMIN))
        out = await ingest(k, "stock_items", [
            {"name": "Wardrobe 3 Door", "closing_qty": "7", "rate": "48000", "hsn": "9403", "gst_pct": "18"},
            {"name": "Teak Chair", "part_no": "CH-9", "closing_qty": "12 Nos", "rate": "4,500"},
            {"closing_qty": "1"}])
        assert (out["updated"], out["created"], out["error_count"]) == (1, 1, 1)
        wr = await server.db.inventory.find_one({"sku": "WR-1"})
        assert (wr["qty"], wr["tally_qty"], wr["hsn"]) == (5, 7, "9403")      # CRM qty untouched
        ch = await server.db.inventory.find_one({"sku": "CH-9"})
        assert (ch["qty"], ch["tally_qty"], ch["source"]) == (0, 12, "tally")
        diff = await server.inventory_tally_compare(user=ADMIN)
        assert [(r["sku"], r["difference"]) for r in diff] == [("CH-9", 12), ("WR-1", 2)]
        await server.inventory_accept_tally_qty("WR-1", user=ADMIN)
        assert (await server.db.inventory.find_one({"sku": "WR-1"}))["qty"] == 7
        mv = await server.db.stock_movements.find_one({"product_id": "WR-1"})
        assert mv["type"] == "Adjustment" and mv["qty"] == 2
    run(go())


def test_ledgers_fill_gaps_but_never_overwrite_crm_details():
    async def go():
        k = await _key()
        await server.db.customers.insert_one(tenancy.stamp(
            {"id": "c1", "name": "Anita Rao", "phone": "9876543210", "address": "Kondapur"}, "customers", ADMIN))
        await ingest(k, "ledgers", [{"name": "anita  rao", "gstin": "36aaapa1234a1z5", "address": "Other road",
                                     "phone": "9000000000", "closing_balance": "18,000.00"}])
        c = await server.db.customers.find_one({"id": "c1"})
        assert (c["address"], c["phone"], c["gstin"], c["tally_outstanding"]) == \
               ("Kondapur", "9876543210", "36AAAPA1234A1Z5", 18000)
    run(go())


def test_sales_vouchers_become_read_only_invoices_and_reimport_updates_in_place():
    async def go():
        k = await _key()
        await server.db.inventory.insert_one(tenancy.stamp(
            {"id": "i1", "sku": "WR-1", "name": "Wardrobe 3 Door", "qty": 5}, "inventory", ADMIN))
        out = await ingest(k, "sales_vouchers", [VOUCHER])
        assert out["created"] == 1
        inv = await server.db.invoices.find_one({"tally_guid": "g-1"}, {"_id": 0})
        assert (inv["invoice_no"], inv["date"], inv["total"], inv["balance"], inv["status"], inv["source"]) == \
               ("MF/101", "2026-10-01", 118000, 118000, "Sent", "tally")
        assert inv["line_items"][0]["sku"] == "WR-1"
        assert (await server.db.inventory.find_one({"sku": "WR-1"}))["qty"] == 5     # Tally sales don't move CRM stock
        await ingest(k, "sales_vouchers", [{**VOUCHER, "total": "1,20,000.00"}])
        assert await server.db.invoices.count_documents({"tally_guid": "g-1"}) == 1
        assert (await server.db.invoices.find_one({"tally_guid": "g-1"}))["total"] == 120000
        with pytest.raises(HTTPException) as e:
            await _route("/api/invoices/{item_id}", "PUT")(inv["id"], {"notes": "edit"}, user=ADMIN)
        assert "Tally" in e.value.detail
        await ingest(k, "sales_vouchers", [{**VOUCHER, "cancelled": True}])
        assert (await server.db.invoices.find_one({"tally_guid": "g-1"}))["status"] == "Cancelled"
    run(go())


def test_a_tally_number_already_used_by_a_crm_invoice_is_reported_not_merged():
    async def go():
        k = await _key()
        await _route("/api/invoices", "POST")(InvoiceCreate(invoice_no="MF/101", date="2026-10-01", customer="X"),
                                              user=ADMIN)
        out = await ingest(k, "sales_vouchers", [VOUCHER])
        assert out["skipped"] == 1 and "raised in the CRM" in out["errors"][0]
    run(go())


def test_receipts_settle_tally_invoices_per_bill_and_cancellations_reverse():
    async def go():
        k = await _key()
        await ingest(k, "sales_vouchers", [VOUCHER])
        receipt = {"guid": "r-1", "voucher_no": "R/7", "date": "02-Oct-2026", "party": "Anita Rao",
                   "amount": "1,00,000", "mode": "HDFC Bank", "bill_refs": [{"name": "MF/101", "amount": "90,000"}]}
        out = await ingest(k, "receipts", [receipt])
        assert out["created"] == 2                                    # 90,000 on the bill + 10,000 on account
        inv = await server.db.invoices.find_one({"tally_guid": "g-1"})
        assert (inv["paid"], inv["balance"]) == (90000, 28000)
        await ingest(k, "receipts", [receipt])                        # re-import: no duplicates
        assert await server.db.payments.count_documents({"source": "tally"}) == 2
        await ingest(k, "receipts", [{**receipt, "cancelled": True}])
        inv = await server.db.invoices.find_one({"tally_guid": "g-1"})
        assert (inv["paid"], inv["balance"]) == (0, 118000)
    run(go())


def test_receipt_against_a_crm_invoice_is_kept_unlinked():
    async def go():
        k = await _key()
        crm = await _route("/api/invoices", "POST")(InvoiceCreate(date="2026-10-01", customer="X", line_items=[
            {"description": "a", "qty": 1, "rate": 1000, "tax_pct": 18}]), user=ADMIN)
        out = await ingest(k, "receipts", [{"guid": "r-2", "voucher_no": "R/8", "date": "20261002", "party": "X",
                                            "amount": "1180", "bill_refs": [{"name": crm["invoice_no"], "amount": "1180"}]}])
        assert "counted twice" in out["errors"][0]
        assert (await server.db.invoices.find_one({"id": crm["id"]}))["paid"] == 0
    run(go())


def test_parsing_helpers():
    assert ti.tally_date("1-Oct-2026") == "2026-10-01" and ti.tally_date("20261001") == "2026-10-01"
    assert ti._num("1,20,000.50 Dr") == 120000.5 and ti._num("(250)") == -250
    assert ti.sku_for({"name": "Teak Chair 4' x 2'"}) == "T-TEAK-CHAIR-4-X-2"
    with pytest.raises(ValueError):
        ti.validate_batch("vouchers", [])
