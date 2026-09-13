"""Manufacturer orders: sequential coding, tax math, server-side settlement,
the Other/Direct-Settlement privacy mask, and the project P&L roll-up.

Same harness as test_purchase_orders.py — real functions, server.db on
mongomock — and the masking half is written to the standard of
test_cashbook_masking.py: the claim is not that a screen declines to render a
number, it is that the masked response does not contain it and that no
arithmetic over what IS in the response puts it back.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
import lifecycle as lc  # noqa: E402
import tenancy  # noqa: E402
from models import (  # noqa: E402
    ManufacturerOrderCreate, ManufacturerPayment, MO_COMMITTED_STATUSES,
    manufacturer_order_totals, mask_manufacturer_order,
)

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
SALES = {"id": "u2", "tenant_id": "acme", "name": "Floor Staff", "role": "user"}
OTHER_TENANT = {"id": "u9", "tenant_id": "globex", "name": "Globex", "role": "admin"}

# Order arithmetic, chosen so that no two of these numbers coincide and no
# sum or difference of the visible ones lands on the masked figure by luck:
#     actual 90000 + 18% tax 16200 = final 106200
#     split: 71200 by bank transfer, 35000 direct
# SECRET is the direct-settlement figure the privacy mask exists to redact.
ACTUAL, RATE, TAX, FINAL = 90000.0, 18.0, 16200.0, 106200.0
BANK_DUE, SECRET = 71200.0, 35000.0


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["mo_test"])
    monkeypatch.setattr(csv_engine, "db", server.db, raising=False)
    yield


def _route(path: str, method: str = "GET"):
    """The real registered handler for a make_crud-generated route — testing
    the helper alone would prove the mask works and nothing about whether the
    route is wired to it."""
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route registered")


list_orders = _route("/api/manufacturer-orders")
update_order = _route("/api/manufacturer-orders/{item_id}", "PUT")


async def _make_manufacturer(user=ADMIN, vid="v1"):
    doc = {"id": vid, "name": "Sharma Woodworks", "code": "VEN-007",
           "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(doc, "vendors", user)
    await server.db.vendors.insert_one(dict(doc))
    return doc


async def _make_order(status="Confirmed", project_id="", user=ADMIN, oid="mo1"):
    """One order through the real normalizer, so the stored shape is exactly
    what the routes would have written."""
    await _make_manufacturer(user=user)
    doc = {"vendor_id": "v1", "division": "Furniture", "project_id": project_id,
           "site_location": "Jubilee Hills", "description": "Wardrobe shutters",
           "quote_no": "SW/Q/114", "actual_amount": ACTUAL, "tax_rate": RATE,
           "bank_due": BANK_DUE, "other_due": SECRET, "status": status}
    await server.normalize_manufacturer_order(doc, None, user)
    doc.update(id=oid, created_at="2026-01-01T00:00:00+00:00")
    tenancy.stamp(doc, "manufacturer_orders", user)
    await server.db.manufacturer_orders.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# --------------------------------------------------------------- order codes
def test_order_code_is_sequential_and_dated():
    first = lc.next_manufacturer_order_no([])
    assert first.startswith("MO-") and first.endswith("-001")
    assert lc.next_manufacturer_order_no([{"order_code": first}]).endswith("-002")


def test_order_code_is_assigned_server_side_and_keeps_counting():
    """Two people raising an order at once must never be handed the same
    code, so the client never supplies one."""
    async def run():
        await _make_manufacturer()
        first = {"vendor_id": "v1", "order_code": "MO-CLIENT-PICKED"}
        await server.normalize_manufacturer_order(first, None, ADMIN)
        assert first["order_code"].startswith("MO-") and first["order_code"].endswith("-001")

        first.update(id="mo1", created_at="2026-01-01T00:00:00+00:00")
        tenancy.stamp(first, "manufacturer_orders", ADMIN)
        await server.db.manufacturer_orders.insert_one(dict(first))

        second = {"vendor_id": "v1"}
        await server.normalize_manufacturer_order(second, None, ADMIN)
        assert second["order_code"].endswith("-002")
    asyncio.run(run())


def test_order_code_is_immutable_once_raised():
    async def run():
        await _make_manufacturer()
        existing = {"id": "mo1", "vendor_id": "v1", "order_code": "MO-2601-001"}
        doc = {"order_code": "MO-HACKED"}
        await server.normalize_manufacturer_order(doc, existing, ADMIN)
        assert "order_code" not in doc
    asyncio.run(run())


def test_order_code_sequence_is_tenant_scoped():
    async def run():
        await _make_order(oid="mo1")
        await _make_manufacturer(user=OTHER_TENANT, vid="v2")
        theirs = {"vendor_id": "v2"}
        await server.normalize_manufacturer_order(theirs, None, OTHER_TENANT)
        assert theirs["order_code"].endswith("-001")
    asyncio.run(run())


# ----------------------------------------------------------------- tax maths
def test_totals_reuse_the_document_tax_helper():
    """One agreed amount at one rate is exactly lc.quote_total's shape —
    po_totals/invoice_totals roll per-line HSN slabs up and there are no
    lines here to roll. A third parallel tax calculator would be a third
    place for the same maths to drift."""
    t = manufacturer_order_totals({"actual_amount": ACTUAL, "tax_rate": RATE})
    assert t == {"actual_amount": ACTUAL, "tax_amount": TAX, "final_total": FINAL}


def test_zero_rate_is_respected_and_not_silently_taxed():
    t = manufacturer_order_totals({"actual_amount": 50000, "tax_rate": 0})
    assert t["tax_amount"] == 0
    assert t["final_total"] == 50000


def test_client_supplied_totals_are_always_overwritten():
    """The order authorises money out of the business, so a tampered
    final_total sent from a browser must not survive — same rule as
    normalize_purchase_order."""
    async def run():
        await _make_manufacturer()
        doc = {"vendor_id": "v1", "actual_amount": ACTUAL, "tax_rate": RATE,
               "tax_amount": 1.0, "final_total": 1.0}
        await server.normalize_manufacturer_order(doc, None, ADMIN)
        assert doc["tax_amount"] == TAX
        assert doc["final_total"] == FINAL
    asyncio.run(run())


def test_an_order_with_no_split_stated_defaults_to_fully_bank_settled():
    """Silence must not land money in the Other bucket — the official leg is
    the safe default."""
    async def run():
        await _make_manufacturer()
        doc = {"vendor_id": "v1", "actual_amount": ACTUAL, "tax_rate": RATE}
        await server.normalize_manufacturer_order(doc, None, ADMIN)
        assert doc["bank_due"] == FINAL
        assert doc["other_due"] == 0
        assert doc["total_balance_due"] == FINAL
    asyncio.run(run())


# ------------------------------------------------------- create / normalize
def test_a_manufacturer_is_required():
    with pytest.raises(ValidationError):
        ManufacturerOrderCreate(actual_amount=1000, vendor_id="")


def test_status_must_be_a_known_production_state():
    with pytest.raises(ValidationError):
        ManufacturerOrderCreate(vendor_id="v1", status="Teleported")


def test_normalize_derives_the_manufacturer_from_the_vendor_row():
    """Manufacturers are vendors — no parallel entity, and no client-supplied
    name, or a redacted user could write in a name they cannot even read."""
    async def run():
        await _make_manufacturer()
        doc = {"vendor_id": "v1", "vendor_name": "Not This"}
        await server.normalize_manufacturer_order(doc, None, ADMIN)
        assert doc["vendor_name"] == "Sharma Woodworks"
        assert doc["vendor_code"] == "VEN-007"
    asyncio.run(run())


def test_normalize_rejects_an_unknown_manufacturer():
    async def run():
        with pytest.raises(HTTPException) as e:
            await server.normalize_manufacturer_order({"vendor_id": "ghost"}, None, ADMIN)
        assert e.value.status_code == 400
    asyncio.run(run())


def test_normalize_rejects_a_manufacturer_from_another_tenant():
    async def run():
        await _make_manufacturer(user=ADMIN)
        with pytest.raises(HTTPException):
            await server.normalize_manufacturer_order({"vendor_id": "v1"}, None, OTHER_TENANT)
    asyncio.run(run())


def test_normalize_rejects_an_unknown_project_link():
    async def run():
        await _make_manufacturer()
        with pytest.raises(HTTPException):
            await server.normalize_manufacturer_order(
                {"vendor_id": "v1", "project_id": "ghost"}, None, ADMIN)
    asyncio.run(run())


def test_the_payment_ledger_cannot_be_written_through_a_plain_edit():
    """payments/total_paid are only ever written by the payment route.
    Accepting them on a PUT would let a caller mark an order settled without
    a rupee moving."""
    async def run():
        order = await _make_order()
        out = await update_order(
            "mo1",
            {"notes": "chased", "total_paid": 999999,
             "payments": [{"mode": "OTHER", "amount": 999999}]},
            mask_other=False, user=ADMIN)
        assert out["notes"] == "chased"
        assert out["total_paid"] == 0
        assert out["payments"] == []
        assert out["total_balance_due"] == order["total_balance_due"]
    asyncio.run(run())


# ------------------------------------------------------------- settlements
def test_payment_decrements_the_bank_bucket_only():
    async def run():
        await _make_order()
        out = await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="BANK_TRANSFER", amount=20000,
                                       reference_no="UTR-9911"),
            mask_other=False, user=ADMIN)
        assert out["bank_due"] == BANK_DUE - 20000
        assert out["other_due"] == SECRET            # untouched
        assert out["total_paid"] == 20000
        assert out["total_balance_due"] == (BANK_DUE - 20000) + SECRET
        assert out["payments"][0]["reference_no"] == "UTR-9911"
    asyncio.run(run())


def test_payment_decrements_the_direct_settlement_bucket_only():
    async def run():
        await _make_order()
        out = await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000),
            mask_other=False, user=ADMIN)
        assert out["other_due"] == SECRET - 5000
        assert out["bank_due"] == BANK_DUE           # untouched
        assert out["total_balance_due"] == BANK_DUE + (SECRET - 5000)
    asyncio.run(run())


def test_balances_are_recomputed_server_side_not_taken_from_the_client():
    """A posted balance is exactly the number an attacker would want to
    choose — same rule that governs po_totals and invoice_totals."""
    async def run():
        await _make_order()
        out = await server.record_manufacturer_payment(
            "mo1",
            ManufacturerPayment(mode="OTHER", amount=5000,
                                # extra="ignore" drops these before they are
                                # ever looked at; assert the outcome anyway.
                                **{"total_balance_due": 0, "total_paid": 0}),
            mask_other=False, user=ADMIN)
        assert out["total_paid"] == 5000
        assert out["total_balance_due"] == BANK_DUE + SECRET - 5000
    asyncio.run(run())


def test_overpaying_a_bucket_is_refused_not_clamped():
    """Silently absorbing the excess would leave the order's books
    disagreeing with the money that actually moved."""
    async def run():
        await _make_order()
        with pytest.raises(HTTPException) as e:
            await server.record_manufacturer_payment(
                "mo1", ManufacturerPayment(mode="OTHER", amount=SECRET + 1), user=ADMIN)
        assert e.value.status_code == 400

        order = await server.db.manufacturer_orders.find_one({"id": "mo1"}, {"_id": 0})
        assert order["other_due"] == SECRET      # nothing was written
        assert order["payments"] == []
    asyncio.run(run())


def test_a_bank_payment_cannot_be_used_to_drain_the_direct_bucket():
    """The buckets are independent: a bank transfer larger than the bank due
    must not spill over into the Other leg."""
    async def run():
        await _make_order()
        with pytest.raises(HTTPException):
            await server.record_manufacturer_payment(
                "mo1", ManufacturerPayment(mode="BANK_TRANSFER", amount=BANK_DUE + 1),
                user=ADMIN)
    asyncio.run(run())


def test_zero_and_negative_payments_are_refused():
    async def run():
        await _make_order()
        for bad in (0, -5000):
            with pytest.raises(HTTPException):
                await server.record_manufacturer_payment(
                    "mo1", ManufacturerPayment(mode="OTHER", amount=bad), user=ADMIN)
    asyncio.run(run())


def test_a_payment_against_another_tenants_order_is_not_found():
    async def run():
        await _make_order()
        with pytest.raises(HTTPException) as e:
            await server.record_manufacturer_payment(
                "mo1", ManufacturerPayment(mode="OTHER", amount=1000), user=OTHER_TENANT)
        assert e.value.status_code == 404
    asyncio.run(run())


def test_settling_in_full_zeroes_the_balance():
    async def run():
        await _make_order()
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="BANK_TRANSFER", amount=BANK_DUE),
            user=ADMIN)
        out = await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=SECRET),
            mask_other=False, user=ADMIN)
        assert out["total_balance_due"] == 0
        assert out["total_paid"] == FINAL
        assert len(out["payments"]) == 2
    asyncio.run(run())


# --------------------------------------------------------- the wallet leg
async def _wallet(project_id="p1"):
    doc = {"id": "b1", "book_name": "Site Wallet", "initial_balance": 200000,
           "current_balance": 200000, "status": "ACTIVE", "project_id": project_id,
           "assigned_users": [], "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(doc, "cashbooks", ADMIN)
    await server.db.cashbooks.insert_one(dict(doc))


def test_a_wallet_funded_payment_really_debits_the_wallet():
    """Money paid out of a site wallet has left that wallet — the ledger has
    to move with it, same $inc pattern as create_split_payment's credit."""
    async def run():
        await _make_order()
        await _wallet()
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000, wallet_id="b1"),
            user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"}, {"_id": 0})
        assert book["current_balance"] == 195000
        entry = await server.db.cashbook_entries.find_one({"cashbook_id": "b1"}, {"_id": 0})
        assert entry["type"] == "CASH_OUT" and entry["status"] == "Approved"
        assert entry["manufacturer_order_id"] == "mo1"
    asyncio.run(run())


