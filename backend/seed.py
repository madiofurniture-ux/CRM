"""Seed real sample data on startup."""
import json
import os
import random
import re
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta

from auth import hash_pin
from models import now_iso, new_id, GST_DEFAULT

DATA_DIR = Path(__file__).parent / "data"


# ── Logins are ROLES, not people ──────────────────────────────────────────
# Staff share a role login, so someone joining or leaving never means editing
# users. Names appear on records (via "attend person" / owner fields), not here.
#
# PINs are NEVER hardcoded — this file is in a public repo, and a committed PIN
# is the same as no PIN at all. Supply them at deploy time:
#
#     SEED_PINS=Promoter:8471,Admin:2093,MF:5510,MAP:6624,MDW:7735,Accounting:3348,Reception:9902
#
# Anything not supplied gets a random 4-digit PIN, printed ONCE to the server log
# at first startup so an admin can hand it out and then change it in Role Manager.

_SALES_PAGES = ["dashboard", "alerts", "pipeline", "quotes", "sales", "visitors",
                "leads", "architects", "inventory", "inv-analytics", "projects",
                "meetplan", "tasks", "attendance", "reports"]

# NOTE: /auth/login does username.lower(), so the stored username MUST be
# lowercase or the lookup never matches. `name` is what the login screen shows.
SEED_ROLES = [
    # username     display       icon  colour     pages (None = full admin)
    ("promoter",   "Promoter",   "PR", "#1A1D1A", None),
    ("admin",      "Admin",      "AD", "#3A3F3A", None),
    ("mf",         "MF",         "MF", "#C85A32", _SALES_PAGES),
    ("map",        "MAP",        "MP", "#D48B30", _SALES_PAGES + ["dwsurvey"]),
    ("mdw",        "MDW",        "DW", "#4A5D4E", _SALES_PAGES + ["dwsurvey"]),
    ("accounting", "Accounting", "AC", "#2F5D7C",
     ["dashboard", "alerts", "sales", "outstanding", "invoice-gen", "petty",
      "reports", "tasks", "data-centre", "inventory", "inv-analytics"]),
    ("reception",  "Reception",  "RC", "#7C5D9C",
     ["dashboard", "visitors", "leads", "meetplan", "tasks", "attendance"]),
]


def _seed_pins() -> dict:
    """PINs from the SEED_PINS env var; the rest are random and logged once."""
    supplied = {}
    raw = os.environ.get("SEED_PINS", "")
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            k, v = k.strip(), v.strip()
            if k and v.isdigit():
                supplied[k.lower()] = v
    out, generated = {}, []
    for username, *_ in SEED_ROLES:
        pin = supplied.get(username.lower())
        if not pin:
            pin = f"{secrets.randbelow(9000) + 1000}"
            generated.append(f"{username}={pin}")
        out[username] = pin
    if generated:
        print("=" * 64)
        print("MADIO CRM — generated PINs for roles with no SEED_PINS entry.")
        print("Shown ONCE. Change them in Admin > Role Manager after first login.")
        print("   " + "   ".join(generated))
        print("=" * 64)
    return out


def _seed_role(username: str, pages) -> str:
    # "accountant" is a distinct role (not just "user") so it can be granted
    # access to vendor names — see server.py's _can_see_vendor_names.
    if pages is None:
        return "admin"
    if username == "accounting":
        return "accountant"
    return "user"


SEED_USERS = [
    {"username": u, "name": name, "pin": "", "role": _seed_role(u, pages),
     "icon": icon, "color": colour, "pages": pages}
    for (u, name, icon, colour, pages) in SEED_ROLES
]


# Pipeline stages
STAGES = ["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"]
DIVISIONS = ["Furniture", "MAP", "D&W"]


def _parse_date(s):
    """Best-effort date parser for messy CSV data. Returns ISO date string."""
    if not s or s in ("-", "?", ""):
        return datetime.now(timezone.utc).date().isoformat()
    s = str(s).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            continue
    return datetime.now(timezone.utc).date().isoformat()


def _norm_phone(p):
    if not p:
        return ""
    p = str(p).strip()
    if p in ("-", "?", "nan", "None"):
        return ""
    return p


