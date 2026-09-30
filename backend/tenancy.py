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
WORKFLOW_ENTITIES = ["visitor", "lead", "customer", "quote", "sale", "project",
                     "vendor_order", "purchase_order", "invoice", "product", "task"]

# Which collection each entity's records live in.
ENTITY_COLLECTION = {
    "visitor": "visitors", "lead": "leads", "customer": "customers", "quote": "quotes",
    "sale": "sales", "project": "projects", "vendor_order": "manufacturer_orders",
    "purchase_order": "purchase_orders", "invoice": "invoices",
    "product": "inventory", "task": "tasks",
}
COLLECTION_ENTITY = {v: k for k, v in ENTITY_COLLECTION.items()}

# Display names for the workflow builder and error messages.
ENTITY_LABELS = {
    "visitor": "Visitors", "lead": "Leads", "customer": "Customers",
    "quote": "Quotations", "sale": "Sales Orders", "project": "Projects",
    "vendor_order": "Vendor Orders", "purchase_order": "Purchase Orders",
    "invoice": "Invoices", "product": "Products", "task": "Tasks",
}

# The field that holds an entity's position in its workflow. Most records
# carry `stage`; these carry a `status` instead.
STAGE_FIELD = {
    "vendor_order": "status", "purchase_order": "status",
    "invoice": "status", "task": "status",
}


def stage_field(entity: str) -> str:
    return STAGE_FIELD.get(entity, "stage")


# Entities whose stage list is a system state machine, not tenant vocabulary.
# Project P&L, committed spend, payroll/notification triggers and model
# validators key off these exact strings, so a tenant may configure
# everything ABOUT each stage (probability, guidance, required fields,
# allowed next stages, colour, automations) but never add, drop or rename
# one. Kept in sync with models.py by tests/test_workflow_engine.py.
LOCKED_STAGES: dict[str, list] = {
    "project": ["Survey", "Quoted", "Execution", "Review", "Closure", "Completed"],
    "vendor_order": ["Quoted", "Confirmed", "In Production", "Dispatched", "Delivered"],
    "purchase_order": ["Draft", "Issued", "Received", "Cancelled"],
    "invoice": ["Draft", "Sent", "Paid", "Cancelled"],
    "task": ["Pending", "In Progress", "Completed", "Rolled Over"],
}

# Collections that hold per-tenant business data and must always be scoped.
TENANT_COLLECTIONS = {
    "visitors", "leads", "architects", "quotes", "sales", "inventory", "tasks",
    "invoices", "meets", "petty_cash", "quote_lines", "dw_openings", "dw_surveys",
    "projects", "payments", "stock_movements", "customers", "activities",
    "settings", "workflows", "attendance", "vendors", "floors",
    "commission_rules", "commission_payouts",
    "requirements", "product_configs", "teams", "roles", "audit_log", "notification_logs",
    "cashbooks", "cashbook_entries", "agent_tasks", "agent_conversations",
    "record_contacts", "saved_views", "custom_field_defs", "finance_payments",
    "project_daily_logs", "business_profiles", "purchase_orders",
    "sites", "cashbook_transactions", "manufacturer_orders", "documents",
    "discussions", "whatsapp_messages",
    # Canonical CRM v1 (models_canonical.py / api_canonical.py) — same
    # tenant_id chokepoint as everything else, just new collections.
    "crm_accounts", "crm_contacts", "crm_leads", "crm_opportunities",
    "crm_products", "crm_quotations", "crm_activities",
    # HR: attendance -> payroll (models_hr.py / api_hr.py) — separate from
    # the legacy "attendance" collection above, same tenant_id chokepoint.
    "hr_attendance_logs", "payroll_periods", "leave_requests",
    # Tally sync (Phase 5, tally.py / server.py) — per-tenant connection
    # settings and the sync idempotency ledger.
    "tally_connections", "tally_sync_runs", "tally_sync_items",
    # Wallets (prompt_1_wallets.md, models_wallet.py / api_wallets.py) —
    # petty-cash -> project cash-position ledger.
    "wallets", "wallet_transactions",
    # Budgets (prompt_3_budgets.md, models_budget.py / api_budget.py) —
    # cost-center spend control (budget/lines/overrides/transactions).
    "budgets", "budget_lines", "budget_overrides", "budget_transactions",
}

# Entities a tenant can define custom fields for. Values live on the record's
# own document (Lead.custom_fields / Customer.custom_fields / Project.custom_fields),
# not here.
CUSTOM_FIELD_ENTITIES = ["lead", "customer", "project"]

SYSTEM_TENANT = "system"          # reserved; never assigned to a business


# ── stage helpers ──────────────────────────────────────────────────────────
def stage_key(label: str) -> str:
    """'Adv Received' -> 'adv_received'. Stable id so labels can be renamed."""
    return re.sub(r"[^a-z0-9]+", "_", str(label or "").strip().lower()).strip("_")


def make_stage(label: str, *, terminal: bool = False, won: bool = False,
               color: str = "", probability: int | None = None) -> dict:
    return {
        "key": stage_key(label),
        "label": str(label).strip(),
        "terminal": bool(terminal),   # no further movement expected
        "won": bool(won),             # counts as a positive outcome in reports
        "color": color or "",
        # Chance a record at this stage reaches a won stage, 0-100. Drives the
        # weighted pipeline. None = not a forecast stage.
        "probability": probability,
        "guidance": "",               # "guidance for success" shown on the record's Path
        "required_fields": [],        # must be filled before a record can enter this stage
        "next": [],                   # stage keys allowed next; empty = any stage
    }