def test_a_payment_without_a_wallet_touches_no_ledger():
    async def run():
        await _make_order()
        await _wallet()
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000), user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"}, {"_id": 0})
        assert book["current_balance"] == 200000
        assert await server.db.cashbook_entries.count_documents({}) == 0
    asyncio.run(run())


# --------------------------------------------------------------- P&L roll-up
async def _project(value=500000):
    doc = {"id": "p1", "project_no": "PRJ-1", "customer": "Acme Co", "value": value,
           "stage": "Execution", "created_at": "2026-01-01T00:00:00+00:00"}
    tenancy.stamp(doc, "projects", ADMIN)
    await server.db.projects.insert_one(dict(doc))


def test_a_committed_order_registers_as_project_material_cost():
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1")
        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == FINAL
        assert row["net_margin"] == 500000 - FINAL
    asyncio.run(run())


def test_a_quoted_order_is_not_yet_committed_spend():
    """An unaccepted manufacturer quotation is not money the business owes
    anyone — the same line PO_COMMITTED_STATUSES draws at Draft."""
    async def run():
        await _project()
        await _make_order(status="Quoted", project_id="p1")
        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == 0
        assert row["net_margin"] == 500000
    asyncio.run(run())


def test_every_post_confirmation_state_counts():
    async def run():
        for status in sorted(MO_COMMITTED_STATUSES):
            await server.db.manufacturer_orders.delete_many({})
            await server.db.projects.delete_many({})
            await _project()
            await _make_order(status=status, project_id="p1")
            row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
            assert row["material_cost"] == FINAL, status
    asyncio.run(run())


