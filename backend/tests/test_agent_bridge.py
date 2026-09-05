"""Unit tests for agent_bridge.py's conversation lifecycle functions,
against mongomock_motor — same pattern as test_agent_tasks.py.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mongomock_motor import AsyncMongoMockClient

import agent_bridge

USER = {"id": "U1", "name": "Admin", "role": "admin", "tenant_id": "t1"}


def _db():
    return AsyncMongoMockClient()["agent_bridge_test"]


def test_start_conversation_reopens_existing_open_one():
    async def run():
        db = _db()
        c1 = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        c2 = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        assert c1["id"] == c2["id"]
        assert await db.agent_conversations.count_documents({}) == 1
    asyncio.run(run())


def test_start_conversation_opens_a_new_one_after_close():
    async def run():
        db = _db()
        c1 = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        await agent_bridge.close_conversation(db, c1["id"])
        c2 = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        assert c2["id"] != c1["id"]
        assert await db.agent_conversations.count_documents({}) == 2
    asyncio.run(run())


def test_append_event_pushes_to_log():
    async def run():
        db = _db()
        c = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        await agent_bridge.append_event(db, c["id"], by="Rep", text="Called the customer")
        doc = await db.agent_conversations.find_one({"id": c["id"]})
        assert len(doc["log"]) == 1
        assert doc["log"][0]["text"] == "Called the customer"
        assert doc["log"][0]["kind"] == "message"
    asyncio.run(run())


def test_ask_and_answer_question_lifecycle():
    async def run():
        db = _db()
        c = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        q = await agent_bridge.ask_question(db, c["id"], text="Confirm budget?", options=["Yes", "No"])
        doc = await db.agent_conversations.find_one({"id": c["id"]})
        assert doc["status"] == "awaiting_input"
        assert doc["pending_question"]["id"] == q["id"]
        assert doc["pending_question"]["options"] == ["Yes", "No"]
        assert doc["log"][-1]["kind"] == "question"

        await agent_bridge.answer_question(db, c["id"], by="Rep", text="Yes")
        doc2 = await db.agent_conversations.find_one({"id": c["id"]})
        assert doc2["status"] == "open"
        assert doc2["pending_question"] is None
        assert doc2["log"][-1]["kind"] == "answer"
        assert doc2["log"][-1]["text"] == "Yes"
    asyncio.run(run())


def test_close_conversation_is_terminal_and_isolated_per_tenant():
    async def run():
        db = _db()
        c = await agent_bridge.start_conversation(db, USER, subject_type="lead", subject_id="L1")
        await agent_bridge.close_conversation(db, c["id"])
        doc = await db.agent_conversations.find_one({"id": c["id"]})
        assert doc["status"] == "closed"

        other_user = {"id": "U2", "name": "Other", "role": "admin", "tenant_id": "t2"}
        import tenancy
        other_visible = await db.agent_conversations.find(
            tenancy.scope({}, "agent_conversations", other_user)).to_list(10)
        assert other_visible == []
    asyncio.run(run())