async def seed_users(db):
    pins = _seed_pins()
    for u in SEED_USERS:
        existing = await db.users.find_one({"username": u["username"]})
        if existing:
            if u["pages"] is not None:
                await db.users.update_one({"username": u["username"]}, {"$addToSet": {"pages": {"$each": ["projects", "attendance"]}}})
            continue
        doc = {
            "id": new_id(),
            "username": u["username"],
            "name": u["name"],
            "pin_hash": hash_pin(pins[u["username"]]),
            "role": u["role"],
            "icon": u["icon"],
            "color": u["color"],
            "pages": u["pages"],
            "created_at": now_iso(),
        }
        await db.users.insert_one(doc)



async def seed_visitors(db):
    if await db.visitors.count_documents({}) > 0:
        return
    # Inline sample from user's CSV (representative slice covering the data shape)
    raw = [
        {"date": "9-7-2024", "name": "Nakul", "ref": "Gowtham Hive", "phone": "-", "req": "Sofa", "by": "Nenmu", "remarks": "Will be visiting again", "status": None},
        {"date": "9-7-2024", "name": "Rama Raju & Bheema Ram", "ref": "Gowtham Hive", "phone": "-", "req": "Sofa & Cots", "by": "Gowtham Hive", "remarks": "Will be visiting again", "status": None},
        {"date": "20-7-2024", "name": "Sudheer - Jubleehills", "ref": "Kiran MF", "phone": "-", "req": "Sofa & Cots", "by": "Nenmu", "remarks": "Have to give quotations", "status": None},
        {"date": "21-7-2024", "name": "Dr K Srikanth Panjagutta", "ref": "Ar Ravindra SR associates", "phone": "-", "req": "Sofa", "by": "Raghu MF", "remarks": "Site visit pending", "status": None},
        {"date": "21-7-2024", "name": "Anil Athena, Shaikpet", "ref": "Raghu MF", "phone": "9949012342", "req": "Dining table & Dining chair", "by": "Raghu MF", "remarks": "4 chairs pending", "status": "Delivered"},
        {"date": "22-7-2024", "name": "Raghu Babu", "ref": "Gowtham Hive", "phone": "-", "req": "Sofa", "by": "Gowtham Hive", "remarks": "Walk-in", "status": None},
        {"date": "26-7-2024", "name": "Shweta Viswa interiors", "ref": "Kiran Sir", "phone": "-", "req": "Bulk order", "by": "Kiran Sir", "remarks": "Designer firm", "status": None},
        {"date": "29-7-2024", "name": "Ar Sirisha, Kollur", "ref": "Raghu MF", "phone": "9908212134", "req": "Madio Acrylic Paint", "by": "Raghu MF", "remarks": "Waiting for confirmation", "status": None},
        {"date": "29-7-2024", "name": "Ar Sirisha, Kollur", "ref": "Raghu MF", "phone": "9908212134", "req": "Bedsheets & Pillows", "by": "Raghu MF", "remarks": "Waiting for confirmation", "status": None},
        {"date": "30-7-2024", "name": "Mr Sumanth", "ref": "Gowtham Hive", "phone": "9739602097", "req": "Sofa & Leisure chair", "by": "Nenmu", "remarks": "Amount received", "status": "Delivered"},
        {"date": "31-7-2024", "name": "Anja Reddy", "ref": "Gowtham Hive", "phone": "7022830867", "req": "Cots & Dining Table", "by": "Gowtham Hive", "remarks": "Will be visiting again", "status": None},
        {"date": "01-08-2024", "name": "Uma - Villa 64, Kollur", "ref": "Ar Sirisha", "phone": "-", "req": "Cots & Sofa", "by": "Raghu MF", "remarks": "Will be visiting again", "status": None},
        {"date": "14-08-2024", "name": "Ar Jeevan", "ref": "Raghu MF", "phone": "9985556181", "req": "Sofa & Carpets", "by": "Nenmu", "remarks": "Will be visiting again", "status": None},
        {"date": "15-08-2024", "name": "Anja Reddy", "ref": "Gowtham Hive", "phone": "7022830867", "req": "Cots, Dining Table & Chair", "by": "Nenmu", "remarks": "Waiting for confirmation", "status": "Quoted"},
        {"date": "17-08-2024", "name": "Arjun Rao - Kukatpally", "ref": "Sharath PNR", "phone": "9000123456", "req": "Sofa & Dining Chairs", "by": "Raghu MF", "remarks": "Site visit scheduled", "status": "Qualified"},
        {"date": "18-08-2024", "name": "Vasanta Laxmi", "ref": "Gowtham Hive", "phone": "9110556817", "req": "Wardrobes, Sofa, Dining table & chair", "by": "Raghu MF", "remarks": "Bulk requirement", "status": "Quoted"},
        {"date": "18-08-2024", "name": "Rajababu", "ref": "Viswa interiors", "phone": "7995565101", "req": "Sofa, Dining table & chair", "by": "Raghu MF", "remarks": "Designer reference", "status": "Negotiation"},
        {"date": "27-08-2024", "name": "Sumanth Tirupati", "ref": "Naveen Smiley", "phone": "8220637727", "req": "MAP", "by": "Raghu MF", "remarks": "Paint sample requested", "status": "Quoted"},
        {"date": "10-09-2024", "name": "Priya", "ref": "Gowtham Hive", "phone": "9988776655", "req": "Sofas", "by": "Nenmu", "remarks": "Will be visiting again", "status": None},
        {"date": "15-09-2024", "name": "Krishna Reddy - Banjara Hills", "ref": "Ar Ravindra", "phone": "9876543210", "req": "Complete villa fit-out", "by": "Raghu MF", "remarks": "High-value lead", "status": "Negotiation"},
        {"date": "20-09-2024", "name": "Mahesh Industries", "ref": "Walk-in", "phone": "9123456789", "req": "Office furniture - bulk", "by": "Gowtham Hive", "remarks": "Asked for catalogue", "status": "Qualified"},
        {"date": "25-09-2024", "name": "Lakshmi Devi", "ref": "Kiran Sir", "phone": "9234567890", "req": "Cots & Wardrobes", "by": "Nenmu", "remarks": "Quote sent", "status": "Quoted"},
        {"date": "01-10-2024", "name": "Ar Manoj - Hi-Tech City", "ref": "Sharath PNR", "phone": "9345678901", "req": "MAP for villa project", "by": "Raghu MF", "remarks": "Sample approved", "status": "Won"},
        {"date": "05-10-2024", "name": "Sanjay Builders", "ref": "Architect referral", "phone": "9456789012", "req": "Doors & Windows", "by": "Gowtham Hive", "remarks": "Site survey done", "status": "Qualified"},
        {"date": "10-10-2024", "name": "Ramesh - Madhapur", "ref": "Gowtham Hive", "phone": "9567890123", "req": "Sofa - leather", "by": "Nenmu", "remarks": "Color samples shared", "status": "Negotiation"},
    ]
    docs = []
    for i, r in enumerate(raw, start=1):
        st = r.get("status") or random.choice(["New", "Qualified", "Quoted", "Negotiation"])
        docs.append({
            "id": new_id(),
            "date": _parse_date(r["date"]),
            "name": r["name"],
            "location": "",
            "reference": r["ref"],
            "phone": _norm_phone(r["phone"]),
            "requirement": r["req"],
            "attend_person": r["by"],
            "site_visit": "",
            "remarks": r["remarks"],
            "status": st,
            "stage": st,
            "ticket_value": float(random.choice([45000, 80000, 120000, 250000, 350000])),
            "created_at": now_iso(),
        })
    if docs:
        await db.visitors.insert_many(docs)


