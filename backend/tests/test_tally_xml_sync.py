"""Tally XML envelope correctness and the UPI review gate.

The XML assertions parse the envelope and walk it, rather than substring
matching: a voucher that merely CONTAINS the right words can still be
rejected by Tally for nesting them wrongly, and a voucher with the debit and
credit signs flipped imports cleanly while posting backwards — which is worse
than a rejection, because it looks like it worked.

The HTTP call is mocked throughout. There is no Tally gateway in this
environment and a test that needed one would be a test that never runs.
"""
import asyncio
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import tally  # noqa: E402
import tenancy  # noqa: E402
from models import CashbookTxnCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin", "username": "admin"}
STAFF = {"id": "u2", "tenant_id": "acme", "name": "Ravi", "role": "user",
         "username": "ravi", "role_id": ""}

PAYMENT_TXN = {"id": "t1", "date": "2026-03-12", "type": "OUT", "payment_mode": "CASH",
               "amount": 5000.0, "from_ledger": "Cash-in-Hand", "to_ledger": "Timber Vendor A",
               "reference_no": "VCH-001", "narration": "Plywood purchase"}
RECEIPT_TXN = {"id": "t2", "date": "2026-03-12", "type": "IN", "payment_mode": "BANK_TRANSFER",
               "amount": 25000.0, "from_ledger": "Customer Sharath", "to_ledger": "HDFC Bank",
               "reference_no": "UTR-99", "narration": "Advance received"}
CONTRA_TXN = {"id": "t3", "date": "2026-03-12", "type": "OUT", "payment_mode": "BANK_TRANSFER",
              "amount": 10000.0, "from_ledger": "HDFC Bank", "to_ledger": "Petty Cash",
              "reference_no": "TRF-7", "narration": "Site float"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["tally_test"])
    yield


def _root(txn):
    return ET.fromstring(tally.build_voucher_xml(txn, "MADIO Furniture"))


def _voucher(txn):
    return _root(txn).find("./BODY/IMPORTDATA/REQUESTDATA/TALLYMESSAGE/VOUCHER")


def _entries(txn):
    return _voucher(txn).findall("ALLLEDGERENTRIES.LIST")


def _entry_for(txn, ledger):
    for e in _entries(txn):
        if e.findtext("LEDGERNAME") == ledger:
            return e
    raise AssertionError(f"no ledger entry for {ledger}")


# ------------------------------------------------------- envelope structure
def test_envelope_has_tallys_required_nesting():
    root = _root(PAYMENT_TXN)
    assert root.tag == "ENVELOPE"
    assert root.findtext("./HEADER/TALLYREQUEST") == "Import Data"
    assert root.findtext("./BODY/IMPORTDATA/REQUESTDESC/REPORTNAME") == "Vouchers"
    assert root.find("./BODY/IMPORTDATA/REQUESTDATA/TALLYMESSAGE/VOUCHER") is not None


def test_company_name_is_carried_in_static_variables():
    root = _root(PAYMENT_TXN)
    assert root.findtext(
        "./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES/SVCURRENTCOMPANY") == "MADIO Furniture"


def test_date_is_yyyymmdd_without_separators():
    assert _voucher(PAYMENT_TXN).findtext("DATE") == "20260312"
    assert _voucher(PAYMENT_TXN).findtext("EFFECTIVEDATE") == "20260312"


def test_voucher_carries_reference_and_narration():
    v = _voucher(PAYMENT_TXN)
    assert v.findtext("REFERENCE") == "VCH-001"
    assert v.findtext("NARRATION") == "Plywood purchase"
    assert v.get("ACTION") == "Create"


# ------------------------------------------------------------ classification
def test_vendor_payout_is_a_payment_voucher():
    assert tally.classify_voucher(PAYMENT_TXN) == "Payment"
    assert _voucher(PAYMENT_TXN).get("VCHTYPE") == "Payment"
    assert _voucher(PAYMENT_TXN).findtext("VOUCHERTYPENAME") == "Payment"