def test_manufacturing_cost_rolls_up_tax_inclusive_like_a_purchase_order():
    """material_cost is one column carrying both PO and manufacturer spend.
    A column that is net of GST for half its rows and gross for the other
    half is a wrong number, so this line matches the PO line's grand_total."""
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1")
        po = {"id": "po1", "po_no": "PO-2601-001", "vendor_id": "v1", "project_id": "p1",
              "status": "Issued", "grand_total": 11800, "subtotal": 10000,
              "line_items": [], "created_at": "2026-01-01T00:00:00+00:00"}
        tenancy.stamp(po, "purchase_orders", ADMIN)
        await server.db.purchase_orders.insert_one(dict(po))

        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == FINAL + 11800
        # ...and not the pre-tax figure, which is what a mixed column would give.
        assert row["material_cost"] != ACTUAL + 11800
    asyncio.run(run())


def test_an_unlinked_order_never_touches_any_project():
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="")
        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == 0
    asyncio.run(run())


def test_manufacturing_cost_is_tenant_scoped():
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1")
        assert (await csv_engine.compute_project_pnl(server.db, OTHER_TENANT))["projects"] == []
    asyncio.run(run())


def test_a_wallet_funded_payment_is_not_charged_to_the_project_twice():
    """The order is already in material_cost. Counting its wallet debit as
    petty cash too would charge the same rupee twice and understate margin
    by the amount paid."""
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1")
        await _wallet()
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000, wallet_id="b1"),
            user=ADMIN)

        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["material_cost"] == FINAL
        assert row["approved_petty_cash"] == 0        # not counted a second time
        assert row["net_margin"] == 500000 - FINAL
        # The wallet itself still shows the money gone — the debit is real.
        assert row["float_balance"] == 195000
    asyncio.run(run())