async def seed_inventory(db):
    if await db.inventory.count_documents({}) > 0:
        return
    path = DATA_DIR / "inventory.json"
    if not path.exists():
        return
    items = json.loads(path.read_text(encoding="utf-8"))
    docs = []

    # NEW FORMAT (built by tools/build_inventory_seed.py from the audited catalogue):
    # records already carry the real MF-### business key, true location, and a
    # same-origin product photo. Pass them through instead of fabricating values.
    # The old branch below stays for the legacy raw-Excel dump.
    if items and isinstance(items[0], dict) and "sku" in items[0]:
        for it in items:
            name = (it.get("name") or "").strip()
            sku = (it.get("sku") or "").strip()
            if not name or not sku:
                continue
            docs.append({
                "id": new_id(),
                "sku": sku,
                "name": name,
                "category": (it.get("category") or "").strip() or "General",
                "vendor": (it.get("vendor") or "").strip(),
                "model_no": (it.get("model_no") or "").strip(),
                "qty": int(float(it.get("qty") or 1)),
                "cost": float(it.get("cost") or 0),
                "mrp": float(it.get("mrp") or 0),
                "margin": float(it.get("margin") or 0),
                "status": (it.get("status") or "In Stock").strip(),
                "location": (it.get("location") or "Warehouse").strip(),
                "image_url": (it.get("image_url") or "").strip(),
                "date_added": (it.get("date_added") or ""),
                "created_at": now_iso(),
            })
        if docs:
            await db.inventory.insert_many(docs)
        return

    for idx, it in enumerate(items, start=1):
        name = (it.get("PRODUCT") or "").strip()
        if not name:
            continue
        vendor = (it.get("VENDOR") or "").strip()
        model = (it.get("MODEL NO") or "").strip()
        try:
            qty = int(float(it.get("QTY") or 1))
        except Exception:
            qty = 1
        try:
            cost = float(it.get("Purchase Cost") or 0)
        except Exception:
            cost = 0
        try:
            mrp = float(it.get("Selling Price") or 0)
        except Exception:
            mrp = 0
        margin = round(((mrp - cost) / cost * 100), 2) if cost > 0 else 0
        status = (it.get("Status") or "In Stock").strip()
        if status not in ("In Stock", "Display", "Sold", "Missing", "Reserved"):
            status = "Display" if "Display" in status else "In Stock"

        images_pool = [
            "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800&auto=format&fit=crop&q=60", # Sofa
            "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800&auto=format&fit=crop&q=60", # Armchair
            "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=800&auto=format&fit=crop&q=60", # Interior Lounge
            "https://images.unsplash.com/photo-1538688525198-9b88f6f53126?w=800&auto=format&fit=crop&q=60", # Modern Chair
            "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=800&auto=format&fit=crop&q=60", # Living Room
            "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800&auto=format&fit=crop&q=60", # Bed / Bedroom
            "https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=800&auto=format&fit=crop&q=60", # Modern Table
            "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800&auto=format&fit=crop&q=60", # Villa Woodwork
            "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92?w=800&auto=format&fit=crop&q=60", # Minimal Decor
            "https://images.unsplash.com/photo-1567538096630-e0c55bd6374c?w=800&auto=format&fit=crop&q=60", # Dining Set
        ]

        docs.append({
            "id": new_id(),
            "sku": f"MAD-{idx:04d}",
            "name": name,
            "category": model or "General",
            "vendor": vendor,
            "model_no": model,
            "qty": qty,
            "cost": cost,
            "mrp": mrp,
            "margin": margin,
            "status": status,
            "location": random.choice(["Showroom Floor", "Warehouse A", "Warehouse B", "Display Area"]),
            "image_url": images_pool[(idx - 1) % len(images_pool)],
            "created_at": now_iso(),
        })
    if docs:
        await db.inventory.insert_many(docs)