def _stages(*specs) -> list:
    """Each spec is a label, or (label, terminal, won[, probability])."""
    out = []
    for s in specs:
        if isinstance(s, tuple):
            out.append(make_stage(s[0], terminal=s[1], won=s[2],
                                  probability=s[3] if len(s) > 3 else None))
        else:
            out.append(make_stage(s))
    return out


def _p(label: str, probability: int):
    """A non-terminal stage with a forecast probability."""
    return (label, False, False, probability)


# Sensible starting workflows for a brand-new tenant. Generic on purpose — a
# business renames these to its own language rather than inheriting MADIO's.
DEFAULT_WORKFLOWS: dict[str, list] = {
    # The stage vocabularies below are the ones the app's own screens already
    # use (Leads/Pipeline/Visitors), so an unconfigured tenant sees the same
    # stages in the workflow builder as on the pages.
    "visitor":  _stages("New", "Qualified", "Quoted", "Negotiation",
                        ("Won", True, True), ("Lost", True, False),
                        ("Delivered", True, True)),
    "lead":     _stages(_p("New", 10), _p("Contacted", 20), _p("Qualified", 30),
                        _p("Quoted", 50), _p("Negotiation", 70),
                        ("Won", True, True, 100), ("Lost", True, False, 0)),
    # "Active" is a customer's success state — not terminal (they can go
    # dormant and come back), but it is what conversion reporting counts.
    "customer": _stages("Prospect", ("Active", False, True), ("Dormant", True, False)),
    "quote":    _stages(_p("New", 10), _p("Qualified", 30), _p("Quoted", 50),
                        _p("Negotiation", 70), ("Won", True, True, 100),
                        ("Lost", True, False, 0)),
    "sale":     _stages("Confirmed", "In Progress", "Delivered",
                        ("Completed", True, True), ("Cancelled", True, False)),
    "project":  _stages("Survey", "Quoted", "Execution", "Review", "Closure",
                        ("Completed", True, True)),
    "vendor_order": _stages("Quoted", "Confirmed", "In Production", "Dispatched",
                            ("Delivered", True, True)),
    "purchase_order": _stages("Draft", "Issued", ("Received", True, True),
                              ("Cancelled", True, False)),
    "invoice":  _stages("Draft", "Sent", ("Paid", True, True), ("Cancelled", True, False)),
    # An "Active" product is the sellable state — the one reports count.
    "product":  _stages("Draft", ("Active", False, True), ("Discontinued", True, False)),
    "task":     _stages("Pending", "In Progress", ("Completed", True, True), "Rolled Over"),
}


def default_workflow(entity: str) -> list:
    stages = DEFAULT_WORKFLOWS.get(entity) or _stages("New", ("Done", True, True))
    return [{**s, "required_fields": list(s["required_fields"]), "next": list(s["next"])}
            for s in stages]


def validate_stages(stages: Any, entity: str = "", fields: Iterable[str] | None = None) -> list:
    """Normalise and sanity-check a stage list coming from an API caller.

    `entity` enables the locked-stage check; `fields`, when given, is the set
    of field names `required_fields` may reference."""
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
            "color": str(raw.get("color") or "")[:32],
            "probability": _probability(raw.get("probability"), label),
            "guidance": str(raw.get("guidance") or "").strip()[:2000],
            "required_fields": _field_list(raw.get("required_fields"), label, fields),
            "next": [stage_key(k) for k in (raw.get("next") or []) if stage_key(k)],
        })
    if len(out) > 40:
        raise ValueError("a workflow cannot have more than 40 stages")
    keys = {s["key"] for s in out}
    for s in out:
        unknown = [k for k in s["next"] if k not in keys]
        if unknown:
            raise ValueError(f"stage {s['label']!r} allows moving to unknown stage(s): {unknown}")
        s["next"] = [k for k in dict.fromkeys(s["next"]) if k != s["key"]]
    if entity in LOCKED_STAGES:
        want = [stage_key(x) for x in LOCKED_STAGES[entity]]
        if [s["key"] for s in out] != want:
            raise ValueError(
                f"{ENTITY_LABELS.get(entity, entity)} stages are fixed by the system "
                f"({', '.join(LOCKED_STAGES[entity])}); you can configure each stage "
                f"but not add, remove, rename or reorder them")
        for s, label in zip(out, LOCKED_STAGES[entity]):
            s["label"] = label
    return out


def _probability(value: Any, label: str):
    if value is None or value == "":
        return None
    try:
        p = int(round(float(value)))
    except (TypeError, ValueError):
        raise ValueError(f"stage {label!r}: probability must be a number")
    if not 0 <= p <= 100:
        raise ValueError(f"stage {label!r}: probability must be between 0 and 100")
    return p


def _field_list(value: Any, label: str, fields: Iterable[str] | None) -> list:
    if not value:
        return []
    if not isinstance(value, list):
        raise ValueError(f"stage {label!r}: required_fields must be a list")
    out = list(dict.fromkeys(str(f).strip() for f in value if str(f).strip()))
    if fields is not None:
        allowed = set(fields)
        bad = [f for f in out if f not in allowed]
        if bad:
            raise ValueError(f"stage {label!r}: unknown field(s) {bad}")
    if len(out) > 20:
        raise ValueError(f"stage {label!r}: at most 20 required fields")
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
