"""One connected record graph: customer and project links on every record.

Every business record answers "who is this for?" with `customer_id` and,
where it applies, "which project?" with `project_id`. This module is the
single place that keeps those links right:

* ``link(db, collection, doc, user, existing)`` runs on every create/update
  (make_crud and the conversion routes call it). It walks the chain the
  record already points at — payment → order → quotation → project →
  customer — fills the links that are missing, refuses a contradiction
  (a quotation for one customer pointing at another customer's project),
  and fills the record's display copies of the customer's name and phone
  from the customer record.
* ``propagate_customer(db, customer, user)`` runs after a customer is
  edited: LIVE copies (lead, visitor, project, meeting, call, task, survey)
  follow the customer; SNAPSHOTS on issued documents (quotation, order,
  invoice, payment) keep what was issued.
* ``backfill(db, user)`` links existing data once: by conversion chain and
  by phone (only when exactly one customer has that number), creating
  Prospect customers for enquiries whose phone has none. It only fills empty
  links, so running it twice changes nothing.

The display copies (`customer` / `name` / `phone` on a record) stay because
PDFs, WhatsApp buttons, Tally and every list read them; the server writes
them from the customer record, so they are a cache of the master, never a
second place to type it.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import tenancy
from models import new_id, now_iso


class RelationError(ValueError):
    """A record points at two things that don't belong together."""


# collection -> (name field, phone field, live?)
# live = a copy that follows the customer record; otherwise a snapshot of
# what the document said when it was issued (filled only when empty).
DISPLAY = {
    "leads": ("name", "phone", True),
    "visitors": ("name", "phone", True),
    "projects": ("customer", "phone", True),
    "meets": ("with_person", None, True),
    "calls": ("name", "phone", True),
    "tasks": ("linked_entity_name", None, True),
    "dw_surveys": ("customer", "phone", True),
    "site_surveys": (None, None, True),
    "service_tickets": (None, None, True),
    "quotes": ("customer", "phone", False),
    "sales": ("customer", "phone", False),
    "invoices": ("customer", "phone", False),
    "payments": (None, "phone", False),
    "manufacturer_orders": (None, None, True),
    "purchase_orders": (None, None, True),
}
LINKED = set(DISPLAY)
# A new record of these kinds for someone not yet in the CRM creates them as
# a Prospect customer (name + phone are enough).
CREATES_CUSTOMER = {"leads", "quotes", "projects"}
# Collections whose records also carry project_id.
HAS_PROJECT = {"meets", "tasks", "quotes", "sales", "invoices", "payments", "dw_surveys",
               "site_surveys", "service_tickets", "manufacturer_orders", "purchase_orders", "leads", "calls"}


