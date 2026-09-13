"""Tests for Phase 4: real WhatsApp Cloud API send (credential-gated,
mocked HTTP) and the inbound webhook. Same approach as test_documents.py.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
import notifications as notif  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["wa_cloud_test"])
    yield


def test_send_whatsapp_stub_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_ID", raising=False)
    status, error = notif._send_whatsapp("919999999999", "hi")
    assert (status, error) == ("Sent", "")


def test_send_whatsapp_calls_graph_api_when_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return SimpleNamespace(status_code=200, text="")

    monkeypatch.setattr(notif.requests, "post", fake_post)
    status, error = notif._send_whatsapp("919999999999", "hi there")
    assert status == "Sent"
    assert "12345" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer fake-token"
    assert captured["json"]["to"] == "919999999999"


def test_send_whatsapp_reports_failure_on_error_status(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "fake-token")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "12345")
    monkeypatch.setattr(notif.requests, "post",
                         lambda *a, **k: SimpleNamespace(status_code=401, text="bad token"))
    status, error = notif._send_whatsapp("919999999999", "hi")
    assert status == "Failed"
    assert "bad token" in error


def test_webhook_verification_echoes_challenge_on_matching_token(monkeypatch):
    monkeypatch.setattr(server, "WHATSAPP_VERIFY_TOKEN", "secret123")

    async def run():
        req = SimpleNamespace(query_params={"hub.verify_token": "secret123", "hub.challenge": "42"})
        resp = await server.whatsapp_webhook_verify(req)
        assert resp.body == b"42"
    asyncio.run(run())


def test_webhook_stores_inbound_message(monkeypatch):
    monkeypatch.setattr(server, "WHATSAPP_WEBHOOK_TENANT_ID", "acme")

    async def run():
        payload = {"entry": [{"changes": [{"value": {"messages": [
            {"from": "919999999999", "id": "wamid.1", "text": {"body": "Hello"}}
        ]}}]}]}
        req = SimpleNamespace(json=lambda: _async_ret(payload))
        result = await server.whatsapp_webhook_receive(req)
        assert result == {"ok": True}
        stored = await server.db.whatsapp_messages.find_one({"phone": "919999999999"})
        assert stored["text"] == "Hello"
        assert stored["tenant_id"] == "acme"
    asyncio.run(run())


async def _async_ret(value):
    return value
