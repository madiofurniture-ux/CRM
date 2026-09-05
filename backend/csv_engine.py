"""
Bulk CSV export/import engine for Leads and Customers.

Two entities, one engine: export streams every tenant-owned document (base
fields + active custom fields) as CSV without buffering the whole result set;
import parses an uploaded CSV, lets the caller map its columns onto known
fields (base or custom), and commits row-by-row so one bad row doesn't sink
the whole file — the response reports exactly which rows failed and why.

Reuses lifecycle.csv_cell (CSV-injection guarding) and lifecycle.from_csv
(whole-buffer parse — fine for import since the upload is already fully in
memory as UploadFile bytes; only export needs a true streaming writer).
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any, AsyncGenerator, Optional

from pydantic import ValidationError

import lifecycle as lc
import tenancy
from models import LeadCreate, CustomerCreate, new_id, now_iso

logger = logging.getLogger("madio")

# ponytail: fixed caps — raise or move to chunked/background processing if a
# real import ever needs more than this in one file.
MAX_IMPORT_ROWS = 20_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024

ENTITY_CONFIG = {
    "leads": {
        "collection": "leads",
        "custom_entity": "lead",
        "create_model": LeadCreate,
        # Mirrors make_crud(api, "leads", ..., owner_field="assigned_to") —
        # a caller scoped to "own"/"team" must not export/import outside it.
        "owner_field": "assigned_to",
        "base_fields": [
            "id", "created_at", "date", "name", "phone", "source", "reference",
            "stage", "follow_up_date", "remarks", "assigned_to", "attended_by",
            "confidence_level", "team_id", "visitor_id", "value",
        ],
    },
    "customers": {
        "collection": "customers",
        "custom_entity": "customer",
        "create_model": CustomerCreate,
        # No owner_field on make_crud's customers registration either — "own"/
        # "team" scope already behaves like "all" for customers app-wide.
        "owner_field": None,
        "base_fields": [
            "id", "created_at", "name", "phone", "email", "address", "gstin",
            "division", "stage", "lead_id", "first_sale_id", "customer_since",
            "lifetime_value", "balance", "remarks", "confidence_level", "team_id",
            "gender", "maps_url", "lat", "lng", "alt_contact_name", "alt_phone",
        ],
    },
}


def _owner_scoped(query: dict, cfg: dict, owners: Optional[list]) -> dict:
    """Add the "own"/"team" permission-scope filter to a query — same
    restriction make_crud's _list/_update apply via owner_field/_scope_owners.
    `owners=None` means no restriction ("all" scope, or the entity has no
    owner_field); a list restricts to those owner-field values."""
    if owners is not None and cfg.get("owner_field"):
        query[cfg["owner_field"]] = {"$in": owners}
    return query


async def _custom_defs(db, entity: str, user: dict) -> list[dict]:
    q = tenancy.scope({"entity": ENTITY_CONFIG[entity]["custom_entity"], "active": True},
                       "custom_field_defs", user)
    return await db.custom_field_defs.find(q, {"_id": 0}).sort("order", 1).to_list(200)


async def export_fields(db, entity: str, user: dict) -> list[str]:
    base = ENTITY_CONFIG[entity]["base_fields"]
    defs = await _custom_defs(db, entity, user)
    return base + [d["key"] for d in defs]


def _row_values(doc: dict, fields: list[str], custom_keys: set[str]) -> list[str]:
    custom = doc.get("custom_fields") or {}
    return [lc.csv_cell(custom.get(f) if f in custom_keys else doc.get(f)) for f in fields]


async def stream_csv_rows(db, entity: str, user: dict, owners: Optional[list] = None) -> AsyncGenerator[str, None]:
    cfg = ENTITY_CONFIG[entity]
    defs = await _custom_defs(db, entity, user)
    custom_keys = {d["key"] for d in defs}
    fields = cfg["base_fields"] + list(custom_keys)

    header_buf = io.StringIO()
    csv.writer(header_buf).writerow(fields)
    yield header_buf.getvalue()

    q = _owner_scoped(tenancy.scope({}, cfg["collection"], user), cfg, owners)
    cursor = db[cfg["collection"]].find(q, {"_id": 0}).batch_size(500)
    async for doc in cursor:
        buf = io.StringIO()
        csv.writer(buf).writerow(_row_values(doc, fields, custom_keys))
        yield buf.getvalue()


CASHBOOK_ENTRY_FIELDS = [
    "id", "created_at", "cashbook_id", "type", "amount", "category",
    "payment_mode", "remark", "receipt_url", "entry_person",
    "status", "approved_by", "approved_at",
]


async def stream_cashbook_entries_csv(db, user: dict) -> AsyncGenerator[str, None]:
    """Export-only — deliberately no import counterpart. A generic CSV
    import would insert_one straight into cashbook_entries and skip the
    $inc balance/approval side effects that cashbook_top_up/expense/approve
    enforce, silently corrupting a book's running balance."""
    header_buf = io.StringIO()
    csv.writer(header_buf).writerow(CASHBOOK_ENTRY_FIELDS)
    yield header_buf.getvalue()

    cursor = db.cashbook_entries.find(
        tenancy.scope({}, "cashbook_entries", user), {"_id": 0}).sort("created_at", -1).batch_size(500)
    async for doc in cursor:
        buf = io.StringIO()
        csv.writer(buf).writerow([lc.csv_cell(doc.get(f)) for f in CASHBOOK_ENTRY_FIELDS])
        yield buf.getvalue()


