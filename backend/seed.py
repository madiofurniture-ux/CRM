"""Seed real sample data on startup."""
import json
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

from auth import hash_pin
from models import now_iso, new_id

DATA_DIR = Path(__file__).parent / "data"


SEED_USERS = [
    {"username": "admin", "name": "Admin", "pin": "1234", "role": "admin", "icon": "AD", "color": "#1A1D1A", "pages": None},
    {"username": "raghu", "name": "Raghu MF", "pin": "2222", "role": "user", "icon": "RM", "color": "#C85A32", "pages": ["dashboard", "pipeline", "quotes", "sales", "visitors", "leads", "architects", "inventory", "tasks"]},
    {"username": "nenmu", "name": "Nenmu", "pin": "3333", "role": "user", "icon": "NM", "color": "#4A5D4E", "pages": ["dashboard", "pipeline", "quotes", "sales", "visitors", "leads", "architects", "inventory", "tasks"]},
    {"username": "gowtham", "name": "Gowtham Hive", "pin": "4444", "role": "user", "icon": "GH", "color": "#D48B30", "pages": ["dashboard", "pipeline", "quotes", "sales", "visitors", "leads", "architects", "inventory", "tasks"]},
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
    existing = await db.users.count_documents({})
    if existing >= len(SEED_USERS):
        return
    for u in SEED_USERS:
        if await db.users.find_one({"username": u["username"]}):
            continue
        doc = {
            "id": new_id(),
            "username": u["username"],
            "name": u["name"],
            "pin_hash": hash_pin(u["pin"]),
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
    items = json.loads(path.read_text())
    docs = []
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
            "image_url": "",
            "created_at": now_iso(),
        })
    if docs:
        await db.inventory.insert_many(docs)


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


async def seed_all(db):
    await seed_users(db)
    await seed_visitors(db)
    await seed_inventory(db)
    await seed_sales(db)
    await seed_leads(db)
    await seed_architects(db)
    await seed_quotes(db)
    await seed_tasks(db)