async def seed_vendors(db):
    """Vendor codes are assigned once and never reassigned — safe to call every
    startup (only adds names not already present). Names come from two
    sources: data/vendors.json (seeded first, so its order sets the low
    codes), then any distinct `vendor` string already sitting on an inventory
    item that isn't covered yet — the curated JSON list turned out to be a
    stale subset of what the real seeded inventory actually uses. Also
    backfills vendor_id/vendor_code onto any inventory item whose free-text
    `vendor` name matches a vendor here but has no link yet — additive only,
    the item's own `vendor` text is never touched or removed.
    """
    path = DATA_DIR / "vendors.json"
    names = []
    if path.exists():
        try:
            names = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            names = []

    existing = await db.vendors.find({}, {"_id": 0}).to_list(5000)
    covered = {str(n or "").strip().lower() for n in names} | {
        (v.get("name") or "").strip().lower() for v in existing
    }
    inventory_vendors = await db.inventory.distinct("vendor")
    for v in sorted(str(n or "").strip() for n in inventory_vendors):
        if v and v.lower() not in covered:
            names.append(v)
            covered.add(v.lower())

    by_name = {(v.get("name") or "").strip().lower(): v for v in existing}
    top = 0
    for v in existing:
        m = re.search(r"(\d+)\s*$", str(v.get("code") or ""))
        if m:
            top = max(top, int(m.group(1)))

    added = []
    for raw in names:
        name = str(raw or "").strip()
        if not name or name.lower() in by_name:
            continue
        top += 1
        doc = {"id": new_id(), "name": name, "code": f"VEN-{top:03d}", "created_at": now_iso()}
        added.append(doc)
        by_name[name.lower()] = doc
    if added:
        await db.vendors.insert_many(added)

    unlinked = db.inventory.find(
        {"vendor": {"$nin": ["", None]},
         "$or": [{"vendor_id": {"$exists": False}}, {"vendor_id": ""}]},
        {"_id": 0, "id": 1, "vendor": 1},
    )
    async for item in unlinked:
        v = by_name.get(str(item.get("vendor") or "").strip().lower())
        if v:
            await db.inventory.update_one(
                {"id": item["id"]}, {"$set": {"vendor_id": v["id"], "vendor_code": v["code"]}})