def test_an_ordinary_site_debit_still_counts_as_petty_cash():
    """Guard on the exclusion above: it must key on the manufacturer tag, not
    quietly drop every approved CASH_OUT line."""
    async def run():
        await _project()
        await _wallet()
        entry = {"id": "e1", "cashbook_id": "b1", "type": "CASH_OUT", "status": "Approved",
                 "amount": 4000, "category": "Transport",
                 "created_at": "2026-01-02T00:00:00+00:00"}
        tenancy.stamp(entry, "cashbook_entries", ADMIN)
        await server.db.cashbook_entries.insert_one(dict(entry))

        row = (await csv_engine.compute_project_pnl(server.db, ADMIN))["projects"][0]
        assert row["approved_petty_cash"] == 4000
    asyncio.run(run())


# ------------------------------------------------------------- the mask
def test_masked_order_hides_the_direct_settlement_figure():
    async def run():
        await _make_order()
        rows = await list_orders(mask_other=True, user=ADMIN)
        row = rows[0]

        assert row["other_due"] is None
        assert str(SECRET) not in str(row)
        # Masked, not zeroed — a 0 reads as "nothing outstanding".
        assert row["other_due"] != 0

        # Everything the screen needs to stay legible survives.
        assert row["order_code"].startswith("MO-")
        assert row["status"] == "Confirmed"
        assert row["site_location"] == "Jubilee Hills"
        assert row["quote_no"] == "SW/Q/114"
        assert row["final_total"] == FINAL
    asyncio.run(run())