def test_customer_money_in_is_a_receipt_voucher():
    assert tally.classify_voucher(RECEIPT_TXN) == "Receipt"
    assert _voucher(RECEIPT_TXN).get("VCHTYPE") == "Receipt"


def test_bank_to_cash_transfer_is_a_contra_voucher():
    """Both sides are the entity's own money ledgers, so nothing crossed the
    entity boundary — that is precisely what Contra means."""
    assert tally.classify_voucher(CONTRA_TXN) == "Contra"
    assert _voucher(CONTRA_TXN).get("VCHTYPE") == "Contra"


def test_contra_beats_the_in_out_direction():
    """A Contra is classified from its ledgers, not its direction — an
    IN-flagged bank-to-cash move is still a Contra, never a Receipt."""
    assert tally.classify_voucher({**CONTRA_TXN, "type": "IN"}) == "Contra"


# ---------------------------------------------------------- double entry
def test_every_voucher_has_exactly_two_ledger_entries():
    for txn in (PAYMENT_TXN, RECEIPT_TXN, CONTRA_TXN):
        assert len(_entries(txn)) == 2, f"{txn['id']} is not a balanced pair"


def test_destination_ledger_is_debited_with_a_negative_amount():
    """Tally's sign convention: a DEBIT is a negative AMOUNT flagged
    ISDEEMEDPOSITIVE=Yes. Getting this backwards posts the voucher the wrong
    way round while still importing cleanly."""
    debit = _entry_for(PAYMENT_TXN, "Timber Vendor A")
    assert debit.findtext("ISDEEMEDPOSITIVE") == "Yes"
    assert debit.findtext("AMOUNT") == "-5000.00"


def test_source_ledger_is_credited_with_a_positive_amount():
    credit = _entry_for(PAYMENT_TXN, "Cash-in-Hand")
    assert credit.findtext("ISDEEMEDPOSITIVE") == "No"
    assert credit.findtext("AMOUNT") == "5000.00"


def test_the_two_sides_sum_to_zero():
    for txn in (PAYMENT_TXN, RECEIPT_TXN, CONTRA_TXN):
        total = sum(float(e.findtext("AMOUNT")) for e in _entries(txn))
        assert total == 0.0, f"{txn['id']} does not balance"


def test_receipt_debits_the_bank_and_credits_the_customer():
    assert _entry_for(RECEIPT_TXN, "HDFC Bank").findtext("ISDEEMEDPOSITIVE") == "Yes"
    assert _entry_for(RECEIPT_TXN, "Customer Sharath").findtext("ISDEEMEDPOSITIVE") == "No"


def test_ledger_names_with_xml_characters_do_not_break_the_envelope():
    """A real ledger is called things like "Sharma & Sons" — building the
    envelope by string concatenation would emit malformed XML here."""
    txn = {**PAYMENT_TXN, "to_ledger": "Sharma & Sons <Timber>"}
    assert _entry_for(txn, "Sharma & Sons <Timber>") is not None   # parses at all


# ------------------------------------------------------- response parsing
def test_created_response_is_accepted():
    ok, _ = tally.parse_sync_response(
        "<RESPONSE><CREATED>1</CREATED><ALTERED>0</ALTERED></RESPONSE>")
    assert ok is True


def test_altered_response_is_accepted():
    ok, msg = tally.parse_sync_response(
        "<RESPONSE><CREATED>0</CREATED><ALTERED>1</ALTERED></RESPONSE>")
    assert ok is True and msg == "Altered"


def test_zero_created_is_not_success():
    ok, _ = tally.parse_sync_response("<RESPONSE><CREATED>0</CREATED><ALTERED>0</ALTERED></RESPONSE>")
    assert ok is False


def test_line_error_is_surfaced():
    ok, msg = tally.parse_sync_response(
        "<RESPONSE><LINEERROR>Ledger 'Timber Vendor A' does not exist</LINEERROR></RESPONSE>")
    assert ok is False
    assert "does not exist" in msg


def test_unparseable_response_is_not_success():
    ok, msg = tally.parse_sync_response("<html>gateway error")
    assert ok is False and "Unparseable" in msg


