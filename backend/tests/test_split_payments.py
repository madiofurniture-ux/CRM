"""Tests for the Dual-Payment (Other/Direct Settlement vs. Bank Transfer + GST) engine and
PIN-protected privacy masking. New `finance_payments` collection/model —
deliberately separate from the existing Payment (sale/invoice collection
ledger, no GST or deal/project linkage). Same mongomock pattern as
tests/test_petty_cash.py.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import SplitPaymentCreate, BankTransferComponent, OtherComponent, PrivacyPinSet, PrivacyPinVerify  # noqa: E402
from tenancy import stamp  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["split_payments_test"])
    yield


async def _make_user(user_id="u1", tenant="acme", **overrides):
    doc = {"id": user_id, "tenant_id": tenant, "username": "admin", "name": "Admin", "role": "admin"}
    doc.update(overrides)
    await server.db.users.insert_one(dict(doc))
    return doc


async def _make_wallet(wallet_id="b1", user=ADMIN, **overrides):
    doc = {"book_name": "Site A Wallet", "initial_balance": 1000, "current_balance": 1000,
           "status": "ACTIVE", "assigned_users": [], "project_id": "", "imprest_limit": 0,
           "strict_overdraft": False, "id": wallet_id, "created_at": "2026-01-01T00:00:00+00:00"}
    doc.update(overrides)
    stamp(doc, "cashbooks", user)
    await server.db.cashbooks.insert_one(dict(doc))
    return doc


def test_split_payment_computes_gst_and_grand_total():
    async def run():
        payload = SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(taxable_amount=10000, gst_rate=18.0, utr_reference="UTR123"),
            other_component=OtherComponent(other_amount=5000),
        )
        doc = await server.create_split_payment(payload, user=ADMIN)
        # GST: 10000 * 18% = 1800; BT total = 11800; grand total = 11800 + 5000 = 16800
        assert doc["bank_transfer_component"]["gst_amount"] == 1800
        assert doc["bank_transfer_component"]["total_bt_amount"] == 11800
        assert doc["total_collected"] == 16800
        assert doc["status"] == "RECORDED"
    asyncio.run(run())


def test_split_payment_other_only_has_no_gst():
    async def run():
        payload = SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=2000),
        )
        doc = await server.create_split_payment(payload, user=ADMIN)
        assert doc["total_collected"] == 2000
        assert doc["bank_transfer_component"] is None
    asyncio.run(run())


def test_split_payment_credits_wallet_when_other_has_wallet_id():
    async def run():
        await _make_wallet()
        payload = SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=500, wallet_id="b1"),
        )
        await server.create_split_payment(payload, user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 1500  # 1000 + 500 credited
        entries = await server.db.cashbook_entries.find({"cashbook_id": "b1"}).to_list(10)
        assert len(entries) == 1
        assert entries[0]["type"] == "CASH_IN"
        assert entries[0]["amount"] == 500
    asyncio.run(run())


def test_split_payment_without_wallet_id_does_not_touch_cashbook():
    async def run():
        await _make_wallet()
        payload = SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=500),  # no wallet_id
        )
        await server.create_split_payment(payload, user=ADMIN)
        book = await server.db.cashbooks.find_one({"id": "b1"})
        assert book["current_balance"] == 1000  # untouched
    asyncio.run(run())


def test_list_payments_masks_other_by_default():
    async def run():
        payload = SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(taxable_amount=10000, gst_rate=18.0),
            other_component=OtherComponent(other_amount=5000, receipt_voucher_no="RV-1"),
        )
        await server.create_split_payment(payload, user=ADMIN)

        masked = await server.list_split_payments(mask_other=True, user=ADMIN)
        assert masked[0]["other_component"] is None
        assert masked[0]["bank_transfer_component"]["total_bt_amount"] == 11800  # official figures intact

        unmasked = await server.list_split_payments(mask_other=False, user=ADMIN)
        assert unmasked[0]["other_component"]["other_amount"] == 5000
    asyncio.run(run())


def test_masked_total_collected_cannot_be_subtracted_back_to_the_other_amount():
    """The mask has to survive arithmetic, not just hide a field.

    total_collected is bank-transfer + Other and the bank-transfer leg stays
    visible, so a masked row that kept the true grand total would hand the
    hidden figure to anyone who could subtract. Masked, the total must BE
    the bank-transfer figure, leaving a zero residual.
    """
    async def run():
        await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(taxable_amount=10000, gst_rate=18.0),
            other_component=OtherComponent(other_amount=5000),
        ), user=ADMIN)

        row = (await server.list_split_payments(mask_other=True, user=ADMIN))[0]
        visible_bt = row["bank_transfer_component"]["total_bt_amount"]
        assert visible_bt == 11800                      # official figure untouched
        assert row["total_collected"] == 11800          # restated to bank-transfer only
        assert row["total_collected"] - visible_bt == 0  # no residual to recover 5000 from
        assert "5000" not in str(row)
    asyncio.run(run())


def test_masked_other_only_payment_collapses_to_zero_not_the_hidden_amount():
    """No bank-transfer leg means there is no visible figure at all — the
    masked total must not fall back to the Other amount."""
    async def run():
        await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
            other_component=OtherComponent(other_amount=7777),
        ), user=ADMIN)

        row = (await server.list_split_payments(mask_other=True, user=ADMIN))[0]
        assert row["bank_transfer_component"] is None
        assert row["total_collected"] == 0
        assert "7777" not in str(row)
    asyncio.run(run())


def test_unmasked_total_collected_is_still_the_real_grand_total():
    """The fix is purely about what the mask reveals — an authorised viewer
    must still get the true total, Other included."""
    async def run():
        await server.create_split_payment(SplitPaymentCreate(
            project_id="p1", payment_mode="SPLIT", receipt_date="2026-01-01",
            bank_transfer_component=BankTransferComponent(taxable_amount=10000, gst_rate=18.0),
            other_component=OtherComponent(other_amount=5000),
        ), user=ADMIN)

        row = (await server.list_split_payments(mask_other=False, user=ADMIN))[0]
        assert row["other_component"]["other_amount"] == 5000
        assert row["total_collected"] == 16800  # 11800 + 5000, unchanged
        assert row["total_collected"] - row["bank_transfer_component"]["total_bt_amount"] == 5000
    asyncio.run(run())


def test_masking_a_legacy_cash_row_also_restates_its_total():
    """Pre-rename rows go through normalize_settlement first; the mask must
    still cover them rather than passing the stored total through."""
    async def run():
        await server.db.finance_payments.insert_one(stamp({
            "id": "legacy1", "created_at": "2025-06-01T00:00:00+00:00",
            "project_id": "p1", "payment_mode": "CASH", "receipt_date": "2025-06-01",
            "bank_transfer_component": {"taxable_amount": 1000, "gst_amount": 180,
                                        "total_bt_amount": 1180},
            "cash_component": {"cash_amount": 9000, "wallet_id": ""},
            "total_collected": 10180, "status": "RECORDED"}, "finance_payments", ADMIN))

        row = (await server.list_split_payments(mask_other=True, user=ADMIN))[0]
        assert row["other_component"] is None
        assert row["total_collected"] == 1180
        assert row["total_collected"] - row["bank_transfer_component"]["total_bt_amount"] == 0
        assert "9000" not in str(row)
    asyncio.run(run())


def test_tenant_isolation_on_split_payments():
    async def run():
        payload = SplitPaymentCreate(project_id="p1", payment_mode="OTHER", receipt_date="2026-01-01",
                                      other_component=OtherComponent(other_amount=100))
        await server.create_split_payment(payload, user=ADMIN)
        await server.create_split_payment(payload, user=OTHER_TENANT_ADMIN)

        acme_payments = await server.list_split_payments(mask_other=False, user=ADMIN)
        assert len(acme_payments) == 1
        assert acme_payments[0]["tenant_id"] == "acme"
    asyncio.run(run())


def test_set_and_verify_privacy_pin():
    async def run():
        await _make_user()
        await server.set_privacy_pin(PrivacyPinSet(pin="4321"), user=ADMIN)
        user_doc = await server.db.users.find_one({"id": "u1"})
        assert user_doc["finance_privacy_pin_hash"]
        assert user_doc["finance_privacy_pin_hash"] != "4321"  # actually hashed, not stored raw

        ok = await server.verify_privacy_pin(PrivacyPinVerify(pin="4321"), user=ADMIN)
        assert ok["verified"] is True

        with pytest.raises(HTTPException) as exc:
            await server.verify_privacy_pin(PrivacyPinVerify(pin="0000"), user=ADMIN)
        assert exc.value.status_code == 401
    asyncio.run(run())


def test_verify_privacy_pin_fails_when_none_set():
    async def run():
        await _make_user()  # no finance_privacy_pin_hash set — no insecure default
        with pytest.raises(HTTPException) as exc:
            await server.verify_privacy_pin(PrivacyPinVerify(pin="0000"), user=ADMIN)
        assert exc.value.status_code == 400
        assert "not set" in exc.value.detail.lower()
    asyncio.run(run())
