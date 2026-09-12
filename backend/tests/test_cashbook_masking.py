"""Privacy-mode masking on the Cashbook routes.

c155c78 closed the mathematical leak on Payments and Project P&L and wrote
down what it had not closed: "the Cashbook screen shows wallet entries
unmasked, so an operator with cashbook access can still reach the underlying
CASH_OUT lines."

That residual is what this file tests. It is a masking hole, not an
access-control one: /reports/project-pnl and /cashbooks/{id}/entries are
gated on the very same `cashbook:view` grant, so the two routes have exactly
the same audience — the mask on one was simply absent on the other, one hop
away through the P&L screen's own "View Linked Wallet" deep-link.

Written to the standard of test_cost_price_security.py: the claim is not
that a screen declines to render a number, it is that the masked response
does not contain it and that no arithmetic over what IS in the response
puts it back.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import csv_engine  # noqa: E402
from models import CashbookTopUp, CashbookExpense, CashbookEntryApproval  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}

# The wallet's arithmetic, chosen so no two of these numbers coincide and a
# leak cannot pass as a false positive:
#     opening 20000 + top-up 5000 - approved 15000 = balance 10000
# SECRET is the figure mask_pnl already redacts as approved_petty_cash.
OPENING, TOP_UP, SECRET, PENDING = 20000, 5000, 15000, 2000
BALANCE = OPENING + TOP_UP - SECRET


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["cashbook_masking_test"])
    yield


def _route(path: str, method: str = "GET"):
    """The real registered handler for a make_crud-generated route.

    The wallet list is a closure inside make_crud, so testing the helper
    alone would prove the mask works and nothing about whether the route is
    wired to it — which is the half that was missing in the first place."""
    for r in server.api.routes:
        if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
            return r.endpoint
    raise AssertionError(f"no {method} {path} route registered")


list_cashbooks = _route("/api/cashbooks")
update_cashbook = _route("/api/cashbooks/{item_id}", "PUT")


async def _wallet_with_spend():
    """One project wallet carrying an approved debit, a pending one, and a
    top-up — the shape the Cashbook screen actually renders."""
    doc = {"book_name": "Site A Wallet", "initial_balance": OPENING,
           "current_balance": OPENING, "status": "ACTIVE", "assigned_users": [],
           "project_id": "p1", "imprest_limit": 50000, "strict_overdraft": False,
           "id": "b1", "created_at": "2026-01-01T00:00:00+00:00"}
    from tenancy import stamp
    stamp(doc, "cashbooks", ADMIN)
    await server.db.cashbooks.insert_one(dict(doc))

    project = {"project_no": "PRJ-1", "customer": "Acme Co", "value": 100000,
               "stage": "Execution", "id": "p1", "created_at": "2026-01-01T00:00:00+00:00"}
    stamp(project, "projects", ADMIN)
    await server.db.projects.insert_one(dict(project))

    await server.cashbook_top_up("b1", CashbookTopUp(amount=TOP_UP), user=ADMIN)
    approved = await server.cashbook_expense(
        "b1", CashbookExpense(amount=SECRET, category="Materials"), user=ADMIN)
    await server.cashbook_entry_approve(
        approved["id"], CashbookEntryApproval(approved=True), user=ADMIN)
    await server.cashbook_expense("b1", CashbookExpense(amount=PENDING), user=ADMIN)

    book = await server.db.cashbooks.find_one({"id": "b1"}, {"_id": 0})
    assert book["current_balance"] == BALANCE, "fixture arithmetic drifted"


# --------------------------------------------------------------- the ledger
def test_masked_entries_do_not_carry_the_amounts_that_sum_to_the_spend_figure():
    """The leak in its plainest form: the P&L hides approved_petty_cash, and
    the wallet it links to itemises the very lines that add up to it."""
    async def run():
        await _wallet_with_spend()
        rows = await server.list_cashbook_entries("b1", mask_other=True, user=ADMIN)

        assert len(rows) == 3                       # top-up, approved debit, pending debit
        assert all(r["amount"] is None for r in rows)
        assert str(SECRET) not in str(rows)
        # Masked, not zeroed — a 0 would read as a real, settled figure.
        assert not any(r["amount"] == 0 for r in rows)

        # Everything the screen needs to stay legible survives.
        assert {r["type"] for r in rows} == {"CASH_IN", "CASH_OUT"}
        assert {r["status"] for r in rows} == {"Approved", "Pending"}
        assert any(r.get("category") == "Materials" for r in rows)
    asyncio.run(run())


def test_masked_entry_list_defaults_to_masked_so_an_older_client_fails_closed():
    async def run():
        await _wallet_with_spend()
        rows = await server.list_cashbook_entries("b1", user=ADMIN)  # no flag at all
        assert all(r["amount"] is None for r in rows)
    asyncio.run(run())


def test_unmasked_entry_list_still_returns_the_real_amounts():
    """The allow case. A PIN-unlocked viewer must keep the true ledger —
    a mask that cannot be lifted is a broken screen, not a secure one."""
    async def run():
        await _wallet_with_spend()
        rows = await server.list_cashbook_entries("b1", mask_other=False, user=ADMIN)
        assert sorted(r["amount"] for r in rows) == sorted([TOP_UP, SECRET, PENDING])
    asyncio.run(run())


# --------------------------------------------------------------- the wallet
def test_masked_wallet_balances_close_the_opening_minus_current_inversion():
    """Blanking the ledger alone is not enough. The balance is the running
    result of those same lines, so

        approved_out = initial_balance + top_ups - current_balance

    and with the top-ups already masked that collapses to a subtraction of
    two numbers sitting side by side on the wallet card. Same defect as
    total_collected in mask_settlement — both halves have to go."""
    async def run():
        await _wallet_with_spend()
        books = await list_cashbooks(mask_other=True, user=ADMIN)
        book = books[0]

        assert book["current_balance"] is None
        assert book["initial_balance"] is None
        assert str(SECRET) not in str(book)

        # The configured ceiling is an input, not a result of spend — it
        # stays, the same line mask_pnl draws when it keeps contract_value.
        assert book["imprest_limit"] == 50000
        assert book["book_name"] == "Site A Wallet"
    asyncio.run(run())


def test_masked_wallet_list_defaults_to_masked():
    async def run():
        await _wallet_with_spend()
        books = await list_cashbooks(user=ADMIN)  # no flag at all
        assert books[0]["current_balance"] is None
    asyncio.run(run())


def test_unmasked_wallet_list_still_returns_the_real_balance():
    async def run():
        await _wallet_with_spend()
        books = await list_cashbooks(mask_other=False, user=ADMIN)
        assert books[0]["current_balance"] == BALANCE
        assert books[0]["initial_balance"] == OPENING
    asyncio.run(run())


def test_the_wallet_update_readback_cannot_be_used_to_re_read_the_balance():
    """current_balance is server-maintained, so the PUT response hands back
    something the caller never sent. Leaving it unmasked would make a no-op
    edit a one-request bypass of the wallet card's mask."""
    async def run():
        await _wallet_with_spend()
        out = await update_cashbook("b1", {"description": "touched"}, user=ADMIN)
        assert out["current_balance"] is None
        assert out["initial_balance"] is None
        assert out["description"] == "touched"
    asyncio.run(run())