def test_empty_response_is_not_success():
    assert tally.parse_sync_response("")[0] is False


# --------------------------------------------------------- the review gate
async def _txn(user=ADMIN, **fields):
    payload = {"date": "2026-03-12", "type": "OUT", "payment_mode": "CASH", "amount": 5000.0,
               "from_ledger": "Cash-in-Hand", "to_ledger": "Timber Vendor A",
               "reference_no": "VCH-001", "narration": ""}
    payload.update(fields)
    return await server.create_cashbook_transaction(CashbookTxnCreate(**payload), user=user)


def _mock_tally(monkeypatch, accepted=True, message="Created"):
    calls = []

    def fake(xml):
        calls.append(xml)
        return accepted, message
    monkeypatch.setattr(server, "_post_to_tally", fake)
    return calls


def test_upi_transaction_defaults_to_needing_review():
    async def run():
        txn = await _txn(payment_mode="UPI")
        assert txn["needs_review"] is True
    asyncio.run(run())


def test_cash_and_bank_transactions_do_not_need_review():
    async def run():
        assert (await _txn(payment_mode="CASH"))["needs_review"] is False
        assert (await _txn(payment_mode="BANK_TRANSFER"))["needs_review"] is False
    asyncio.run(run())


def test_a_client_cannot_declare_a_upi_row_pre_reviewed():
    """needs_review is derived server-side, never taken on trust."""
    async def run():
        txn = await _txn(payment_mode="UPI", needs_review=False)
        assert txn["needs_review"] is True
    asyncio.run(run())


def test_unreviewed_upi_transaction_is_blocked_from_sync(monkeypatch):
    """The central gate: an auto-captured UPI row cannot reach the accounts
    until a human has confirmed its ledgers."""
    calls = _mock_tally(monkeypatch)

    async def run():
        txn = await _txn(payment_mode="UPI")
        with pytest.raises(HTTPException) as e:
            await server.tally_sync_one(txn["id"], user=ADMIN)
        assert e.value.status_code == 400
        assert "needs review" in e.value.detail.lower()
        assert calls == [], "nothing should have been sent to Tally"
        stored = await server.db.cashbook_transactions.find_one({"id": txn["id"]}, {"_id": 0})
        assert stored["tally_synced"] is False
    asyncio.run(run())


def test_the_same_upi_row_syncs_once_reviewed(monkeypatch):
    calls = _mock_tally(monkeypatch)

    async def run():
        txn = await _txn(payment_mode="UPI")
        await server.review_cashbook_transaction(txn["id"], user=ADMIN)
        out = await server.tally_sync_one(txn["id"], user=ADMIN)
        assert out["synced"] is True
        assert len(calls) == 1
        stored = await server.db.cashbook_transactions.find_one({"id": txn["id"]}, {"_id": 0})
        assert stored["tally_synced"] is True
        assert stored["tally_sync_time"]
        assert stored["reviewed_by"] == "Admin"
    asyncio.run(run())


def test_batch_sync_skips_unreviewed_upi_rows(monkeypatch):
    """The batch route must not be a way to sidestep review one row at a
    time — the gate lives below both endpoints, not in either of them."""
    calls = _mock_tally(monkeypatch)

    async def run():
        await _txn(payment_mode="UPI")                      # unreviewed
        await _txn(payment_mode="CASH", reference_no="C-1")  # ready
        out = await server.tally_sync_batch(user=ADMIN)
        assert out["attempted"] == 1 and out["synced"] == 1
        assert len(calls) == 1
    asyncio.run(run())


def test_sync_failure_is_recorded_and_does_not_mark_synced(monkeypatch):
    _mock_tally(monkeypatch, accepted=False, message="Tally gateway unreachable")

    async def run():
        txn = await _txn()
        with pytest.raises(HTTPException) as e:
            await server.tally_sync_one(txn["id"], user=ADMIN)
        assert e.value.status_code == 400
        stored = await server.db.cashbook_transactions.find_one({"id": txn["id"]}, {"_id": 0})
        assert stored["tally_synced"] is False
        assert "unreachable" in stored["tally_error"]
    asyncio.run(run())


