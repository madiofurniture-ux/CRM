"""Generic durable background-task queue.

"Agent" names the shape borrowed from a reference CRM's task worker (lease/
attempt/dedupe semantics) — there is no LLM or AI capability anywhere in
this module. It is infrastructure for any future background job (reminders,
digest sends, ...), not an agent framework.

Mongo has no multi-row atomic claim (no `FOR UPDATE SKIP LOCKED` analog).
`claim_batch` instead loops single-document `find_one_and_update` calls:
each call is independently atomic — two concurrent callers can never claim
the same document — at the cost of N round trips instead of one, and a
looser global sort guarantee under contention. That tradeoff is fine at
this app's task volume (background CRM reminders, not a high-throughput
queue); revisit only if it becomes a measured problem.

ponytail: fixed-interval poll loop in server.py, no separate worker
process, no exponential backoff (attempt-count + lease TTL is enough at
this volume). Upgrade only when a real need shows up.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import ReturnDocument

import models as m
import tenancy


async def schedule_task(db, user: dict, *, kind: str, subject_type: str = "", subject_id: str = "",
                         reason: str = "", payload: Optional[dict] = None, due_at: str = "",
                         priority: int = 0) -> str:
    """Re-dates an existing open task for the same (kind, subject) instead
    of duplicating it — a functional dedupe (query-then-upsert), not a DB
    constraint, matching the reference queue's own dedupe behavior."""
    q = tenancy.scope({"kind": kind, "subject_type": subject_type, "subject_id": subject_id,
                        "finished_at": ""}, "agent_tasks", user)
    existing = await db.agent_tasks.find_one(q)
    if existing:
        await db.agent_tasks.update_one({"id": existing["id"]},
                                         {"$set": {"due_at": due_at, "priority": priority, "reason": reason}})
        return existing["id"]
    doc = {
        "id": m.new_id(), "created_at": m.now_iso(), "kind": kind, "subject_type": subject_type,
        "subject_id": subject_id, "reason": reason, "payload": payload or {}, "due_at": due_at,
        "priority": priority, "attempts": 0, "max_attempts": 3, "leased_until": "", "leased_by": "",
        "started_at": "", "finished_at": "", "outcome": "", "log": [],
    }
    tenancy.stamp(doc, "agent_tasks", user)
    await db.agent_tasks.insert_one(dict(doc))
    return doc["id"]


def _eligible_filter(now: str) -> dict:
    return {
        "finished_at": "",
        "due_at": {"$lte": now},
        "attempts": {"$lt": 3},
        "$or": [{"leased_until": ""}, {"leased_until": {"$lt": now}}],
    }


async def _claim_by_id(db, task_id: str, now: str, worker_id: str, lease_until: str) -> Optional[dict]:
    """Claims a single task by its exact id — the eligibility filter is
    re-checked here too, so a task that lost the race between the
    candidate read and this write (already claimed by another caller) is
    correctly skipped rather than double-claimed. This is a single-document
    `find_one_and_update` with no `sort`/`projection`, both of which are the
    part that isn't reliable enough to depend on for the multi-candidate
    variant — claiming by a known id needs neither."""
    doc = await db.agent_tasks.find_one_and_update(
        {"id": task_id, **_eligible_filter(now)},
        {"$set": {"leased_until": lease_until, "leased_by": worker_id, "started_at": now},
         "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if doc:
        doc.pop("_id", None)
    return doc


async def claim_batch(db, n: int, worker_id: str, lease_seconds: int = 60) -> list[dict]:
    """Reads eligible candidates (read-only, no update — cheap to sort
    client-side), sorts by (priority desc, due_at asc), then claims each in
    order by exact id via an atomic single-document find_one_and_update.
    Each claim is independently atomic — two concurrent callers can never
    end up with the same document — at the cost of N round trips instead of
    one, and a looser global sort guarantee under real contention (another
    caller may claim a higher-priority candidate between this read and this
    caller's write). That tradeoff is fine at this app's task volume
    (background CRM reminders, not a high-throughput queue); revisit only
    if it becomes a measured problem."""
    now = m.now_iso()
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
    candidates = await db.agent_tasks.find(
        _eligible_filter(now), {"_id": 0, "id": 1, "priority": 1, "due_at": 1}
    ).to_list(max(n * 4, 50))
    candidates.sort(key=lambda c: (-c.get("priority", 0), c.get("due_at", "")))

    claimed = []
    for c in candidates:
        if len(claimed) >= n:
            break
        doc = await _claim_by_id(db, c["id"], now, worker_id, lease_until)
        if doc:
            claimed.append(doc)
    return claimed


async def complete_task(db, task_id: str, outcome: str) -> None:
    """Idempotent: a task already closed (e.g. by reconciliation) is a
    silent no-op — a guarded update, not a blind set."""
    await db.agent_tasks.update_one({"id": task_id, "finished_at": ""},
                                     {"$set": {"finished_at": m.now_iso(), "outcome": outcome[:500]}})


async def reconcile(db) -> dict:
    """Pure risk-reduction pass, run at the top of every dispatch tick
    before claim_batch — same ordering as the reference queue's stale-row
    sweep. Releases leases that died without the handler ever completing
    (crash, timeout) so the task becomes reclaimable again, and retires
    tasks that exhausted their attempts so they stop being polled forever.
    Both are broad update_many calls — safe because they only ever relax a
    stuck state, never race against a live claim (a task mid-lease has
    leased_until in the future and is untouched by either branch)."""
    now = m.now_iso()
    released = await db.agent_tasks.update_many(
        {"finished_at": "", "leased_until": {"$ne": "", "$lt": now}, "attempts": {"$lt": 3}},
        {"$set": {"leased_until": ""}},
    )
    retired = await db.agent_tasks.update_many(
        {"finished_at": "", "attempts": {"$gte": 3}},
        {"$set": {"finished_at": now, "outcome": "abandoned"}},
    )
    return {"released": released.modified_count, "retired": retired.modified_count}
