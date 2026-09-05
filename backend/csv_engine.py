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
from typing import Any, AsyncGenerator

from pydantic import ValidationError

import lifecycle as lc
import tenancy
from models import LeadCreate, CustomerCreate, new_id, now_iso

# ponytail: fixed caps — raise or move to chunked/background processing if a
# real import ever needs more than this in one file.
MAX_IMPORT_ROWS = 20_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024

ENTITY_CONFIG = {
    "leads": {
        "collection": "leads",
        "custom_entity": "lead",
        "create_model": LeadCreate,
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
        "base_fields": [
            "id", "created_at", "name", "phone", "email", "address", "gstin",
            "division", "stage", "lead_id", "first_sale_id", "customer_since",
            "lifetime_value", "balance", "remarks", "confidence_level", "team_id",
            "gender", "maps_url", "lat", "lng", "alt_contact_name", "alt_phone",
        ],
    },
}


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


async def stream_csv_rows(db, entity: str, user: dict) -> AsyncGenerator[str, None]:
    cfg = ENTITY_CONFIG[entity]
    defs = await _custom_defs(db, entity, user)
    custom_keys = {d["key"] for d in defs}
    fields = cfg["base_fields"] + list(custom_keys)

    header_buf = io.StringIO()
    csv.writer(header_buf).writerow(fields)
    yield header_buf.getvalue()

    cursor = db[cfg["collection"]].find(
        tenancy.scope({}, cfg["collection"], user), {"_id": 0}).batch_size(500)
    async for doc in cursor:
        buf = io.StringIO()
        csv.writer(buf).writerow(_row_values(doc, fields, custom_keys))
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


async def commit_import(db, entity: str, user: dict, csv_text: str, mapping: dict[str, str]) -> dict:
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
                existing = await db[cfg["collection"]].find_one(
                    tenancy.scope({"id": row_id}, cfg["collection"], user))
            if existing:
                merged = {**existing, **record}
                validated = cfg["create_model"](**merged).model_dump()
                updates = {k: validated[k] for k in record if k in validated}
                await db[cfg["collection"]].update_one(
                    tenancy.scope({"id": row_id}, cfg["collection"], user), {"$set": updates})
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
        except Exception as e:  # noqa: BLE001 — one bad row must never abort the batch
            failed += 1
            errors.append({"row": i, "error": str(e)})

    return {"imported": imported, "updated": updated, "failed": failed, "errors": errors}