def test_an_unreachable_gateway_fails_gracefully(monkeypatch):
    """No Tally server exists in this environment; the transport must report
    that rather than raise a 500."""
    import urllib.request

    def explode(*a, **kw):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", explode)
    ok, msg = server._post_to_tally("<ENVELOPE/>")
    assert ok is False
    assert "unreachable" in msg.lower()


def test_the_tally_destination_comes_only_from_config(monkeypatch):
    """SSRF guard: no route accepts a host, so whatever a caller sends, the
    POST goes to the configured TALLY_URL and nowhere else."""
    import urllib.request
    seen = {}

    def capture(req, *a, **kw):
        seen["url"] = req.full_url
        raise OSError("stop here")
    monkeypatch.setattr(urllib.request, "urlopen", capture)
    server._post_to_tally("<ENVELOPE/>")
    assert seen["url"] == server.TALLY_URL


def test_no_sync_route_accepts_a_host_parameter():
    """Structural guard on the same boundary — if someone later adds a
    host/url/endpoint argument to a sync route, this fails."""
    import inspect
    for fn in (server.tally_sync_one, server.tally_sync_batch, server.tally_preview):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"host", "url", "endpoint", "tally_url", "target"})


def test_already_synced_row_is_not_sent_twice(monkeypatch):
    calls = _mock_tally(monkeypatch)

    async def run():
        txn = await _txn()
        await server.tally_sync_one(txn["id"], user=ADMIN)
        out = await server.tally_sync_batch(user=ADMIN)
        assert out["attempted"] == 0
        assert len(calls) == 1
    asyncio.run(run())


# ------------------------------------------------------- listing and gating
def test_list_filters_by_review_mode_and_sync_state():
    async def run():
        await _txn(payment_mode="UPI")
        await _txn(payment_mode="CASH", reference_no="C-1")
        assert len(await server.list_cashbook_transactions(needs_review=True, user=ADMIN)) == 1
        assert len(await server.list_cashbook_transactions(payment_mode="CASH", user=ADMIN)) == 1
        assert len(await server.list_cashbook_transactions(tally_synced=False, user=ADMIN)) == 2
    asyncio.run(run())


def test_transactions_do_not_cross_a_tenant_boundary():
    async def run():
        await _txn()
        other = {"id": "u9", "tenant_id": "globex", "name": "GX", "role": "admin", "username": "gx"}
        assert await server.list_cashbook_transactions(user=other) == []
    asyncio.run(run())


def test_sync_requires_approve_permission(monkeypatch):
    """A Salesperson role has no approve on cashbook, so it cannot push
    vouchers into the accounts."""
    _mock_tally(monkeypatch)

    async def run():
        txn = await _txn()
        roles = [{"id": "r1", "name": "Salesperson", "permissions": [
            {"module": "cashbook", "view": True, "create": True, "edit": False,
             "delete": False, "approve": False, "export": False, "scope": "all"}]}]
        for r in roles:
            tenancy.stamp(r, "roles", STAFF)
            await server.db.roles.insert_one(dict(r))
        restricted = {**STAFF, "role_id": "r1"}
        with pytest.raises(HTTPException) as e:
            await server.tally_sync_one(txn["id"], user=restricted)
        assert e.value.status_code == 403
    asyncio.run(run())


def test_preview_returns_the_exact_envelope_that_would_be_sent():
    async def run():
        txn = await _txn()
        out = await server.tally_preview(txn["id"], user=ADMIN)
        assert out["voucher_type"] == "Payment"
        assert ET.fromstring(out["xml"]).tag == "ENVELOPE"
    asyncio.run(run())


def test_missing_transaction_is_a_404():
    async def run():
        with pytest.raises(HTTPException) as e:
            await server.tally_sync_one("nope", user=ADMIN)
        assert e.value.status_code == 404
    asyncio.run(run())