def norm_phone(value: Any) -> str:
    """Last ten digits — the part that identifies an Indian mobile whatever
    prefix (+91, 0, spaces) was typed."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else ""


async def _one(db, coll: str, rid: str, user: dict, fields: dict) -> Optional[dict]:
    if not rid:
        return None
    return await db[coll].find_one(tenancy.scope({"id": rid}, coll, user), {"_id": 0, **fields})


async def customer_by_phone(db, phone: Any, user: dict) -> Optional[dict]:
    """The one customer with this number, or None (none, or more than one)."""
    p = norm_phone(phone)
    if not p:
        return None
    rows = await db.customers.find(
        tenancy.scope({"phone": {"$regex": re.escape(p) + "$"}}, "customers", user),
        {"_id": 0, "id": 1, "name": 1, "phone": 1}).to_list(3)
    return rows[0] if len(rows) == 1 else None


def _set(doc: dict, key: str, value: Any, existing: Optional[dict], label: str):
    """Fill a link, or refuse when the record already points elsewhere."""
    if not value:
        return
    have = doc.get(key) if doc.get(key) not in (None, "") else (existing or {}).get(key)
    if have and have != value:
        raise RelationError(label)
    if not doc.get(key):
        doc[key] = value


async def link(db, collection: str, doc: dict, user: dict, existing: Optional[dict] = None) -> dict:
    """Resolve and fill `customer_id` / `project_id` (and the chain links) on
    a record about to be saved. `doc` is the payload (whole doc on create,
    the changed fields on update); `existing` the stored record on update."""
    if collection not in LINKED:
        return doc
    if existing is not None and doc.get("customer_id") in (None, "") and existing.get("customer_id"):
        # Edit forms resend every field; a blank one never unlinks the customer.
        doc.pop("customer_id", None)
    cur = {**(existing or {}), **{k: v for k, v in doc.items() if v not in (None, "")}}
    if "project_id" in doc and doc["project_id"] in (None, ""):
        cur.pop("project_id", None)          # "no particular project" unlinks it

    # Walk up the chain: payment → order → quotation → project → customer.
    sale_id = cur.get("sale_id") or cur.get("against_sale_id")
    if sale_id:
        sale = await _one(db, "sales", sale_id, user, {"customer_id": 1, "project_id": 1, "quote_id": 1})
        if sale:
            if collection == "invoices" and not cur.get("quote_id"):
                doc["quote_id"] = sale.get("quote_id") or ""
            if collection in HAS_PROJECT:
                _set(doc, "project_id", sale.get("project_id"), existing, "This order belongs to a different project")
            _set(doc, "customer_id", sale.get("customer_id"), existing, "This order belongs to a different customer")
            cur = {**cur, **{k: v for k, v in doc.items() if v not in (None, "")}}
    if cur.get("quote_id") and collection != "quotes":
        quote = await _one(db, "quotes", cur["quote_id"], user, {"customer_id": 1, "project_id": 1})
        if quote:
            if collection in HAS_PROJECT and collection != "projects":
                _set(doc, "project_id", quote.get("project_id"), existing,
                     "This quotation belongs to a different project")
            _set(doc, "customer_id", quote.get("customer_id"), existing,
                 "This quotation belongs to a different customer")
            cur = {**cur, **{k: v for k, v in doc.items() if v not in (None, "")}}
    if cur.get("project_id") and collection != "projects":
        project = await _one(db, "projects", cur["project_id"], user, {"customer_id": 1})
        if project is None:
            raise RelationError("The selected project doesn't exist")
        _set(doc, "customer_id", project.get("customer_id"), existing,
             "The selected project belongs to a different customer")
        cur = {**cur, **{k: v for k, v in doc.items() if v not in (None, "")}}
    if cur.get("lead_id") and collection not in ("leads",):
        lead = await _one(db, "leads", cur["lead_id"], user, {"customer_id": 1})
        if lead and lead.get("customer_id") and not cur.get("customer_id"):
            doc["customer_id"] = lead["customer_id"]
            cur["customer_id"] = lead["customer_id"]

    name_f, phone_f, live = DISPLAY[collection]
    # No link yet: a typed phone that belongs to exactly one customer links it.
    if not cur.get("customer_id") and phone_f and doc.get(phone_f):
        match = await customer_by_phone(db, doc.get(phone_f), user)
        if match:
            doc["customer_id"] = match["id"]
            cur["customer_id"] = match["id"]

    cid = cur.get("customer_id")
    if not cid and existing is None and collection in CREATES_CUSTOMER:
        # A new enquiry, quotation or project for someone not yet in the CRM:
        # they become a (Prospect) customer here, once, instead of living only
        # as typed text on this record.
        name = str(doc.get(name_f) or "").strip()
        phone = norm_phone(doc.get(phone_f)) if phone_f else ""
        if name and phone:
            new = {"id": new_id(), "created_at": now_iso(), "name": name, "phone": phone,
                   "email": doc.get("email") or "", "address": doc.get("location") or doc.get("site_address") or "",
                   "division": doc.get("division") or "Furniture", "stage": "Prospect",
                   "source": f"created from a new {collection[:-1]}"}
            await assign_code(db, new, user)
            tenancy.stamp(new, "customers", user)
            try:
                await db.customers.insert_one(dict(new))
                cid = doc["customer_id"] = new["id"]
            except Exception:                 # raced with another save of the same phone
                match = await customer_by_phone(db, phone, user)
                cid = doc["customer_id"] = (match or {}).get("id", "")
    if not cid:
        return doc
    customer = await _one(db, "customers", cid, user, {"name": 1, "phone": 1, "address": 1})
    if customer is None:
        raise RelationError("The selected customer doesn't exist")
    linked_now = bool(doc.get("customer_id")) and doc.get("customer_id") != (existing or {}).get("customer_id")
    for field, value in ((name_f, customer.get("name")), (phone_f, customer.get("phone"))):
        if not field or not value:
            continue
        if live or linked_now or not cur.get(field):
            # Live copies follow the customer; a document gets the customer's
            # details when it is first linked, and keeps them after that.
            if collection in ("meets", "tasks") and cur.get(field):
                continue                     # a meeting's "with" may name someone else at the customer
            doc[field] = value
    return doc


async def propagate_customer(db, customer: dict, user: dict) -> dict:
    """Push a customer's current name and phone to every LIVE copy. Issued
    documents (quotations, orders, invoices, payments) keep their snapshot."""
    counts = {}
    for coll, (name_f, phone_f, live) in DISPLAY.items():
        if not live:
            continue
        patch = {}
        if name_f and customer.get("name") and coll not in ("meets", "tasks"):
            patch[name_f] = customer["name"]
        if phone_f and customer.get("phone"):
            patch[phone_f] = customer["phone"]
        if not patch:
            continue
        res = await db[coll].update_many(tenancy.scope({"customer_id": customer["id"]}, coll, user),
                                         {"$set": patch})
        if res.modified_count:
            counts[coll] = res.modified_count
    return counts


# ── one-time linking of existing data ─────────────────────────────────────
PHONE_LINKED = ("visitors", "leads", "quotes", "sales", "projects", "calls", "invoices", "dw_surveys",
                "payments")


async def _next_code(db, user: dict) -> int:
    rows = await db.customers.find(tenancy.scope({"code": {"$regex": "^C-"}}, "customers", user),
                                   {"_id": 0, "code": 1}).to_list(100000)
    nums = [int(m.group(1)) for r in rows for m in [re.match(r"C-(\d+)$", r.get("code") or "")] if m]
    return max(nums or [0]) + 1


async def assign_code(db, doc: dict, user: dict) -> None:
    """Short customer number people can quote and search ("C-0042")."""
    if not doc.get("code"):
        doc["code"] = f"C-{await _next_code(db, user):04d}"


async def backfill(db, user: dict, *, create_prospects: bool = True) -> dict:
    """Link existing records. Additive: only empty links are filled; names
    and phones on documents are left as they are."""
    report: dict[str, int] = {}

    def bump(key, n=1):
        if n:
            report[key] = report.get(key, 0) + n

    customers = await db.customers.find(tenancy.scope({}, "customers", user), {"_id": 0}).to_list(100000)
    # Customer numbers for everyone, oldest first.
    nxt = await _next_code(db, user)
    for c in sorted(customers, key=lambda c: str(c.get("created_at") or "")):
        if not c.get("code"):
            c["code"] = f"C-{nxt:04d}"
            nxt += 1
            await db.customers.update_one(tenancy.scope({"id": c["id"]}, "customers", user),
                                          {"$set": {"code": c["code"]}})
            bump("customer numbers assigned")
    by_phone: dict[str, list] = {}
    for c in customers:
        p = norm_phone(c.get("phone"))
        if p:
            by_phone.setdefault(p, []).append(c)

    # Prospect customers for enquiries (leads, quotations) whose phone has none.
    if create_prospects:
        seen: dict[str, dict] = {}
        for coll, name_f in (("leads", "name"), ("quotes", "customer")):
            async for r in db[coll].find(tenancy.scope({"customer_id": {"$in": [None, ""]}}, coll, user),
                                         {"_id": 0, "phone": 1, name_f: 1, "email": 1, "division": 1,
                                          "location": 1, "date": 1}):
                p = norm_phone(r.get("phone"))
                name = str(r.get(name_f) or "").strip()
                if not p or not name or p in by_phone:
                    continue
                prev = seen.get(p)
                if prev is None or str(r.get("date") or "") > prev["_date"]:
                    seen[p] = {"name": name, "phone": p, "email": r.get("email") or "",
                               "address": r.get("location") or "", "division": r.get("division") or "Furniture",
                               "_date": str(r.get("date") or "")}
        for p, s in sorted(seen.items(), key=lambda kv: kv[1]["_date"]):
            doc = {"id": new_id(), "created_at": now_iso(), "name": s["name"], "phone": p,
                   "email": s["email"], "address": s["address"], "division": s["division"],
                   "stage": "Prospect", "source": "linked from enquiries", "code": f"C-{nxt:04d}"}
            nxt += 1
            tenancy.stamp(doc, "customers", user)
            await db.customers.insert_one(dict(doc))
            by_phone[p] = [doc]
            bump("prospect customers created")

    # Link by conversion chain first (exact), then by phone (unique match only).
    async for p in db.projects.find(tenancy.scope({}, "projects", user), {"_id": 0, "id": 1, "sale_id": 1,
                                                                          "quote_id": 1, "customer_id": 1}):
        if p.get("sale_id"):
            r = await db.sales.update_one(tenancy.scope({"id": p["sale_id"], "project_id": {"$in": [None, ""]}},
                                                        "sales", user), {"$set": {"project_id": p["id"]}})
            bump("orders linked to their project", r.modified_count)
        if p.get("quote_id"):
            r = await db.quotes.update_one(tenancy.scope({"id": p["quote_id"], "project_id": {"$in": [None, ""]}},
                                                         "quotes", user), {"$set": {"project_id": p["id"]}})
            bump("quotations linked to their project", r.modified_count)
    for coll in PHONE_LINKED:
        _, phone_f, _ = DISPLAY[coll]
        async for r in db[coll].find(tenancy.scope({"customer_id": {"$in": [None, ""]}}, coll, user),
                                     {"_id": 0, "id": 1, phone_f: 1, "quote_id": 1, "sale_id": 1,
                                      "against_sale_id": 1}):
            cid = ""
            for key, src in (("quote_id", "quotes"), ("sale_id", "sales"), ("against_sale_id", "sales")):
                if r.get(key) and not cid:
                    up = await db[src].find_one(tenancy.scope({"id": r[key]}, src, user), {"_id": 0, "customer_id": 1})
                    cid = (up or {}).get("customer_id") or ""
            if not cid:
                hits = by_phone.get(norm_phone(r.get(phone_f)), [])
                cid = hits[0]["id"] if len(hits) == 1 else ""
            if cid:
                await db[coll].update_one(tenancy.scope({"id": r["id"]}, coll, user), {"$set": {"customer_id": cid}})
                bump(f"{coll} linked to a customer")
    # Records that hang off a project take its customer.
    for coll in ("meets", "tasks", "manufacturer_orders", "purchase_orders", "service_tickets", "site_surveys",
                 "projects"):
        q = {"customer_id": {"$in": [None, ""]}}
        if coll == "tasks":
            q["ref_type"] = "project"
        async for r in db[coll].find(tenancy.scope(q, coll, user), {"_id": 0, "id": 1, "project_id": 1, "ref": 1,
                                                                    "sale_id": 1, "quote_id": 1}):
            pid = r.get("project_id") or (r.get("ref") if coll == "tasks" else "")
            cid = ""
            if coll == "projects":
                for key, src in (("sale_id", "sales"), ("quote_id", "quotes")):
                    if r.get(key) and not cid:
                        up = await db[src].find_one(tenancy.scope({"id": r[key]}, src, user), {"_id": 0, "customer_id": 1})
                        cid = (up or {}).get("customer_id") or ""
            elif pid:
                proj = await db.projects.find_one(tenancy.scope({"id": pid}, "projects", user), {"_id": 0, "customer_id": 1})
                cid = (proj or {}).get("customer_id") or ""
            if cid:
                patch = {"customer_id": cid}
                if coll == "tasks" and not r.get("project_id"):
                    patch["project_id"] = pid
                await db[coll].update_one(tenancy.scope({"id": r["id"]}, coll, user), {"$set": patch})
                bump(f"{coll} linked to a customer")
    # Orders and quotations take their project's / quotation's customer when
    # still missing (the chain is exact where the phone was blank).
    for coll, up_key, up_coll in (("sales", "quote_id", "quotes"), ("quotes", "project_id", "projects")):
        async for r in db[coll].find(tenancy.scope({"customer_id": {"$in": [None, ""]},
                                                    up_key: {"$nin": [None, ""]}}, coll, user),
                                     {"_id": 0, "id": 1, up_key: 1}):
            up = await db[up_coll].find_one(tenancy.scope({"id": r[up_key]}, up_coll, user), {"_id": 0, "customer_id": 1})
            if (up or {}).get("customer_id"):
                await db[coll].update_one(tenancy.scope({"id": r["id"]}, coll, user),
                                          {"$set": {"customer_id": up["customer_id"]}})
                bump(f"{coll} linked to a customer")
    # Activities carry the links too, so a timeline is one query.
    for coll, entity in (("leads", "lead"), ("quotes", "quote"), ("sales", "sale"), ("projects", "project")):
        async for r in db[coll].find(tenancy.scope({"customer_id": {"$nin": [None, ""]}}, coll, user),
                                     {"_id": 0, "id": 1, "customer_id": 1, "project_id": 1}):
            patch = {"customer_id": r["customer_id"]}
            if r.get("project_id") or coll == "projects":
                patch["project_id"] = r.get("project_id") or r["id"]
            await db.activities.update_many(tenancy.scope({"entity": entity, "entity_id": r["id"],
                                                           "customer_id": {"$in": [None, ""]}}, "activities", user),
                                            {"$set": patch})
    return report
