"""Tests for WhatsApp click-to-chat logging: the templates endpoint and the
manual-click audit log. Same approach as test_documents.py — call the real
server.py route functions directly with server.db monkeypatched.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["wa_click_test"])
    yield


def test_templates_endpoint_returns_all_click_to_chat_contexts():
    async def run():
        out = await server.whatsapp_templates(user=ADMIN)
        assert set(out.keys()) == {"quote-shared", "payment-reminder", "installation-scheduled", "follow-up"}
        assert "{customer_name}" in out["quote-shared"]
    asyncio.run(run())


def test_click_logs_manual_send_with_distinct_status():
    async def run():
        result = await server.log_whatsapp_click(
            {"context": "quote-shared", "to": "9999999999", "customer_name": "Asha",
             "ref_type": "quote", "ref_id": "Q-100"},
            user=ADMIN,
        )
        assert result == {"ok": True}
        logged = await server.db.notification_logs.find_one({"to": "9999999999"})
        assert logged["status"] == "Sent (manual)"
        assert logged["ref_id"] == "Q-100"
        assert "Asha" in logged["message"]
    asyncio.run(run())


def test_click_with_no_phone_is_a_noop():
    async def run():
        await server.log_whatsapp_click({"context": "follow-up", "to": ""}, user=ADMIN)
        assert await server.db.notification_logs.find_one({}) is None
    asyncio.run(run())
