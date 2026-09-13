"""Tests for the Discussion forum (Team Board): channels, posting, replying,
tenant isolation, and permission gating. Same approach as test_documents.py.
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from models import DiscussionCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}


@pytest.fixture(autouse=True)
def _mongomock_db(monkeypatch):
    monkeypatch.setattr(server, "db", AsyncMongoMockClient()["discussions_test"])
    yield


def test_channels_defaults_to_general_when_none_exist():
    async def run():
        out = await server.list_discussion_channels(user=ADMIN)
        assert out == ["General"]
    asyncio.run(run())


def test_create_and_list_scoped_to_tenant():
    async def run():
        post = await server.create_discussion(DiscussionCreate(channel="General", text="hello team"), user=ADMIN)
        assert post["author_name"] == "Admin"
        assert post["parent_id"] == ""
        items = await server.list_discussions(channel="General", user=ADMIN)
        assert len(items) == 1
        other = await server.list_discussions(channel="General", user=OTHER_TENANT_ADMIN)
        assert other == []
    asyncio.run(run())


def test_reply_inherits_parent_channel():
    async def run():
        post = await server.create_discussion(DiscussionCreate(channel="General", text="hello"), user=ADMIN)
        reply = await server.reply_to_discussion(post["id"], DiscussionCreate(channel="ignored", text="hi back"), user=LEGACY_USER)
        assert reply["parent_id"] == post["id"]
        assert reply["channel"] == "General"
    asyncio.run(run())


def test_reply_to_missing_or_other_tenant_post_is_404():
    async def run():
        post = await server.create_discussion(DiscussionCreate(channel="General", text="hello"), user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await server.reply_to_discussion(post["id"], DiscussionCreate(channel="x", text="hi"), user=OTHER_TENANT_ADMIN)
        assert exc.value.status_code == 404
    asyncio.run(run())


def test_legacy_user_can_view_and_post_without_a_role():
    async def run():
        await server.create_discussion(DiscussionCreate(channel="General", text="hi"), user=LEGACY_USER)
        items = await server.list_discussions(channel="General", user=LEGACY_USER)
        assert len(items) == 1
    asyncio.run(run())
