"""
Migrate the LIVE business data out of the Google Sheets backend into MongoDB Atlas.

Why
---
The Emergent app ships demo rows (25 visitors, 15 leads, 15 quotes, 80 sales,
10 architects). The real records live in the Google Sheets backend that the
single-file web CRM uses. This pulls them over and maps them onto the Emergent
Pydantic models so the React app shows the actual business.

Design notes
------------
* READ-ONLY against Google Sheets (`action=read`). Nothing is written back there.
* Idempotent per collection: an existing document with the same natural key is
  UPDATED, never duplicated (upsert on quote_no / sale_no / phone+date / name).
* Field hygiene ported from the web app's hard-won rules:
    - phones come back from Sheets as NUMBERS -> always str-coerce, keep last 10
    - dates are wildly inconsistent ('04//01/26', '24/o1/2026') -> best-effort
    - `value > 1e10` is a timestamp that leaked into a money column -> zero it
* Rows with a blank natural key are skipped (the known empty-id junk rows).

Usage
-----
    python backend/tools/migrate_from_sheets.py --dry-run   # report only
    python backend/tools/migrate_from_sheets.py             # write to Atlas
"""
import asyncio
import json
import os
import re
import ssl
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

env_path = BACKEND / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

SHEETS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzO5fU8CrHmm6Kf1zWOvHgqNMyFz9voXF1G2P9DmWvr-S_KR6SYWzoRk5fUTW51kAjbZg/exec"
)
API_KEY = "madio_secret_crm_key_2026"
_ctx = ssl.create_default_context()


def fetch(sheet):
    url = f"{SHEETS_URL}?action=read&sheet={sheet}&apiKey={API_KEY}"
    with urllib.request.urlopen(url, timeout=120, context=_ctx) as r:
        return json.loads(r.read().decode()).get("rows", [])


def s(v):
    """Sheets returns numeric-looking text as numbers; always work in strings."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def phone(v):
    d = re.sub(r"\D", "", s(v))
    return d[-10:] if len(d) > 10 else d


def money(v):
    try:
        n = float(s(v).replace(",", "") or 0)
    except ValueError:
        return 0.0
    # a timestamp that leaked into a money column (the known corruption signature)
    return 0.0 if abs(n) > 1e10 else n


def date(v):
    t = s(v)
    if not t:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", t):
        return t[:10]
    m = re.search(r"(\d{1,2})[/\-.]+(\d{1,2})[/\-.]+(\d{2,4})", t)
    if m:
        d_, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return datetime(y, mo, d_).date().isoformat()
        except ValueError:
            return ""
    return ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


# ── mappers: Sheets row -> Emergent model dict ──────────────────────────────
def map_quote(r):
    if not s(r.get("id")):
        return None
    return {
        "quote_no": s(r.get("id")),
        "date": date(r.get("vdate") or r.get("qdate")),
        "customer": s(r.get("name")),
        "reference": s(r.get("ref")),
        "phone": phone(r.get("phone")),
        "division": s(r.get("div")) or "Furniture",
        "by_user": s(r.get("by")),
        "stage": s(r.get("stage")) or "Quoted",
        "value": money(r.get("value")),
        "cash": money(r.get("cash")),
        "bank": money(r.get("bank")),
        "mode": s(r.get("mode")),
        "remarks": s(r.get("remarks")),
    }


def map_sale(r):
    if not s(r.get("id")):
        return None
    val, paid = money(r.get("value")), money(r.get("paid"))
    bal = r.get("bal")
    # legacy rows carry paid=0,bal=0 meaning "settled, never itemised" -- do NOT
    # recompute those into phantom outstanding.
    balance = money(bal) if s(bal) != "" else max(0.0, val - paid)
    return {
        "sale_no": s(r.get("id")),
        "date": date(r.get("date")),
        "customer": s(r.get("name")),
        "division": s(r.get("div")) or "Furniture",
        "quote_ref": s(r.get("af")),
        "by_user": s(r.get("by")),
        "value": val,
        "paid": paid,
        "balance": balance,
        "stage": s(r.get("stage")) or "Adv Received",
        "remarks": s(r.get("remarks")),
    }


def map_visitor(r):
    nm = s(r.get("name"))
    if not nm:
        return None
    return {
        "date": date(r.get("date")),
        "name": nm,
        "location": "",
        "reference": s(r.get("ref")),
        "phone": phone(r.get("phone")),
        "requirement": s(r.get("req")),
        "attend_person": s(r.get("by")),
        "site_visit": "",
        "remarks": s(r.get("remarks")),
        "status": "",
        "stage": s(r.get("stage")) or "New Lead",
        "ticket_value": 0,
    }


def map_lead(r):
    nm = s(r.get("name"))
    if not nm:
        return None
    return {
        "date": date(r.get("intake_date")),
        "name": nm,
        "phone": phone(r.get("phone")),
        "source": s(r.get("source")) or "Walk-in",
        "stage": s(r.get("stage")) or "New",
        "follow_up_date": date(r.get("next_action_date")),
        "remarks": s(r.get("remarks")),
        "assigned_to": s(r.get("owner")),
        "value": 0,
    }


def map_architect(r):
    nm = s(r.get("name"))
    if not nm:
        return None
    return {
        "name": nm,
        "firm": s(r.get("firm")),
        "type": s(r.get("type")) or "Architect",
        "location": s(r.get("loc")) or s(r.get("location")),
        "phone": phone(r.get("phone")),
        "last_contact": date(r.get("last_contact")),
        "visited": s(r.get("visited")).lower() in ("y", "yes", "true", "1"),
        "assigned_to": s(r.get("assigned")),
        "remarks": s(r.get("remarks")),
    }


JOBS = [
    # (sheet,            collection,   mapper,         natural key fields)
    ("Quotes_2026",      "quotes",     map_quote,      ("quote_no",)),
    ("Sales_Register",   "sales",      map_sale,       ("sale_no",)),
    ("Visitors",         "visitors",   map_visitor,    ("name", "phone", "date")),
    ("Leads",            "leads",      map_lead,       ("name", "phone", "date")),
    ("Architects",       "architects", map_architect,  ("name",)),
]


async def main(dry: bool):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20000)[
        os.environ.get("DB_NAME", "madio_crm")
    ]
    await db.client.admin.command("ping")
    print(("DRY RUN — nothing will be written\n" if dry else "WRITING to Atlas\n"))

    for sheet, coll, mapper, keyf in JOBS:
        try:
            rows = fetch(sheet)
        except Exception as e:
            print(f"  {coll:<11} FETCH FAILED {type(e).__name__}: {str(e)[:60]}")
            continue

        docs, skipped = [], 0
        for r in rows:
            d = mapper(r)
            if d is None:
                skipped += 1
                continue
            docs.append(d)

        before = await db[coll].count_documents({})
        ins = upd = 0
        if not dry:
            for d in docs:
                q = {k: d.get(k, "") for k in keyf}
                existing = await db[coll].find_one(q, {"_id": 1})
                if existing:
                    await db[coll].update_one({"_id": existing["_id"]}, {"$set": d})
                    upd += 1
                else:
                    d = {"id": new_id(), **d, "created_at": now_iso()}
                    await db[coll].insert_one(d)
                    ins += 1
        after = await db[coll].count_documents({})
        print(
            f"  {coll:<11} sheet={len(rows):<5} mapped={len(docs):<5} "
            f"skipped={skipped:<4} inserted={ins:<5} updated={upd:<5} "
            f"total {before} -> {after}"
        )


if __name__ == "__main__":
    asyncio.run(main("--dry-run" in sys.argv))