# ------------------------------------------------------- no residual at all
def test_no_arithmetic_over_the_whole_masked_surface_recovers_the_spend():
    """The real claim. Take everything a masked viewer with full cashbook
    access can pull — the wallet card, the ledger, and the P&L row that
    links to it — and check that no visible number, and no sum or difference
    of any two of them, is the hidden figure."""
    async def run():
        await _wallet_with_spend()
        books = await list_cashbooks(mask_other=True, user=ADMIN)
        rows = await server.list_cashbook_entries("b1", mask_other=True, user=ADMIN)
        pnl = await server.project_pnl_report(mask_other=True, user=ADMIN)

        surface = [books, rows, pnl]
        assert str(SECRET) not in str(surface)

        numbers = _numbers(surface)
        assert SECRET not in numbers
        for a in numbers:
            for b in numbers:
                assert a - b != SECRET, f"{a} - {b} recovers the masked spend"
                assert a + b != SECRET, f"{a} + {b} recovers the masked spend"
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


def test_float_balance_is_masked_on_the_pnl_side_of_the_same_boundary():
    """The wallet balance is reachable from the P&L too, as the sum of the
    project's wallets. Masking it on one surface and not the other would
    just move the leak."""
    async def run():
        await _wallet_with_spend()
        masked = (await server.project_pnl_report(mask_other=True, user=ADMIN))["projects"][0]
        assert masked["float_balance"] is None

        unmasked = (await server.project_pnl_report(mask_other=False, user=ADMIN))["projects"][0]
        assert unmasked["float_balance"] == BALANCE
    asyncio.run(run())


# ------------------------------------------------------------- the CSV door
def test_masked_csv_export_cannot_be_used_to_bypass_the_on_screen_mask():
    """Same one-click bypass c155c78 had to close on the P&L export."""
    async def run():
        await _wallet_with_spend()
        masked = "".join([chunk async for chunk in
                          csv_engine.stream_cashbook_entries_csv(server.db, ADMIN, True)])
        assert str(SECRET) not in masked
        assert "Materials" in masked          # the ledger is still exportable

        unmasked = "".join([chunk async for chunk in
                            csv_engine.stream_cashbook_entries_csv(server.db, ADMIN, False)])
        assert str(SECRET) in unmasked
    asyncio.run(run())


def test_cashbook_csv_export_route_defaults_to_masked():
    async def run():
        await _wallet_with_spend()
        resp = await server.cashbook_entries_export(user=ADMIN)  # no flag at all
        body = "".join([chunk async for chunk in resp.body_iterator])
        assert str(SECRET) not in body
    asyncio.run(run())
