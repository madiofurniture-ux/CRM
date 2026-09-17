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
from models import DiscussionCreate, DirectMessageCreate  # noqa: E402

ADMIN = {"id": "u1", "tenant_id": "acme", "name": "Admin", "role": "admin"}
LEGACY_USER = {"id": "u2", "tenant_id": "acme", "name": "Field Staff", "role": "user", "role_id": ""}
OTHER_TENANT_ADMIN = {"id": "u3", "tenant_id": "globex", "name": "Globex Admin", "role": "admin"}
THIRD_USER = {"id": "u4", "tenant_id": "acme", "name": "Snoop", "role": "user", "role_id": ""}


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


# --------------------------------------------------- direct messages (DMs)

def test_dm_channel_is_never_in_the_public_channel_list():
    async def run():
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="hi"), user=ADMIN)
        channels = await server.list_discussion_channels(user=ADMIN)
        assert all(not c.startswith("dm:") for c in channels)
    asyncio.run(run())


def test_dm_is_visible_to_both_participants():
    async def run():
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="hi there"), user=ADMIN)
        as_sender = await server.list_direct_messages(LEGACY_USER["id"], user=ADMIN)
        as_recipient = await server.list_direct_messages(ADMIN["id"], user=LEGACY_USER)
        assert [m["text"] for m in as_sender] == ["hi there"]
        assert [m["text"] for m in as_recipient] == ["hi there"]
    asyncio.run(run())


def test_dm_is_invisible_to_a_non_participant_even_with_discussions_permission():
    async def run():
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="private"), user=ADMIN)
        # THIRD_USER has the same tenant + the same general discussions:view
        # grant as everyone else here — the DM must stay hidden regardless.
        snooped = await server.list_direct_messages(LEGACY_USER["id"], user=THIRD_USER)
        assert snooped == []
    asyncio.run(run())


def test_public_discussion_endpoints_reject_a_forged_dm_channel_name():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await server.create_discussion(DiscussionCreate(channel="dm:u1:u2", text="sneaky"), user=ADMIN)
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc2:
            await server.list_discussions(channel="dm:u1:u2", user=ADMIN)
        assert exc2.value.status_code == 400
    asyncio.run(run())


def test_dm_does_not_cross_a_tenant_boundary():
    async def run():
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="hi"), user=ADMIN)
        cross_tenant = await server.list_direct_messages(LEGACY_USER["id"], user=OTHER_TENANT_ADMIN)
        assert cross_tenant == []
    asyncio.run(run())


def test_a_dm_message_cannot_be_replied_to_via_the_public_reply_endpoint():
    async def run():
        dm = await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="private"), user=ADMIN)
        with pytest.raises(HTTPException) as exc:
            await server.reply_to_discussion(dm["id"], DiscussionCreate(channel="ignored", text="gotcha"), user=THIRD_USER)
        assert exc.value.status_code == 400
    asyncio.run(run())


def test_my_conversations_lists_the_other_party_and_last_message():
    async def run():
        for u in (ADMIN, LEGACY_USER):
            await server.db.users.insert_one({"id": u["id"], "tenant_id": u["tenant_id"], "name": u["name"]})
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="first"), user=ADMIN)
        await server.send_direct_message(LEGACY_USER["id"], DirectMessageCreate(text="second"), user=ADMIN)
        convos = await server.list_my_dm_conversations(user=ADMIN)
        assert len(convos) == 1
        assert convos[0]["other_user_id"] == LEGACY_USER["id"]
        assert convos[0]["other_user_name"] == "Field Staff"
        assert convos[0]["last_text"] == "second"

        their_side = await server.list_my_dm_conversations(user=LEGACY_USER)
        assert their_side[0]["other_user_id"] == ADMIN["id"]
    asyncio.run(run())
