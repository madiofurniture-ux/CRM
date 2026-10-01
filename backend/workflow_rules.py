"""Per-entity workflow behaviour: stage gates and stage automations.

tenancy.py owns the stage SCHEMA (what a tenant's stages look like); this
module owns what happens when a record MOVES between them, in the same
spirit as Salesforce's Path + validation rules + record-triggered flows:

  * gates — a stage can list the fields that must be filled before a record
    may enter it (`required_fields`), and the stages a record may move to
    next (`next`). Both only bind when the tenant has switched enforcement
    on, exactly like the stage list itself;
  * history — every stage change is appended to the record's own
    `stage_history` (so it inherits the record's visibility rules instead of
    needing a second permission model) and stamps `stage_entered_at`;
  * automations — tenant-defined rules ("when a Quotation enters Won, create
    a task for the owner, due in 2 days") that run after the write.

Everything here is pure (no db, no FastAPI) so it can be unit-tested
directly; server.py does the reads and writes.
"""
from __future__ import annotations

import re
import typing
from datetime import date, timedelta
from typing import Any, Iterable, Optional

import models as m
import notifications
import tenancy

# ── field catalog ──────────────────────────────────────────────────────────
# The create model behind each workflow entity: the source of truth for which
# fields a stage may require or an automation may set.
ENTITY_MODELS = {
    "visitor": m.VisitorCreate, "lead": m.LeadCreate, "customer": m.CustomerCreate,
    "quote": m.QuoteCreate, "sale": m.SaleCreate, "project": m.ProjectCreate,
    "vendor_order": m.ManufacturerOrderCreate, "purchase_order": m.PurchaseOrderCreate,
    "invoice": m.InvoiceCreate, "product": m.InventoryCreate, "task": m.TaskCreate,
}

# Never offered: server-maintained bookkeeping, approval state, and anything
# the workflow itself owns.
_HIDDEN_FIELDS = {
    "stage", "status", "approval", "approved_by", "approved_at", "version",
    "updated_at", "completed_at", "created_at", "created_by", "tenant_id", "id",
    "image_url", "done",
}

# Fields an automation may never overwrite, even though a stage may require
# them: document numbers and totals are computed server-side, and owner
# fields decide who can SEE a record (see make_crud's owner_field/personal),
# so a rule rewriting them would silently move records between people.
_UNSETTABLE_FIELDS = {
    "quote_no", "sale_no", "po_no", "order_code", "invoice_no", "project_no", "sku",
    "vendor_name", "vendor_code", "by_user", "assigned_to", "attend_person",
    "assigned_engineer", "subtotal", "tax_total", "grand_total", "tax_amount",
    "final_total", "bank_due", "other_due", "total_paid", "total_balance_due",
    "paid", "balance", "lifetime_value", "cgst", "sgst", "igst", "total",
}

# Who "owns" a record, for rules that assign work to the owner. A name, not an
# id: that is what tasks.assigned_to and the rest of this codebase carry.
OWNER_FIELD = {
    "visitor": "attend_person", "lead": "assigned_to", "quote": "by_user",
    "sale": "by_user", "project": "assigned_engineer", "vendor_order": "by_user",
    "purchase_order": "by_user", "invoice": "by_user", "task": "assigned_to",
}

# What to call a record in a task title / message.
_TITLE_FIELDS = ("name", "customer", "title", "quote_no", "sale_no", "project_no",
                 "order_code", "po_no", "invoice_no", "sku")


def _field_type(annotation) -> Optional[str]:
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    base = args[0] if len(args) == 1 else annotation
    if base is bool:
        return "bool"
    if base in (int, float):
        return "number"
    if base is str:
        return "text"
    return None                      # lists/dicts/nested models: not rule-addressable