def test_the_mask_takes_the_whole_settlement_ledger_not_just_the_headline():
    """bank_due cannot stay, however close the parallel with
    mask_settlement's visible bank leg. That one is an independently recorded
    receipt; this one is half a partition of a total that must stay visible,
    so publishing it publishes the other half."""
    async def run():
        await _make_order()
        row = (await list_orders(mask_other=True, user=ADMIN))[0]
        assert row["bank_due"] is None
        assert row["other_due"] is None
        assert row["total_paid"] is None
        assert row["total_balance_due"] is None
    asyncio.run(run())


def test_the_masked_payment_list_cannot_even_be_counted():
    """An itemised list a viewer can COUNT tells them whether anything has
    been paid, and knowing total_paid is 0 collapses the arithmetic to a
    single subtraction. Same reason mask_pnl drops recent_entries wholesale."""
    async def run():
        await _make_order()
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000), user=ADMIN)
        row = (await list_orders(mask_other=True, user=ADMIN))[0]
        assert row["payments"] == []
    asyncio.run(run())


def test_the_order_list_defaults_to_masked_so_an_older_client_fails_closed():
    async def run():
        await _make_order()
        rows = await list_orders(user=ADMIN)  # no flag at all
        assert rows[0]["other_due"] is None
    asyncio.run(run())


def test_unmasked_order_list_still_returns_the_real_settlement():
    """The allow case. A PIN-unlocked viewer must keep the true figures — a
    mask that cannot be lifted is a broken screen, not a secure one."""
    async def run():
        await _make_order()
        row = (await list_orders(mask_other=False, user=ADMIN))[0]
        assert row["other_due"] == SECRET
        assert row["bank_due"] == BANK_DUE
        assert row["total_balance_due"] == BANK_DUE + SECRET
        assert row["total_paid"] == 0
    asyncio.run(run())


def test_the_update_readback_cannot_be_used_to_re_read_the_settlement():
    """The balances are server-maintained, so a PUT hands back something the
    caller never sent. Leaving that unmasked would make a no-op edit a
    one-request bypass of the grid's mask."""
    async def run():
        await _make_order()
        out = await update_order("mo1", {"notes": "touched"}, user=ADMIN)
        assert out["other_due"] is None
        assert out["total_balance_due"] is None
        assert out["notes"] == "touched"
    asyncio.run(run())


def test_the_payment_route_readback_is_masked_too():
    """The most direct bypass of the lot: record a ₹1 payment and read the
    recomputed balance straight out of the response."""
    async def run():
        await _make_order()
        out = await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="BANK_TRANSFER", amount=1), user=ADMIN)
        assert out["other_due"] is None
        assert out["total_balance_due"] is None
        assert out["payments"] == []
        assert str(SECRET) not in str(out)
    asyncio.run(run())


