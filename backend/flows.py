"""Flows: tenant-built automations, in the spirit of Salesforce Flow.

A flow belongs to one entity (lead, quote, project, ...) and has
  * a trigger — record created / any save / stage entered / field changed,
    or a scheduled one: N days before/after a date field, or a record sitting
    in its stage for N days;
  * conditions — field comparisons, all or any must hold;
  * steps — run in order: create a task, alert a teammate, set a field,
    assign the owner, message the customer, or wait N days before the rest.

Everything here is pure (no db, no FastAPI): validation, condition checks,
trigger matching and schedule maths. server.py owns persistence and runs
the steps, reusing workflow_rules for tasks, placeholders and messages.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Optional

import lifecycle as lc
import models as m
import notifications
import tenancy
import workflow_rules as wf

EVENT_TRIGGERS = ("created", "updated", "stage_enter", "field_changed")
SCHEDULED_TRIGGERS = ("date_relative", "stage_stale")
TRIGGERS = EVENT_TRIGGERS + SCHEDULED_TRIGGERS
STEP_TYPES = ("create_task", "alert_user", "set_field", "assign_owner", "notify_customer", "wait")
OPERATORS = ("equals", "not_equals", "contains", "gt", "gte", "lt", "lte", "is_empty", "is_not_empty")
NO_VALUE_OPS = ("is_empty", "is_not_empty")
MAX_FLOWS = 50
MAX_CONDITIONS = 10
MAX_STEPS = 10
MAX_WAIT_DAYS = 90
# A scheduled flow catches up on days the server was down, but not forever.
CATCH_UP_DAYS = 3

TRIGGER_LABELS = {
    "created": "A record is created",
    "updated": "A record is saved",
    "stage_enter": "A record enters a stage",
    "field_changed": "A field changes",
    "date_relative": "Days before/after a date",
    "stage_stale": "Stuck in a stage for N days",
}
STEP_LABELS = {
    "create_task": "Create a task",
    "alert_user": "Alert a teammate",
    "set_field": "Set a field",
    "assign_owner": "Assign the owner",
    "notify_customer": "Message the customer (WhatsApp)",
    "wait": "Wait N days",
}
OPERATOR_LABELS = {
    "equals": "is", "not_equals": "is not", "contains": "contains",
    "gt": ">", "gte": "≥", "lt": "<", "lte": "≤",
    "is_empty": "is empty", "is_not_empty": "is not empty",
}


SINGULAR = {
    "visitor": "Visitor", "lead": "Lead", "customer": "Customer", "quote": "Quotation",
    "sale": "Sales Order", "project": "Project", "vendor_order": "Vendor Order",
    "purchase_order": "Purchase Order", "invoice": "Invoice", "product": "Product", "task": "Task",
}


def _s(value: Any, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _int(value: Any, name: str, lo: int, hi: int) -> int:
    try:
        n = int(value if value not in (None, "") else 0)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number")
    if not lo <= n <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return n


def date_fields(entity: str) -> list[str]:
    """Text fields that hold a date and can anchor a scheduled flow."""
    return [f["key"] for f in wf.field_catalog(entity)
            if f["type"] == "text" and (f["key"].endswith("date") or f["key"].endswith("_until")
                                        or f["key"] in ("next_follow_up",))]


def entity_meta(entity: str, stages: list) -> dict:
    """Everything the builder needs to offer valid choices for one entity."""
    return {
        "entity": entity, "label": tenancy.ENTITY_LABELS.get(entity, entity),
        "singular": SINGULAR.get(entity, entity),
        "fields": wf.field_catalog(entity), "date_fields": date_fields(entity),
        "stages": [{"key": s["key"], "label": s["label"]} for s in stages],
        "owner_field": wf.OWNER_FIELD.get(entity, ""),
    }


def builder_meta() -> dict:
    return {
        "triggers": [{"key": k, "label": TRIGGER_LABELS[k], "scheduled": k in SCHEDULED_TRIGGERS} for k in TRIGGERS],
        "steps": [{"key": k, "label": STEP_LABELS[k]} for k in STEP_TYPES],
        "operators": [{"key": k, "label": OPERATOR_LABELS[k], "needs_value": k not in NO_VALUE_OPS}
                      for k in OPERATORS],
        "message_templates": sorted(notifications.EVENTS),
        "priorities": list(wf.TASK_PRIORITIES),
        "limits": {"flows": MAX_FLOWS, "conditions": MAX_CONDITIONS, "steps": MAX_STEPS,
                   "wait_days": MAX_WAIT_DAYS},
    }


# ── validation ─────────────────────────────────────────────────────────────
def validate_flow(raw: Any, stages: list) -> dict:
    """Normalise a flow definition from the builder. Raises ValueError with a
    message fit to show the person building it."""
    if not isinstance(raw, dict):
        raise ValueError("A flow must be an object")
    entity = str(raw.get("entity") or "")
    if entity not in tenancy.ENTITY_COLLECTION:
        raise ValueError("Pick what the flow runs on (lead, quotation, project, ...)")
    name = _s(raw.get("name"), 120)
    if not name:
        raise ValueError("Give the flow a name")
    catalog = {f["key"]: f for f in wf.field_catalog(entity)}
    stage_keys = {s["key"] for s in stages}

    t = raw.get("trigger") or {}
    if not isinstance(t, dict):
        raise ValueError("trigger must be an object")
    ttype = str(t.get("type") or "")
    if ttype not in TRIGGERS:
        raise ValueError(f"Pick a trigger: {', '.join(TRIGGER_LABELS[k] for k in TRIGGERS)}")
    trigger: dict = {"type": ttype}
    if ttype in ("stage_enter", "stage_stale"):
        stage = tenancy.stage_key(t.get("stage") or "")
        if stage not in stage_keys:
            raise ValueError("Pick the stage this flow watches")
        trigger["stage"] = stage
    if ttype == "stage_stale":
        trigger["days"] = _int(t.get("days"), "Days in stage", 1, 365)
    if ttype == "field_changed":
        field = str(t.get("field") or "")
        if field not in catalog:
            raise ValueError("Pick the field this flow watches")
        trigger["field"] = field
    if ttype == "date_relative":
        field = str(t.get("field") or "")
        if field not in date_fields(entity):
            raise ValueError("Pick the date field this flow counts from")
        trigger["field"] = field
        trigger["offset_days"] = _int(t.get("offset_days"), "Days before/after", -365, 365)

    conds_raw = raw.get("conditions") or []
    if not isinstance(conds_raw, list):
        raise ValueError("conditions must be a list")
    if len(conds_raw) > MAX_CONDITIONS:
        raise ValueError(f"At most {MAX_CONDITIONS} conditions")
    conditions = []
    for c in conds_raw:
        if not isinstance(c, dict):
            raise ValueError("Each condition must be an object")
        field = str(c.get("field") or "")
        if field not in catalog and field != "stage":
            raise ValueError(f"Unknown field '{field}' in a condition")
        op = str(c.get("op") or "equals")
        if op not in OPERATORS:
            raise ValueError(f"Unknown comparison '{op}'")
        conditions.append({"field": field, "op": op,
                           "value": "" if op in NO_VALUE_OPS else _s(c.get("value"), 200)})
    match = "any" if raw.get("match") == "any" else "all"

    steps_raw = raw.get("steps") or []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("Add at least one step")
    if len(steps_raw) > MAX_STEPS:
        raise ValueError(f"At most {MAX_STEPS} steps")
    steps = [_validate_step(s, i, entity, catalog) for i, s in enumerate(steps_raw, 1)]
    if steps[-1]["type"] == "wait":
        raise ValueError("A flow can't end with a wait; add the step to run after it")

    return {
        "id": _s(raw.get("id"), 64) or m.new_id(),
        "name": name, "description": _s(raw.get("description"), 500),
        "entity": entity, "active": raw.get("active", True) is not False,
        "trigger": trigger, "conditions": conditions, "match": match, "steps": steps,
    }


def _validate_step(raw: Any, i: int, entity: str, catalog: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"Step {i} must be an object")
    kind = raw.get("type")
    label = f"Step {i}"
    if kind in ("create_task", "set_field", "notify_customer"):
        # Same shape and checks as a workflow automation action.
        return wf._validate_action(raw, label, catalog, entity)
    if kind == "alert_user":
        user = _s(raw.get("user"), 120)
        message = _s(raw.get("message"), 300)
        if not user:
            raise ValueError(f"{label}: pick who to alert")
        if not message:
            raise ValueError(f"{label}: write the alert")
        return {"type": kind, "user": user, "message": message}
    if kind == "assign_owner":
        if not wf.OWNER_FIELD.get(entity):
            raise ValueError(f"{label}: this record type has no owner field")
        user = _s(raw.get("user"), 120)
        if not user:
            raise ValueError(f"{label}: pick who becomes the owner")
        return {"type": kind, "user": user}
    if kind == "wait":
        return {"type": kind, "days": _int(raw.get("days"), f"{label}: wait days", 1, MAX_WAIT_DAYS)}
    raise ValueError(f"{label}: step type must be one of {', '.join(STEP_LABELS.values())}")


# ── conditions ─────────────────────────────────────────────────────────────
def _num(value: Any) -> Optional[float]:
    try:
        n = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if n != n else n


def _compare(actual: Any, op: str, expected: str) -> bool:
    if op == "is_empty":
        return wf.is_blank(actual)
    if op == "is_not_empty":
        return not wf.is_blank(actual)
    if isinstance(actual, bool):
        want = str(expected).strip().lower() in ("true", "yes", "1")
        return (actual == want) if op == "equals" else (actual != want) if op == "not_equals" else False
    a_txt, e_txt = str(actual if actual is not None else "").strip().lower(), str(expected).strip().lower()
    if op == "contains":
        return e_txt in a_txt
    if op in ("equals", "not_equals"):
        a_n, e_n = _num(actual), _num(expected)
        same = (a_n == e_n) if a_n is not None and e_n is not None else a_txt == e_txt
        return same if op == "equals" else not same
    # Ordering: numbers first, then ISO dates, then plain text.
    a_n, e_n = _num(actual), _num(expected)
    if a_n is None or e_n is None:
        a_d, e_d = lc.parse_date(actual), lc.parse_date(expected)
        if a_d and e_d:
            a_n, e_n = a_d.toordinal(), e_d.toordinal()
        else:
            if not a_txt:
                return False
            a_n, e_n = a_txt, e_txt  # type: ignore[assignment]
    return {"gt": a_n > e_n, "gte": a_n >= e_n, "lt": a_n < e_n, "lte": a_n <= e_n}[op]


def conditions_met(flow: dict, record: dict, stage_field: str = "stage") -> bool:
    conds = flow.get("conditions") or []
    if not conds:
        return True
    results = []
    for c in conds:
        field = stage_field if c["field"] == "stage" else c["field"]
        results.append(_compare(record.get(field), c["op"], c.get("value", "")))
    return any(results) if flow.get("match") == "any" else all(results)


# ── event triggers ─────────────────────────────────────────────────────────
def event_matches(flow: dict, *, created: bool, before: dict, record: dict,
                  entered_key: Optional[str]) -> bool:
    """Does this save fire the flow? `entered_key` is the stage key the record
    just moved into (None when the stage didn't change)."""
    if not flow.get("active", True):
        return False
    t = flow.get("trigger") or {}
    kind = t.get("type")
    if kind == "created":
        return created
    if kind == "updated":
        return not created
    if kind == "stage_enter":
        return bool(entered_key) and entered_key == t.get("stage")
    if kind == "field_changed":
        if created:
            return False
        f = t.get("field")
        before = before or {}
        if before.get("__partial__") and f not in before:
            return False              # old value unknown (e.g. a Convert button): don't guess
        return f in record and _norm(record.get(f)) != _norm(before.get(f))
    return False


def _norm(value: Any) -> str:
    n = _num(value)
    return repr(n) if n is not None else str(value if value is not None else "").strip()


# ── scheduled triggers ─────────────────────────────────────────────────────
def scheduled_fire_key(flow: dict, record: dict, today: date, stage_field: str = "stage") -> Optional[str]:
    """When a scheduled flow is due for this record, a key naming that one
    occasion (so it fires once, however often the scheduler looks); else None."""
    if not flow.get("active", True):
        return None
    t = flow.get("trigger") or {}
    kind = t.get("type")
    if kind == "date_relative":
        anchor = lc.parse_date(record.get(t.get("field")))
        if not anchor:
            return None
        target = anchor + timedelta(days=int(t.get("offset_days") or 0))
        if target <= today <= target + timedelta(days=CATCH_UP_DAYS):
            return f"{t.get('field')}:{target.isoformat()}"
        return None
    if kind == "stage_stale":
        if tenancy.stage_key(record.get(stage_field) or "") != t.get("stage"):
            return None
        entered = lc.parse_date(record.get("stage_entered_at"))
        if not entered:
            return None
        if (today - entered).days >= int(t.get("days") or 0):
            return f"stale:{t.get('stage')}:{record.get('stage_entered_at')}"
        return None
    return None


def split_at_wait(steps: list, start: int = 0) -> tuple[list, Optional[int], int]:
    """Steps to run now from `start`, then (index after the wait, days) if a
    wait cuts the run short, else (None, 0)."""
    now = []
    for i in range(start, len(steps)):
        if steps[i]["type"] == "wait":
            return now, i + 1, int(steps[i].get("days") or 0)
        now.append(steps[i])
    return now, None, 0


def flow_summary(flow: dict) -> str:
    """One line for lists: 'When a Quotation enters Won → 2 steps'."""
    t = flow.get("trigger") or {}
    kind = t.get("type")
    what = {
        "created": "is created", "updated": "is saved",
        "stage_enter": f"enters {t.get('stage', '')}",
        "field_changed": f"changes {t.get('field', '')}",
        "date_relative": (f"{abs(t.get('offset_days', 0))} days {'before' if t.get('offset_days', 0) < 0 else 'after'} "
                          f"{t.get('field', '')}" if t.get("offset_days") else f"on {t.get('field', '')}"),
        "stage_stale": f"sits in {t.get('stage', '')} for {t.get('days', 0)} days",
    }.get(kind, "")
    n = len(flow.get("steps") or [])
    noun = SINGULAR.get(flow.get("entity"), str(flow.get("entity") or "record"))
    article = "an" if noun[:1].lower() in "aeiou" else "a"
    return f"When {article} {noun} {what}: {n} step{'s' if n != 1 else ''}"