def _label(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def field_catalog(entity: str) -> list[dict]:
    """[{key, label, type, settable}] for the builder's pickers."""
    model = ENTITY_MODELS.get(entity)
    if not model:
        return []
    out = []
    for name, f in model.model_fields.items():
        if name in _HIDDEN_FIELDS or name == tenancy.stage_field(entity):
            continue
        if name.endswith("_id") and name not in ("customer_id",):
            continue
        ftype = _field_type(f.annotation)
        if not ftype:
            continue
        out.append({"key": name, "label": _label(name), "type": ftype,
                    "settable": ftype in ("text", "bool") and name not in _UNSETTABLE_FIELDS})
    return out


def field_keys(entity: str) -> list[str]:
    return [f["key"] for f in field_catalog(entity)]


# ── gates ──────────────────────────────────────────────────────────────────
def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False                 # False is an answer, not a gap
    if isinstance(value, (int, float)):
        return value == 0            # a required amount of 0 was never filled in
    return not str(value).strip()


def missing_required(stage: dict | None, record: dict) -> list[str]:
    if not stage:
        return []
    return [f for f in stage.get("required_fields") or [] if is_blank(record.get(f))]


def transition_error(stages: list, from_value: Any, to_stage: dict) -> Optional[str]:
    """None when moving from `from_value` to `to_stage` is allowed."""
    current = tenancy.resolve_stage(stages, str(from_value or ""))
    if not current or current["key"] == to_stage["key"]:
        return None                  # unknown/legacy origin: nothing to hold it to
    allowed = current.get("next") or []
    if not allowed or to_stage["key"] in allowed:
        return None
    labels = [s["label"] for s in stages if s["key"] in allowed]
    return (f"A record at '{current['label']}' can only move to: {', '.join(labels)}.")


def history_entry(from_value: Any, to_value: str, user: dict, at: str) -> dict:
    return {"from": str(from_value or ""), "to": to_value, "at": at,
            "by": (user or {}).get("name", ""), "by_id": (user or {}).get("id", "")}


# ── automation rules ───────────────────────────────────────────────────────
TRIGGERS = ("stage_enter", "created")
ACTION_TYPES = ("create_task", "set_field", "notify_customer")
TASK_PRIORITIES = ("Low", "Medium", "High", "Urgent")
MAX_RULES = 25
MAX_ACTIONS = 5


def _clean_str(value: Any, limit: int) -> str:
    return str(value if value is not None else "").strip()[:limit]


def validate_rules(rules: Any, stages: list, entity: str) -> list[dict]:
    """Normalise and sanity-check an entity's automation rules. Raises ValueError."""
    if rules in (None, ""):
        return []
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    if len(rules) > MAX_RULES:
        raise ValueError(f"at most {MAX_RULES} automation rules per workflow")
    keys = {s["key"] for s in stages}
    catalog = {f["key"]: f for f in field_catalog(entity)}
    out, seen_ids = [], set()
    for i, raw in enumerate(rules, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"rule {i} must be an object")
        name = _clean_str(raw.get("name"), 120) or f"Rule {i}"
        trigger = str(raw.get("trigger") or "stage_enter")
        if trigger not in TRIGGERS:
            raise ValueError(f"{name}: trigger must be one of {list(TRIGGERS)}")
        stage = tenancy.stage_key(raw.get("stage") or "")
        if trigger == "stage_enter":
            if stage not in keys:
                raise ValueError(f"{name}: pick the stage that triggers this rule")
        else:
            stage = ""
        actions_raw = raw.get("actions") or []
        if not isinstance(actions_raw, list) or not actions_raw:
            raise ValueError(f"{name}: add at least one action")
        if len(actions_raw) > MAX_ACTIONS:
            raise ValueError(f"{name}: at most {MAX_ACTIONS} actions per rule")
        actions = [_validate_action(a, name, catalog, entity) for a in actions_raw]
        rule_id = _clean_str(raw.get("id"), 64) or m.new_id()
        if rule_id in seen_ids:
            rule_id = m.new_id()
        seen_ids.add(rule_id)
        out.append({"id": rule_id, "name": name, "active": raw.get("active", True) is not False,
                    "trigger": trigger, "stage": stage, "actions": actions})
    return out


def _validate_action(raw: Any, rule: str, catalog: dict, entity: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{rule}: each action must be an object")
    kind = raw.get("type")
    if kind == "create_task":
        title = _clean_str(raw.get("title"), 200)
        if not title:
            raise ValueError(f"{rule}: a task action needs a title")
        try:
            due = int(raw.get("due_in_days") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{rule}: due_in_days must be a whole number")
        if not 0 <= due <= 365:
            raise ValueError(f"{rule}: due_in_days must be between 0 and 365")
        priority = str(raw.get("priority") or "Medium")
        if priority not in TASK_PRIORITIES:
            raise ValueError(f"{rule}: priority must be one of {list(TASK_PRIORITIES)}")
        assign = _clean_str(raw.get("assign_to"), 120) or "owner"
        return {"type": kind, "title": title, "due_in_days": due, "priority": priority,
                "assign_to": assign}
    if kind == "set_field":
        field = str(raw.get("field") or "")
        spec = catalog.get(field)
        if not spec or not spec["settable"]:
            raise ValueError(f"{rule}: '{field}' is not a field an automation can set")
        value = raw.get("value")
        if spec["type"] == "bool":
            value = value in (True, "true", "True", "1", 1, "yes")
        else:
            value = _clean_str(value, 500)
        return {"type": kind, "field": field, "value": value}
    if kind == "notify_customer":
        event = str(raw.get("event") or "")
        if event not in notifications.EVENTS:
            raise ValueError(f"{rule}: unknown message template '{event}'")
        return {"type": kind, "event": event}
    raise ValueError(f"{rule}: action type must be one of {list(ACTION_TYPES)}")


def matching_rules(rules: Iterable[dict], *, created: bool, entered: Optional[dict]) -> list[dict]:
    """Active rules this write fires. `entered` is the stage the record just
    moved INTO (None when the stage did not change)."""
    out = []
    for r in rules or []:
        if not r.get("active", True):
            continue
        if r.get("trigger") == "created" and created:
            out.append(r)
        elif r.get("trigger") == "stage_enter" and entered and r.get("stage") == entered["key"]:
            out.append(r)
    return out


def record_title(record: dict) -> str:
    for f in _TITLE_FIELDS:
        v = str(record.get(f) or "").strip()
        if v:
            return v
    return ""


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def render(template: str, record: dict, stage_label: str) -> str:
    """'{name}' / '{stage}' / '{record}' / any scalar field → its value.
    Unknown placeholders are left as typed rather than raising."""
    def sub(mt):
        key = mt.group(1)
        if key == "stage":
            return stage_label
        if key == "record":
            return record_title(record)
        v = record.get(key)
        if isinstance(v, float) and v.is_integer():
            return str(int(v))            # 600000.0 reads as 600000 in a task title
        return str(v) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else mt.group(0)
    return _PLACEHOLDER.sub(sub, template or "")


def task_for(action: dict, entity: str, record: dict, stage_label: str, user: dict,
             today: Optional[date] = None) -> dict:
    """The task document a create_task action produces (without id/tenant)."""
    owner = str(record.get(OWNER_FIELD.get(entity, "")) or "").strip()
    assign = action.get("assign_to") or "owner"
    if assign == "owner":
        assignee = owner or (user or {}).get("name", "")
    elif assign == "actor":
        assignee = (user or {}).get("name", "")
    else:
        assignee = assign
    due = (today or date.today()) + timedelta(days=int(action.get("due_in_days") or 0))
    return {
        "title": render(action["title"], record, stage_label),
        "priority": action.get("priority") or "Medium",
        "due_date": due.isoformat(), "assigned_to": assignee,
        "category": "Workflow", "ref": record.get("id", ""), "ref_type": entity,
        "linked_entity_name": record_title(record), "notes": "", "done": False,
        "status": "Pending", "created_by": (user or {}).get("name", ""),
        "created_by_id": (user or {}).get("id", ""),
    }


def record_phone(record: dict) -> str:
    return str(record.get("phone") or record.get("customer_phone") or "").strip()