PROJECT_PNL_FIELDS = [
    "project_id", "project_no", "customer", "stage", "contract_value",
    "approved_petty_cash", "gross_profit", "margin_pct", "float_balance",
    "pending_petty_cash", "wallet_count",
]


async def compute_project_pnl(db, user: dict) -> dict:
    """Project profitability: Project.value is the contract/deal revenue
    (there is no separate Deal collection in this codebase — a Project IS
    the deal record); direct site cost is approved CASH_OUT spend on the
    Cashbook wallet(s) linked to that project via Cashbook.project_id.

    Pending CASH_OUT entries never affect realized margin (they haven't
    debited any wallet yet — see cashbook_expense/cashbook_entry_approve in
    server.py) but do count toward `pending_petty_cash` exposure, so an
    approval backlog is visible before it lands."""
    projects = await db.projects.find(tenancy.scope({}, "projects", user), {"_id": 0}).to_list(5000)
    books = await db.cashbooks.find(tenancy.scope({}, "cashbooks", user), {"_id": 0}).to_list(5000)

    books_by_project: dict[str, list[dict]] = {}
    for b in books:
        pid = b.get("project_id") or ""
        if not pid:
            continue
        books_by_project.setdefault(pid, []).append(b)

    book_ids = [b["id"] for b in books if b.get("project_id")]
    entries = []
    if book_ids:
        entries = await db.cashbook_entries.find(
            tenancy.scope({"cashbook_id": {"$in": book_ids}, "type": "CASH_OUT"}, "cashbook_entries", user),
            {"_id": 0}).to_list(20000)
    entries_by_book: dict[str, list[dict]] = {}
    for e in entries:
        entries_by_book.setdefault(e["cashbook_id"], []).append(e)

    out = []
    total_revenue = total_approved = total_pending = 0.0
    for p in projects:
        pid = p["id"]
        pbooks = books_by_project.get(pid, [])
        pentries = [e for b in pbooks for e in entries_by_book.get(b["id"], [])]
        approved = sum(e["amount"] for e in pentries if e.get("status") == "Approved")
        pending = sum(e["amount"] for e in pentries if e.get("status") == "Pending")
        float_balance = sum(b.get("current_balance", 0) for b in pbooks)
        revenue = p.get("value", 0) or 0
        gross_profit = revenue - approved
        margin_pct = round((gross_profit / revenue) * 100, 2) if revenue else 0.0

        by_category: dict[str, float] = {}
        for e in pentries:
            if e.get("status") != "Approved":
                continue
            cat = e.get("category") or "Other"
            by_category[cat] = by_category.get(cat, 0) + e["amount"]

        total_revenue += revenue
        total_approved += approved
        total_pending += pending

        out.append({
            "project_id": pid, "project_no": p.get("project_no", ""),
            "customer": p.get("customer", ""), "stage": p.get("stage", ""),
            "contract_value": revenue, "approved_petty_cash": approved,
            "gross_profit": gross_profit, "margin_pct": margin_pct,
            "float_balance": float_balance, "pending_petty_cash": pending,
            "wallet_count": len(pbooks),
            "category_breakdown": [{"category": k, "amount": v} for k, v in
                                    sorted(by_category.items(), key=lambda kv: -kv[1])],
        })

    out.sort(key=lambda r: -r["contract_value"])
    aggregate_margin = round(((total_revenue - total_approved) / total_revenue) * 100, 2) if total_revenue else 0.0
    return {
        "summary": {
            "total_contract_revenue": total_revenue,
            "total_field_cash_spent": total_approved,
            "aggregate_margin_pct": aggregate_margin,
            "pending_exposure": total_pending,
        },
        "projects": out,
    }


