"""Seed real sample data on startup."""
import json
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

from auth import hash_pin
from models import now_iso, new_id

DATA_DIR = Path(__file__).parent / "data"


# Page ids must match lib/nav.js on the frontend.
SALES_PAGES = ["dashboard", "alerts", "pipeline", "quotes", "sales", "visitors", "leads",
               "architects", "projects", "dwsurvey", "outstanding", "inventory",
               "stock-ledger", "inv-analytics", "meetplan", "reports", "tasks",
               "attendance", "data-centre"]

SEED_USERS = [
    {"username": "admin", "name": "Admin", "pin": "1234", "role": "admin", "icon": "AD", "color": "#1A1D1A", "pages": None},
    {"username": "raghu", "name": "Raghu MF", "pin": "2222", "role": "user", "icon": "RM", "color": "#C85A32", "pages": SALES_PAGES},
    {"username": "nenmu", "name": "Nenmu", "pin": "3333", "role": "user", "icon": "NM", "color": "#4A5D4E", "pages": SALES_PAGES},
    {"username": "gowtham", "name": "Gowtham Hive", "pin": "4444", "role": "user", "icon": "GH", "color": "#D48B30", "pages": SALES_PAGES},
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
    sources = ["Walk-in", "Navaki", "Architect", "Referral", "Online"]
    divisions = ["Furniture", "MAP", "D&W"]
    docs = []
    today = datetime.now(timezone.utc).date()
    for i, n in enumerate(names):
        stage = random.choice(["New", "Contacted", "Follow-Up", "Qualified", "Dormant", "Lost", "Converted"])
        d = today - timedelta(days=random.randint(0, 60))
        na = today + timedelta(days=random.randint(-3, 14))
        docs.append({
            "id": new_id(),
            "lead_id": f"LD-{d.strftime('%y%m')}-{i + 1:03d}",
            "source": random.choice(sources),
            "source_ref": "",
            "intake_date": d.isoformat(),
            "name": n,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "referrer": random.choice(["Naveen Smiley", "Architect ref", "", "Instagram"]),
            "requirement": random.choice(["Sofa set", "Full home interior", "Wall texture", "uPVC windows", "Dining"]),
            "division": random.choice(divisions),
            "owner": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "stage": stage,
            "next_action_date": "" if stage in ("Lost", "Converted") else na.isoformat(),
            "last_contact_date": "",
            "remarks": random.choice(["Interested in living room", "Asked for catalogue", "Site visit pending", "Quotation under review", "Negotiating price", "Wants paint sample"]),
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
    # Real ops-stage vocabulary — the sales-status axis (Sent/Won/Lost) is derived from these.
    stages = ["Quoted", "Adv Received", "Design & Lock", "Site Not Ready",
              "Rescheduled", "Delivered", "Cancelled"]
    for i, (c, r) in enumerate(customers, start=1):
        stage = random.choice(stages)
        won = stage in ("Adv Received", "Design & Lock", "Delivered")
        value = float(random.choice([85000, 125000, 180000, 245000, 320000, 480000, 750000, 1200000]))
        d = today - timedelta(days=random.randint(0, 90))
        docs.append({
            "id": new_id(),
            "quote_no": f"AF-{d.strftime('%y%m')}-{i:03d}",
            "date": d.isoformat(),
            "customer": c,
            "reference": r,
            "phone": f"9{random.randint(100000000, 999999999)}",
            "division": random.choice(DIVISIONS),
            "by_user": random.choice(["Raghu MF", "Nenmu", "Gowtham Hive"]),
            "stage": stage,
            "value": value,
            "cash": round(value * random.uniform(0.1, 0.4), 2) if won else 0,
            "bank": round(value * random.uniform(0.3, 0.6), 2) if won else 0,
            "mode": random.choice(["Walk-in", "WhatsApp", "Site Visit", "Phone"]),
            "version": 1,
            "next_action_date": "" if stage in ("Delivered", "Cancelled")
                                else (today + timedelta(days=random.randint(-5, 10))).isoformat(),
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
    await seed_invoices(db)
    await seed_meets(db)
    await seed_petty_cash(db)


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
        tax_pct = 18
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
