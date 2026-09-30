"""Durable Agent Bridge — the contract, not the transport.

A reference CRM bridges two independently-deployed processes (main app,
agent worker) with an HS256 shared-secret handshake. MADIO has no second
process and no LLM integration to bridge to yet, so building that
handshake now would secure a hop that doesn't exist. Instead, this module
builds the *durability contract* a real bridge would eventually need —
a conversation record, an append-only event log, a durable
human-in-the-loop question/answer slot, and a two-phase-shaped close —
as plain Mongo operations behind plain Python functions.

If a real separate agent process is ever added, only the *transport*
changes (these function bodies start making an HTTP call through a signed
token instead of writing straight to Mongo) — callers of this module and
the data model stay the same. Same "stub now, real transport later, call
sites unchanged" shape as notifications.py.

No separate `agent_events` collection: a conversation's own `log[]` is
already the durable event archive, same convention as Lead.log/Quote.log/
AgentTask.log. Split it out only if a single conversation's log ever
approaches Mongo's 16MB document cap — not a concern at this stage.
"""
from __future__ import annotations

from typing import Optional

import models as m
import tenancy


async def start_conversation(db, user: dict, *, subject_type: str, subject_id: str) -> dict:
    """Idempotent: reopens the existing open conversation for this subject
    instead of creating a second one, mirroring agent_tasks.schedule_task's
    dedupe-by-subject behavior."""
    q = tenancy.scope({"subject_type": subject_type, "subject_id": subject_id, "status": {"$ne": "closed"}},
                       "agent_conversations", user)
    existing = await db.agent_conversations.find_one(q, {"_id": 0})
    if existing:
        return existing
    doc = {
        "id": m.new_id(), "created_at": m.now_iso(), "subject_type": subject_type,
        "subject_id": subject_id, "status": "open", "pending_question": None,
        "resume_cursor": "", "log": [],
    }
    tenancy.stamp(doc, "agent_conversations", user)
    await db.agent_conversations.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def append_event(db, conversation_id: str, *, by: str, by_id: str = "", text: str, kind: str = "message") -> None:
    entry = {"at": m.now_iso(), "by": by, "by_id": by_id, "text": text, "kind": kind}
    await db.agent_conversations.update_one({"id": conversation_id}, {"$push": {"log": entry}})


async def ask_question(db, conversation_id: str, *, text: str, options: Optional[list] = None) -> dict:
    """Durable HITL: the question is a first-class field on the
    conversation, not just a log entry, so a UI can render "waiting on you"
    state without re-parsing the log."""
    question = {"id": m.new_id(), "text": text, "options": options or [], "asked_at": m.now_iso()}
    await db.agent_conversations.update_one(
        {"id": conversation_id},
        {"$set": {"status": "awaiting_input", "pending_question": question},
         "$push": {"log": {"at": question["asked_at"], "by": "system", "by_id": "", "text": text, "kind": "question"}}},
    )
    return question


async def answer_question(db, conversation_id: str, *, by: str, by_id: str = "", text: str) -> None:
    await db.agent_conversations.update_one(
        {"id": conversation_id},
        {"$set": {"status": "open", "pending_question": None},
         "$push": {"log": {"at": m.now_iso(), "by": by, "by_id": by_id, "text": text, "kind": "answer"}}},
    )


async def close_conversation(db, conversation_id: str) -> None:
    """Durable and sufficient on its own — nothing remote needs stopping
    yet. Keeping `status` (not a boolean `closed` flag) as the field means
    a later "poke a real remote executor after the DB flip" step is a pure
    addition, not a rework, the same two-phase shape the reference bridge
    uses for cancelling a run."""
    await db.agent_conversations.update_one({"id": conversation_id}, {"$set": {"status": "closed"}})