async def seed_sales(db):
    if await db.sales.count_documents({}) > 0:
        return
    path = DATA_DIR / "sales.json"
    if not path.exists():
        return
    raw = json.loads(path.read_text())
    docs = []
    for idx, r in enumerate(raw, start=1):
        cust = (r.get("Cust Name") or "").strip()
        product = (r.get("Product") or "").strip()
        if not cust or not product:
            continue
        try:
            value = float(r.get("Sale price ") or 0)
        except Exception:
            value = 0
        try:
            cost = float(r.get("Purchase Cost") or 0)
        except Exception:
            cost = 0
        paid = round(value * random.choice([1.0, 1.0, 1.0, 0.5, 0.7]), 2)
        balance = round(value - paid, 2)
        sd_raw = r.get("Sale Date") or ""
        sale_date = str(sd_raw)[:10] if sd_raw else datetime.now(timezone.utc).date().isoformat()
        docs.append({
            "id": new_id(),
            "sale_no": f"AF-{idx:04d}",
            "date": sale_date,
            "customer": cust,
            "division": random.choice(DIVISIONS),
            "quote_ref": f"Q-{idx:04d}",
            "by_user": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "value": value,
            "paid": paid,
            "balance": balance,
            "stage": "Delivered" if balance == 0 else "Partial",
            "remarks": product[:80],
            "created_at": now_iso(),
        })
    if docs:
        await db.sales.insert_many(docs)


async def seed_leads(db):
    if await db.leads.count_documents({}) > 0:
        return
    names = ["Priya Nair", "Vikram Singh", "Sneha Patel", "Arjun Kumar", "Divya Reddy",
            "Kiran Rao", "Meera Joshi", "Rohan Mehta", "Sanjana Iyer", "Aditya Rao",
            "Tanvi Kapoor", "Karthik Reddy", "Pooja Sharma", "Naveen Babu", "Anjali Menon"]
    sources = ["Walk-in", "WhatsApp", "Architect Ref", "Instagram", "Site Visit", "Referral"]
    docs = []
    today = datetime.now(timezone.utc).date()
    for i, n in enumerate(names):
        stage = random.choice(["New", "Contacted", "Qualified", "Quoted", "Negotiation", "Won", "Lost"])
        d = today - timedelta(days=random.randint(0, 60))
        fu = today + timedelta(days=random.randint(-3, 14))
        docs.append({
            "id": new_id(),
            "date": d.isoformat(),
            "name": n,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "source": random.choice(sources),
            "stage": stage,
            "follow_up_date": fu.isoformat(),
            "remarks": random.choice(["Interested in living room", "Asked for catalogue", "Site visit pending", "Quotation under review", "Negotiating price", "Wants paint sample"]),
            "assigned_to": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "value": float(random.choice([50000, 120000, 180000, 250000, 450000, 800000])),
            "created_at": now_iso(),
        })
    await db.leads.insert_many(docs)