def test_no_arithmetic_over_the_whole_masked_surface_recovers_the_figure():
    """The real claim. Take everything a masked viewer can pull — the order
    grid and the project P&L row the order feeds — and check that no visible
    number, and no sum or difference of any two of them, is the hidden
    figure. This is the check that caught keeping bank_due visible:
    final_total - bank_due was the answer."""
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1")
        await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="OTHER", amount=5000), user=ADMIN)

        orders = await list_orders(mask_other=True, user=ADMIN)
        pnl = await server.project_pnl_report(mask_other=True, user=ADMIN)
        surface = [orders, pnl]

        assert str(SECRET) not in str(surface)
        numbers = _numbers(surface)
        assert SECRET not in numbers
        for a in numbers:
            for b in numbers:
                assert a - b != SECRET, f"{a} - {b} recovers the masked figure"
                assert a + b != SECRET, f"{a} + {b} recovers the masked figure"
    asyncio.run(run())


def _numbers(obj) -> list:
    """Every numeric leaf in a response payload, booleans excluded."""
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [obj]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numbers(v)]
    if isinstance(obj, (list, tuple)):
        return [n for v in obj for n in _numbers(v)]
    return []


def test_mask_returns_a_new_dict_and_never_mutates_in_place():
    """make_crud's list hands out shared references."""
    order = {"id": "mo1", "other_due": SECRET, "bank_due": BANK_DUE,
             "total_paid": 0, "total_balance_due": FINAL, "payments": [{"amount": 1}]}
    masked = mask_manufacturer_order(order)
    assert masked["other_due"] is None
    assert order["other_due"] == SECRET
    assert order["payments"] == [{"amount": 1}]


# ------------------------------------------------- manufacturer name gating
def test_the_manufacturer_name_is_admin_accountant_only():
    """A manufacturer IS a vendors row, so the cost-price sprint's vendor-name
    boundary applies to it — the code stays, the name does not."""
    async def run():
        await _make_order()
        row = (await list_orders(user=SALES))[0]
        assert "vendor_name" not in row
        assert row["vendor_code"] == "VEN-007"

        row = (await list_orders(user=ADMIN))[0]
        assert row["vendor_name"] == "Sharma Woodworks"
    asyncio.run(run())


def test_the_payment_readback_gates_the_manufacturer_name_too():
    async def run():
        await _make_order()
        out = await server.record_manufacturer_payment(
            "mo1", ManufacturerPayment(mode="BANK_TRANSFER", amount=1), user=SALES)
        assert "vendor_name" not in out
        assert "Sharma Woodworks" not in str(out)
    asyncio.run(run())


# ------------------------------------------------------------- list filters
def test_the_list_route_filters_by_division_status_and_project():
    """Allow-listed exact-match params, applied on top of the tenant scope."""
    async def run():
        await _project()
        await _make_order(status="Confirmed", project_id="p1", oid="mo1")
        second = await _make_order(status="Quoted", project_id="", oid="mo2")
        second_code = second["order_code"]

        class _Req:
            def __init__(self, **kw): self.query_params = kw

        rows = await list_orders(_Req(status="Quoted"), mask_other=False, user=ADMIN)
        assert [r["order_code"] for r in rows] == [second_code]

        rows = await list_orders(_Req(project_id="p1"), mask_other=False, user=ADMIN)
        assert len(rows) == 1 and rows[0]["project_id"] == "p1"

        rows = await list_orders(_Req(division="Furniture"), mask_other=False, user=ADMIN)
        assert len(rows) == 2
        rows = await list_orders(_Req(division="D&W"), mask_other=False, user=ADMIN)
        assert rows == []
    asyncio.run(run())


def test_an_unlisted_filter_param_is_ignored_not_passed_to_mongo():
    """The allow-list is the point: a caller must not be able to turn an
    arbitrary field — or a Mongo operator document — into a query filter."""
    async def run():
        await _make_order()

        class _Req:
            query_params = {"vendor_code": "VEN-999", "tenant_id": "globex"}

        rows = await list_orders(_Req(), mask_other=False, user=ADMIN)
        assert len(rows) == 1
    asyncio.run(run())
