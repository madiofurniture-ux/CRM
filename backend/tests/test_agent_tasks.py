"""Unit tests for the agent_tasks queue (dedupe + no-double-claim under
concurrency), against mongomock_motor — the same in-memory Mongo substitute
tests/run_local_server.py uses for the live e2e suite. No pytest-asyncio
dependency: plain asyncio.run() around each test body is enough here.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mongomock_motor import AsyncMongoMockClient

import agent_tasks

USER = {"id": "U1", "name": "Admin", "role": "admin", "tenant_id": "t1"}


def _db():
    return AsyncMongoMockClient()["agent_tasks_test"]


def test_schedule_task_dedupes_same_kind_and_subject():
    async def run():
        db = _db()
        id1 = await agent_tasks.schedule_task(db, USER, kind="followup_reminder",
                                               subject_type="lead", subject_id="L1", due_at="2026-01-01")
        id2 = await agent_tasks.schedule_task(db, USER, kind="followup_reminder",
                                               subject_type="lead", subject_id="L1", due_at="2026-01-02")
        assert id1 == id2
        count = await db.agent_tasks.count_documents({})
        assert count == 1
        doc = await db.agent_tasks.find_one({"id": id1})
        assert doc["due_at"] == "2026-01-02"  # re-dated, not duplicated
    asyncio.run(run())


def test_schedule_task_does_not_dedupe_different_subjects():
    async def run():
        db = _db()
        id1 = await agent_tasks.schedule_task(db, USER, kind="followup_reminder", subject_type="lead", subject_id="L1")
        id2 = await agent_tasks.schedule_task(db, USER, kind="followup_reminder", subject_type="lead", subject_id="L2")
        assert id1 != id2
        assert await db.agent_tasks.count_documents({}) == 2
    asyncio.run(run())


def test_claim_batch_never_returns_the_same_task_twice_under_concurrency():
    async def run():
        db = _db()
        for i in range(20):
            await agent_tasks.schedule_task(db, USER, kind="followup_reminder",
                                             subject_type="lead", subject_id=f"L{i}", due_at="2000-01-01")
        # Ten concurrent claimers, each trying to grab up to 5 — with 20
        # tasks total, every claimed id across all callers must be unique.
        results = await asyncio.gather(*[agent_tasks.claim_batch(db, n=5, worker_id=f"w{i}") for i in range(10)])
        claimed_ids = [t["id"] for batch in results for t in batch]
        assert len(claimed_ids) == len(set(claimed_ids)), "a task was claimed more than once"
        assert len(claimed_ids) == 20  # every task got claimed exactly once
    asyncio.run(run())


def test_claim_batch_respects_due_at_and_max_attempts():
    async def run():
        db = _db()
        await agent_tasks.schedule_task(db, USER, kind="x", subject_id="future", due_at="2999-01-01")
        due_id = await agent_tasks.schedule_task(db, USER, kind="x", subject_id="due", due_at="2000-01-01")
        claimed = await agent_tasks.claim_batch(db, n=10, worker_id="w1")
        assert [t["id"] for t in claimed] == [due_id]

        # Exhaust attempts: force attempts to max and confirm it's no longer claimable.
        await db.agent_tasks.update_one({"id": due_id}, {"$set": {"attempts": 3, "leased_until": ""}})
        claimed_again = await agent_tasks.claim_batch(db, n=10, worker_id="w1")
        assert claimed_again == []
    asyncio.run(run())


def test_complete_task_is_idempotent():
    async def run():
        db = _db()
        task_id = await agent_tasks.schedule_task(db, USER, kind="x", subject_id="s1", due_at="2000-01-01")
        await agent_tasks.complete_task(db, task_id, "done")
        doc = await db.agent_tasks.find_one({"id": task_id})
        assert doc["outcome"] == "done"
        first_finished_at = doc["finished_at"]
        # Second completion must not overwrite an already-closed task.
        await agent_tasks.complete_task(db, task_id, "done-again")
        doc2 = await db.agent_tasks.find_one({"id": task_id})
        assert doc2["outcome"] == "done"
        assert doc2["finished_at"] == first_finished_at
    asyncio.run(run())