async def seed_architects(db):
    if await db.architects.count_documents({}) > 0:
        return
    architects = [
        ("Ar Ravindra", "SR Associates", "Architect", "Banjara Hills", "9876543210"),
        ("Ar Sirisha", "Sirisha Designs", "Architect", "Kollur", "9908212134"),
        ("Ar Jeevan", "Jeevan & Co", "Architect", "Hyderabad", "9985556181"),
        ("Sharath PNR", "PNR Interiors", "Designer", "Kukatpally", "9000123456"),
        ("Viswa Interiors", "Viswa Interiors", "Designer", "Madhapur", "7995565101"),
        ("Gowtham Hive", "Hive Studios", "Designer", "Hi-Tech City", "9739602097"),
        ("Naveen Smiley", "Smiley Builders", "Builder", "Tirupati", "8220637727"),
        ("Ar Manoj", "Manoj Architects", "Architect", "Hi-Tech City", "9345678901"),
        ("Kiran MF", "MF Studio", "Designer", "Jubilee Hills", "9876512345"),
        ("Sanjay Builders", "Sanjay Constructions", "Builder", "Gachibowli", "9456789012"),
    ]
    today = datetime.now(timezone.utc).date()
    docs = []
    for n, f, t, l, p in architects:
        docs.append({
            "id": new_id(),
            "name": n, "firm": f, "type": t, "location": l, "phone": p,
            "last_contact": (today - timedelta(days=random.randint(1, 40))).isoformat(),
            "visited": random.choice([True, False]),
            "assigned_to": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "remarks": random.choice(["Regular client", "New connection", "High-value referrer", "Loyal partner", ""]),
            "created_at": now_iso(),
        })
    await db.architects.insert_many(docs)


async def seed_quotes(db):
    if await db.quotes.count_documents({}) > 0:
        return
    customers = [("Krishna Reddy - Banjara Hills", "Ar Ravindra"), ("Mahesh Industries", "Walk-in"),
                 ("Lakshmi Devi", "Kiran Sir"), ("Vasanta Laxmi", "Gowtham Hive"),
                 ("Rajababu", "Viswa interiors"), ("Ar Manoj - Hi-Tech City", "Sharath PNR"),
                 ("Anja Reddy", "Gowtham Hive"), ("Sanjay Builders", "Architect referral"),
                 ("Ramesh - Madhapur", "Gowtham Hive"), ("Sumanth Tirupati", "Naveen Smiley"),
                 ("Arjun Rao - Kukatpally", "Sharath PNR"), ("Anil Athena", "Raghu MF"),
                 ("Dr K Srikanth", "Ar Ravindra"), ("Uma Villa 64", "Ar Sirisha"),
                 ("Ar Jeevan Project", "Raghu MF")]
    today = datetime.now(timezone.utc).date()
    docs = []
    for i, (c, r) in enumerate(customers, start=1):
        stage = random.choice(["New", "Qualified", "Quoted", "Negotiation", "Won", "Lost"])
        value = float(random.choice([85000, 125000, 180000, 245000, 320000, 480000, 750000, 1200000]))
        cash = round(value * random.uniform(0.1, 0.4), 2) if stage in ("Won", "Negotiation") else 0
        bank = round(value * random.uniform(0.3, 0.6), 2) if stage in ("Won", "Negotiation") else 0
        docs.append({
            "id": new_id(),
            "quote_no": f"AF-{i:04d}",
            "date": (today - timedelta(days=random.randint(0, 90))).isoformat(),
            "customer": c,
            "reference": r,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "division": random.choice(DIVISIONS),
            "by_user": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "stage": stage,
            "value": value,
            "cash": cash,
            "bank": bank,
            "mode": random.choice(["Walk-in", "WhatsApp", "Site Visit", "Phone"]),
            "remarks": random.choice(["Furniture set for living room", "Complete interior package", "Paint requirement", "Doors and windows for villa", "Bulk order for office"]),
            "created_at": now_iso(),
        })
    await db.quotes.insert_many(docs)


async def seed_tasks(db):
    if await db.tasks.count_documents({}) > 0:
        return
    titles = [
        ("Follow up with Krishna Reddy on villa quote", "High", "Sales"),
        ("Arrange site visit for Sanjay Builders", "Medium", "Site Visit"),
        ("Send updated catalogue to Ar Manoj", "Low", "Marketing"),
        ("Process pending delivery for Anja Reddy", "High", "Delivery"),
        ("Stock audit for Display Area", "Medium", "Inventory"),
        ("Confirm paint sample with Sumanth Tirupati", "High", "Sales"),
        ("Update price list for Q1", "Low", "Admin"),
        ("Schedule meeting with Ar Sirisha", "Medium", "Sales"),
        ("Reorder sofa fabric from V1", "Medium", "Procurement"),
        ("Prepare invoice for Mahesh Industries", "High", "Finance"),
    ]
    today = datetime.now(timezone.utc).date()
    docs = []
    for i, (t, p, c) in enumerate(titles):
        docs.append({
            "id": new_id(),
            "title": t,
            "priority": p,
            "due_date": (today + timedelta(days=random.randint(-2, 14))).isoformat(),
            "assigned_to": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "category": c,
            "ref": "",
            "notes": "",
            "done": i in (2, 6),
            "created_at": now_iso(),
            "created_by": "admin",
        })
    await db.tasks.insert_many(docs)