async def stream_project_pnl_csv(db, user: dict) -> AsyncGenerator[str, None]:
    pnl = await compute_project_pnl(db, user)
    header_buf = io.StringIO()
    csv.writer(header_buf).writerow(PROJECT_PNL_FIELDS)
    yield header_buf.getvalue()
    for row in pnl["projects"]:
        buf = io.StringIO()
        csv.writer(buf).writerow([lc.csv_cell(row.get(f)) for f in PROJECT_PNL_FIELDS])
        yield buf.getvalue()


def suggest_mapping(headers: list[str], base_fields: list[str], custom_defs: list[dict]) -> dict[str, str]:
    """Case-insensitive match of each CSV header to a base field or a custom
    field's key/label; unmatched headers map to "" (skip)."""
    targets: dict[str, str] = {f.lower(): f for f in base_fields if f != "created_at"}
    for d in custom_defs:
        targets.setdefault(d["key"].lower(), d["key"])
        targets.setdefault(d["label"].lower(), d["key"])

    out = {}
    for h in headers:
        hl = h.strip().lower()
        if hl in targets:
            out[h] = targets[hl]
            continue
        match = next((field for key, field in targets.items() if key in hl or hl in key), "")
        out[h] = match
    return out


async def preview_import(db, entity: str, user: dict, csv_text: str) -> dict:
    cfg = ENTITY_CONFIG[entity]
    rows = lc.from_csv(csv_text)
    headers = list(rows[0].keys()) if rows else []
    defs = await _custom_defs(db, entity, user)
    fields = [f for f in cfg["base_fields"] if f != "created_at"] + [d["key"] for d in defs]
    return {
        "headers": headers,
        "sample_rows": rows[:5],
        "suggested_mapping": suggest_mapping(headers, cfg["base_fields"], defs),
        "fields": fields,
        "row_count": len(rows),
    }


async def commit_import(db, entity: str, user: dict, csv_text: str, mapping: dict[str, str],
                         owners: Optional[list] = None) -> dict:
    cfg = ENTITY_CONFIG[entity]
    defs = await _custom_defs(db, entity, user)
    custom_keys = {d["key"] for d in defs}
    rows = lc.from_csv(csv_text)
    if len(rows) > MAX_IMPORT_ROWS:
        rows = rows[:MAX_IMPORT_ROWS]

    imported = updated = failed = 0
    errors: list[dict] = []

    for i, raw in enumerate(rows, start=2):  # row 1 is the header
        record: dict[str, Any] = {}
        custom: dict[str, Any] = {}
        row_id = ""
        for header, value in raw.items():
            field = mapping.get(header, "")
            if not field:
                continue
            if field == "id":
                row_id = str(value or "").strip()
            elif field in custom_keys:
                custom[field] = value
            else:
                record[field] = value
        if custom:
            record["custom_fields"] = custom

        try:
            existing = None
            if row_id:
                # Out-of-scope id reads as "not found" — same 404-not-403
                # convention make_crud's _update uses, so a caller can't
                # probe which ids exist outside their own scope.
                owned = _owner_scoped(tenancy.scope({"id": row_id}, cfg["collection"], user), cfg, owners)
                existing = await db[cfg["collection"]].find_one(owned)
            if existing:
                merged = {**existing, **record}
                validated = cfg["create_model"](**merged).model_dump()
                updates = {k: validated[k] for k in record if k in validated}
                await db[cfg["collection"]].update_one(owned, {"$set": updates})
                updated += 1
            else:
                validated = cfg["create_model"](**record).model_dump()
                validated["id"] = new_id()
                validated["created_at"] = now_iso()
                tenancy.stamp(validated, cfg["collection"], user)
                await db[cfg["collection"]].insert_one(dict(validated))
                imported += 1
        except ValidationError as e:
            failed += 1
            msg = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
            errors.append({"row": i, "error": msg})
        except Exception:  # noqa: BLE001 — one bad row must never abort the batch
            logger.exception("csv_engine.commit_import: row %d failed", i)
            failed += 1
            errors.append({"row": i, "error": "Import failed — see server log"})

    return {"imported": imported, "updated": updated, "failed": failed, "errors": errors}
