"""
Multi-tenancy and configurable entity workflows.

This is the foundation for running the CRM as a product for many businesses
instead of one. Two ideas, kept deliberately small:

1. TENANCY — every business record carries `tenant_id`. Reads are scoped to the
   signed-in user's tenant; writes are stamped with it. The tenant comes from
   the authenticated USER record, never from a header or a token claim the
   client could edit.

   Storage model: one database, `tenant_id` on every document. For this scale
   that beats a database per tenant — one connection pool, one migration, one
   backup — and the isolation guarantee lives in a single chokepoint below.

   FAIL CLOSED: if a caller has no tenant, queries match NOTHING rather than
   everything. A bug must lose data visibility, never leak another business's
   records.

2. WORKFLOWS — stages were hardcoded in five places in MADIO's own vocabulary
   ("Adv Received", "Site Not Ready"). A furniture retailer, a clinic and an
   agency need different words. Each tenant now owns a stage list per entity,
   stored as data and editable at runtime.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Entities a tenant can define a workflow for. Adding one here is all it takes
# for the API and UI to expose it.
WORKFLOW_ENTITIES = ["lead", "customer", "quote", "sale", "project", "product", "task"]

# Which collection each entity's records live in.
ENTITY_COLLECTION = {
    "lead": "leads", "customer": "customers", "quote": "quotes", "sale": "sales",
    "project": "projects", "product": "inventory", "task": "tasks",
}
COLLECTION_ENTITY = {v: k for k, v in ENTITY_COLLECTION.items()}

# Collections that hold per-tenant business data and must always be scoped.
TENANT_COLLECTIONS = {
    "visitors", "leads", "architects", "quotes", "sales", "inventory", "tasks",
    "invoices", "meets", "petty_cash", "quote_lines", "dw_openings", "dw_surveys",
    "projects", "payments", "stock_movements", "customers", "activities",
    "settings", "workflows", "attendance", "commission_rules", "commission_payouts",
    "requirements", "product_configs", "teams", "roles", "audit_log", "notification_logs",
    "cashbooks", "cashbook_entries", "agent_tasks", "agent_conversations",
}

SYSTEM_TENANT = "system"          # reserved; never assigned to a business


# ── stage helpers ──────────────────────────────────────────────────────────
def stage_key(label: str) -> str:
    """'Adv Received' -> 'adv_received'. Stable id so labels can be renamed."""
    return re.sub(r"[^a-z0-9]+", "_", str(label or "").strip().lower()).strip("_")


def make_stage(label: str, *, terminal: bool = False, won: bool = False,
               color: str = "") -> dict:
    return {
        "key": stage_key(label),
        "label": str(label).strip(),
        "terminal": bool(terminal),   # no further movement expected
        "won": bool(won),             # counts as a positive outcome in reports
        "color": color or "",
    }


def _stages(*specs) -> list:
    out = []
    for s in specs:
        out.append(make_stage(s[0], terminal=s[1], won=s[2]) if isinstance(s, tuple)
                   else make_stage(s))
    return out


# Sensible starting workflows for a brand-new tenant. Generic on purpose — a
# business renames these to its own language rather than inheriting MADIO's.
DEFAULT_WORKFLOWS: dict[str, list] = {
    "lead":     _stages("New", "Contacted", "Qualified",
                        ("Converted", True, True), ("Lost", True, False)),
    # "Active" is a customer's success state — not terminal (they can go
    # dormant and come back), but it is what conversion reporting counts.
    "customer": _stages("Prospect", ("Active", False, True), ("Dormant", True, False)),
    "quote":    _stages("Draft", "Sent", "Negotiation",
                        ("Won", True, True), ("Lost", True, False),
                        ("Expired", True, False)),
    "sale":     _stages("Confirmed", "In Progress", "Delivered",
                        ("Completed", True, True), ("Cancelled", True, False)),
    "project":  _stages("Planned", "In Progress", "Review",
                        ("Completed", True, True), ("On Hold", False, False)),
    # An "Active" product is the sellable state — the one reports count.
    "product":  _stages("Draft", ("Active", False, True), ("Discontinued", True, False)),
    "task":     _stages("To Do", "Doing", ("Done", True, True)),
}


def default_workflow(entity: str) -> list:
    return [dict(s) for s in DEFAULT_WORKFLOWS.get(entity, _stages("New", ("Done", True, True)))]


def validate_stages(stages: Any) -> list:
    """Normalise and sanity-check a stage list coming from an API caller."""
    if not isinstance(stages, list) or not stages:
        raise ValueError("stages must be a non-empty list")
    out, seen = [], set()
    for raw in stages:
        if isinstance(raw, str):
            raw = {"label": raw}
        if not isinstance(raw, dict):
            raise ValueError("each stage must be an object or a string")
        label = str(raw.get("label") or raw.get("name") or "").strip()
        if not label:
            raise ValueError("every stage needs a label")
        key = stage_key(raw.get("key") or label)
        if not key:
            raise ValueError(f"stage {label!r} produces an empty key")
        if key in seen:
            raise ValueError(f"duplicate stage: {label!r}")
        seen.add(key)
        out.append({
            "key": key, "label": label,
            "terminal": bool(raw.get("terminal")),
            "won": bool(raw.get("won")),
            "color": str(raw.get("color") or ""),
        })
    if len(out) > 40:
        raise ValueError("a workflow cannot have more than 40 stages")
    return out


def stage_labels(stages: Iterable[dict]) -> list:
    return [s["label"] for s in stages]


def resolve_stage(stages: list, value: str) -> dict | None:
    """Match by key or label, case-insensitively — imported data is inconsistent."""
    v = str(value or "").strip()
    if not v:
        return None
    k = stage_key(v)
    for s in stages:
        if s["key"] == k or s["label"].lower() == v.lower():
            return s
    return None


# ── tenant scoping ─────────────────────────────────────────────────────────
def tenant_of(user: dict | None) -> str:
    """The tenant a request acts within. Comes from the user record only."""
    return str((user or {}).get("tenant_id") or "").strip()


def scope(query: dict | None, collection: str, user: dict | None) -> dict:
    """
    Add the tenant filter to a Mongo query.

    Fail closed: a caller with no tenant gets a query that cannot match, so a
    missing tenant shows an empty screen instead of every customer's data.
    """
    q = dict(query or {})
    if collection not in TENANT_COLLECTIONS:
        return q
    tid = tenant_of(user)
    if not tid:
        q["tenant_id"] = "__no_tenant__"
        return q
    q["tenant_id"] = tid
    return q


def stamp(doc: dict, collection: str, user: dict | None) -> dict:
    """Attach the tenant to a document being written."""
    if collection in TENANT_COLLECTIONS:
        tid = tenant_of(user)
        if tid:
            doc["tenant_id"] = tid
    return doc


def slugify_tenant(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return s or "tenant"