async def seed_projects(db):
    if await db.projects.count_documents({}) > 0:
        return
    sample_projects = [
        ("PRJ-0001", "Krishna Reddy", "9876543210", "Furniture", 450000, 200000, "Survey", "Villa 12, Banjara Hills", "Raghu MF", "AF-0001", "Initial site measurement & layout review completed."),
        ("PRJ-0002", "Ar Manoj - Hi-Tech City", "9345678901", "MAP", 280000, 100000, "Quoted", "Plot 45, Hi-Tech City", "Sharath PNR", "AF-0002", "Acrylic paint & texture quote submitted for architect approval."),
        ("PRJ-0003", "Sanjay Builders", "9456789012", "D&W", 850000, 400000, "Execution", "Gachibowli Site A", "Gowtham Hive", "AF-0003", "Window frame installation in progress (Level 2)."),
        ("PRJ-0004", "Mahesh Industries", "9876512345", "Furniture", 520000, 520000, "Review", "IDA Uppal Block 4", "Nenmu", "AF-0004", "Executive office furniture setup under final quality audit."),
        ("PRJ-0005", "Dr K Srikanth", "9908212134", "Furniture", 680000, 680000, "Closure", "Jubilee Hills Rd 36", "Ar Ravindra", "AF-0005", "Project completed, final sign-off & handover done."),
    ]
    today = datetime.now(timezone.utc).date()
    docs = []
    for pno, c, ph, div, val, pd, stg, addr, eng, qref, rem in sample_projects:
        docs.append({
            "id": new_id(),
            "project_no": pno,
            "customer": c,
            "phone": ph,
            "division": div,
            "value": val,
            "paid": pd,
            "stage": stg,
            "site_address": addr,
            "assigned_engineer": eng,
            "start_date": (today - timedelta(days=random.randint(10, 45))).isoformat(),
            "target_date": (today + timedelta(days=random.randint(5, 30))).isoformat(),
            "remarks": rem,
            "quote_ref": qref,
            "created_at": now_iso(),
        })
    await db.projects.insert_many(docs)


async def seed_all(db):
    await seed_users(db)
    await seed_visitors(db)
    await seed_inventory(db)
    await seed_vendors(db)
    await seed_sales(db)
    await seed_leads(db)
    await seed_architects(db)
    await seed_quotes(db)
    await seed_tasks(db)
    await seed_invoices(db)
    await seed_meets(db)
    await seed_petty_cash(db)
    await seed_projects(db)


async def seed_invoices(db):
    if await db.invoices.count_documents({}) > 0:
        return
    customers = [
        ("Krishna Reddy", "Villa 12, Banjara Hills", "36AAACR1234A1Z5"),
        ("Mahesh Industries", "Plot 45, IDA Uppal", "36AABCM5678B2Z8"),
        ("Ar Manoj", "Hi-Tech City, Madhapur", ""),
        ("Anja Reddy", "Kondapur", ""),
        ("Sanjay Builders", "Gachibowli", "36AASCS1122C3Z1"),
    ]
    today = datetime.now(timezone.utc).date()
    docs = []
    for idx, (c, addr, gstin) in enumerate(customers, start=1):
        subtotal = float(random.choice([85000, 145000, 220000, 380000, 520000]))
        tax_pct = GST_DEFAULT
        is_igst = random.choice([False, False, False, True])
        tax_total = subtotal * tax_pct / 100
        cgst = 0 if is_igst else tax_total / 2
        sgst = 0 if is_igst else tax_total / 2
        igst = tax_total if is_igst else 0
        total = subtotal + tax_total
        paid = round(total * random.choice([1.0, 1.0, 0.5, 0.3]), 2)
        line_items = [
            {"sku": f"MAD-{100+i}", "description": random.choice(["3-Seater Sofa - Leather", "Dining Table 6-Seater", "Wardrobe Sliding Door", "MADIO Acrylic Paint 20L", "Teak Wood Door Frame"]),
             "hsn": "9403", "qty": random.randint(1, 4), "rate": round(subtotal / random.randint(2, 4), 2),
             "discount_pct": 0, "tax_pct": tax_pct}
            for i in range(random.randint(2, 4))
        ]
        docs.append({
            "id": new_id(),
            "invoice_no": f"MAD/24-25/{idx:04d}",
            "date": (today - timedelta(days=random.randint(1, 60))).isoformat(),
            "customer": c,
            "billing_address": addr,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "gstin": gstin,
            "place_of_supply": random.choice(["Telangana", "Andhra Pradesh", "Karnataka"]),
            "is_igst": is_igst,
            "line_items": line_items,
            "subtotal": subtotal, "discount_total": 0,
            "cgst": round(cgst, 2), "sgst": round(sgst, 2), "igst": round(igst, 2),
            "total": round(total, 2), "paid": paid, "balance": round(total - paid, 2),
            "by_user": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "status": "Paid" if paid >= total else "Sent",
            "notes": "Thank you for your business. Warranty as per T&C.",
            "created_at": now_iso(),
        })
    await db.invoices.insert_many(docs)


async def seed_meets(db):
    if await db.meets.count_documents({}) > 0:
        return
    today = datetime.now(timezone.utc).date()
    seeds = [
        ("Site visit - Krishna Reddy Villa", 0, "10:00", "11:30", "Banjara Hills", "Krishna Reddy", "Lead", "Krishna Reddy"),
        ("Design review with Ar Manoj", 1, "14:00", "15:30", "Hi-Tech City", "Ar Manoj", "Architect", "Ar Manoj"),
        ("Team standup", 0, "09:30", "09:45", "Showroom", "All", "Internal", ""),
        ("Sample handover - Sumanth", 2, "11:00", "11:30", "Showroom", "Sumanth Tirupati", "Customer", "Sumanth Tirupati"),
        ("Vendor call - Zhi Ran She", 3, "16:00", "16:45", "Zoom", "Vendor", "Internal", ""),
        ("Follow-up call - Mahesh Industries", 4, "10:30", "11:00", "Phone", "Mahesh", "Customer", "Mahesh Industries"),
        ("Site measurement - Sanjay Builders", 5, "08:00", "10:00", "Gachibowli", "Site engineer", "Customer", "Sanjay Builders"),
    ]
    docs = []
    for i, (title, off, st, et, loc, person, rtype, rname) in enumerate(seeds):
        d = (today + timedelta(days=off)).isoformat()
        docs.append({
            "id": new_id(),
            "title": title,
            "date": d,
            "start_time": st, "end_time": et,
            "location": loc,
            "attendees": [random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"])],
            "with_person": person,
            "ref_type": rtype, "ref_name": rname,
            "agenda": random.choice(["Confirm final specs", "Show new catalogue", "Close deal", "Site measurement"]),
            "status": "Scheduled" if off >= 0 else "Done",
            "created_by": "admin",
            "created_at": now_iso(),
        })
    await db.meets.insert_many(docs)


async def seed_petty_cash(db):
    if await db.petty_cash.count_documents({}) > 0:
        return
    today = datetime.now(timezone.utc).date()
    entries = [
        ("In", "Opening", "", "Opening balance", 25000, "Cash"),
        ("Out", "Fuel", "IOCL Pump", "Delivery van fuel", 3200, "Cash"),
        ("Out", "Food", "Zomato", "Team lunch", 1450, "UPI"),
        ("Out", "Transport", "Auto", "Sample delivery", 450, "Cash"),
        ("In", "Sale", "Anja Reddy", "Advance cash", 15000, "Cash"),
        ("Out", "Repair", "Electrician", "Showroom light fix", 2200, "Cash"),
        ("Out", "Stationery", "Local", "Printer paper", 680, "Cash"),
        ("In", "Sale", "Walk-in customer", "Paint sample sale", 3500, "Cash"),
        ("Out", "Fuel", "HP Pump", "Delivery van", 2800, "Cash"),
        ("Out", "Courier", "Delhivery", "Sample dispatch", 780, "UPI"),
    ]
    docs = []
    for i, (k, cat, party, desc, amt, mode) in enumerate(entries):
        docs.append({
            "id": new_id(),
            "date": (today - timedelta(days=random.randint(0, 20))).isoformat(),
            "kind": k, "category": cat, "party": party,
            "description": desc, "amount": float(amt), "mode": mode,
            "by_user": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "ref": "",
            "created_at": now_iso(),
        })
    await db.petty_cash.insert_many(docs)
