"""Lifecycle engine — pure domain logic ported from the live web CRM (index.html).

Everything here is side-effect free so it can be unit-tested without Mongo. The rules
encoded below come from the production single-file app and must stay behaviour-compatible
with it, because both read the same historical data:

  * dates arrive in a dozen formats (dd/mm/yy, dd-mm-yyyy, ISO, and real typos like
    "24/o1/2026" or "17/01.2026") and a parser that throws takes a whole page render
    down with it — parse_date never raises;
  * any field can come back from the sheet as a NUMBER instead of a string, so every
    text operation coerces with str() first;
  * a money value above 1e10 is a Unix-timestamp that leaked into an amount column,
    never a real amount.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

# Divisions the business reports on. Anything else rolls up into "Other".
DIVISIONS = ["Furniture", "MAP", "D&W"]

# Operational stages a quotation moves through (the sheet's own vocabulary).
QUOTE_STAGES = [
    "Quoted", "Adv Received", "Design & Lock", "Site Not Ready",
    "Rescheduled", "Delivered", "Cancelled",
]
# Stages that mean the deal is won.
_WON_STAGES = {"Adv Received", "Design & Lock", "Site Not Ready", "Rescheduled", "Delivered"}

# Sales-status axis, derived from the ops stage above.
QUOTE_STATUSES = ["Draft", "Sent", "Negotiation", "Won", "Lost", "Expired"]

LEAD_STAGES = ["New", "Contacted", "Follow-Up", "Qualified", "Dormant", "Lost", "Converted"]
LEAD_CLOSED = {"Converted", "Lost"}

MAP_STAGES = [
    "Customer Enquiry", "Site Measurement", "Quotation", "Material Allocation",
    "Applicator Assignment", "Site Readiness", "Project Execution", "Payment & Review",
]

DWS_TYPES = ["Window", "Door", "Sliding", "French Door", "Ventilator", "Partition"]
DWS_FRAMES = ["uPVC", "Aluminium", "Wood", "MS", "WPC"]
DWS_GLASS = ["Single", "Double (DGU)", "Toughened", "Frosted", "Tinted", "None"]

INVENTORY_STATUSES = ["Available", "Sold", "Damaged", "Blocked", "Dealer Catalog"]
# Dealer-catalog rows are a supplier's catalogue page, not owned stock — they are
# searchable and quotable but must never count towards stock value.
NON_STOCK_STATUSES = {"Sold", "Dealer Catalog"}

# A discount above this share of the subtotal needs an admin to approve the quote.
APPROVAL_DISC_PCT = 10.0
# Anything larger than this in a money column is timestamp corruption, not an amount.
MONEY_SANITY_LIMIT = 1e10


# ---------------------------------------------------------------- primitives
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()


def yymm(when: Optional[date] = None) -> str:
    d = when or date.today()
    return f"{d.year % 100:02d}{d.month:02d}"


def norm_phone(value: Any) -> str:
    """Digits only. This is the join key across every dataset."""
    return re.sub(r"\D", "", str(value or ""))


def phone_key(value: Any) -> str:
    """Last 10 digits — folds +91 / 0091 / 0-prefixed variants onto one customer."""
    digits = norm_phone(value)
    return digits[-10:] if len(digits) >= 10 else digits


def latest_remark_text(remarks: Any) -> str:
    """Visitors' `remarks` is either a legacy plain string or the newer list of
    dated entries ([{"text": ..., "at": ...}, ...]). Either way, return the
    most recent note as plain text for callers (like the journey timeline)
    that just want one line, not the whole history."""
    if isinstance(remarks, str):
        return remarks
    if isinstance(remarks, list) and remarks:
        latest = max(remarks, key=lambda r: (r.get("at") or "") if isinstance(r, dict) else "")
        if isinstance(latest, dict):
            return latest.get("text") or ""
        return str(latest)
    return ""


_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DMY_RE = re.compile(r"(\d{1,2})[\/\-.]+(\d{1,2})[\/\-.]+(\d{2,4})")


def parse_date(value: Any) -> Optional[date]:
    """Parse the mixed date formats in the live data. Never raises, returns None instead."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    m = _ISO_RE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # Typos like "24/o1/2026" use a letter o for a zero.
    s2 = s.replace("o", "0").replace("O", "0")
    m = _DMY_RE.search(s2)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def days_since(value: Any) -> Optional[int]:
    d = parse_date(value)
    if not d:
        return None
    return max(0, (date.today() - d).days)


def days_until(value: Any) -> Optional[int]:
    d = parse_date(value)
    if not d:
        return None
    return (d - date.today()).days


def money(value: Any) -> float:
    """Coerce to a float, treating timestamp corruption as zero."""
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if abs(n) > MONEY_SANITY_LIMIT:
        return 0.0
    return n


def is_corrupt_money(value: Any) -> bool:
    try:
        return abs(float(value or 0)) > MONEY_SANITY_LIMIT
    except (TypeError, ValueError):
        return False


def norm_division(value: Any) -> str:
    v = str(value or "").strip()
    return v if v in DIVISIONS else "Other"


# ------------------------------------------------------------ document ids
def _max_suffix(items: Iterable[dict], field: str, prefix: str) -> int:
    top = 0
    for it in items:
        raw = str(it.get(field) or "")
        if raw.startswith(prefix):
            m = re.search(r"(\d+)\s*$", raw[len(prefix):])
            if m:
                top = max(top, int(m.group(1)))
    return top


def next_quote_no(quotes: Iterable[dict]) -> str:
    """AF-YYMM-NNN, restarting each month — matches the sheet's existing convention."""
    prefix = f"AF-{yymm()}-"
    return f"{prefix}{_max_suffix(quotes, 'quote_no', prefix) + 1:03d}"


def next_sale_no(sales: Iterable[dict]) -> str:
    """MF NNN — one running series, never restarted."""
    top = 0
    for s in sales:
        m = re.search(r"(\d+)\s*$", str(s.get("sale_no") or ""))
        if m:
            top = max(top, int(m.group(1)))
    return f"MF {top + 1:03d}"


def _next_dated_id(items: Iterable[dict], field: str, tag: str) -> str:
    prefix = f"{tag}-{yymm()}-"
    return f"{prefix}{_max_suffix(items, field, prefix) + 1:03d}"


def next_lead_id(leads):     return _next_dated_id(leads, "lead_id", "LD")
def next_payment_id(pays):   return _next_dated_id(pays, "payment_id", "PY")
def next_project_id(projs):  return _next_dated_id(projs, "id", "PM")
def next_survey_id(surveys): return _next_dated_id(surveys, "survey_id", "DW")


# ------------------------------------------------------- quote status axis
def quote_status(q: dict) -> str:
    """Sales-status derived from the ops stage. An explicit status always wins."""
    stored = q.get("status")
    if stored:
        return stored
    stage = str(q.get("stage") or "")
    if stage == "Cancelled":
        return "Lost"
    if stage in _WON_STAGES:
        return "Won"
    return "Sent"


def quote_is_open(q: dict) -> bool:
    return quote_status(q) in ("Draft", "Sent", "Negotiation")


def quote_age_days(q: dict) -> Optional[int]:
    return days_since(q.get("date"))


def quote_due_flag(q: dict) -> str:
    """'overdue' / 'stale' / '' — drives the ⚠ and ⏳ markers in the quote list."""
    if quote_status(q) in ("Won", "Lost"):
        return ""
    due = days_until(q.get("next_action_date"))
    if due is not None and due < 0:
        return "overdue"
    age = quote_age_days(q)
    if age is not None and age >= 3 and quote_status(q) == "Sent":
        return "stale"
    return ""


def sanitize_quote(q: dict) -> dict:
    """Idempotent backfill + corruption guard, run on every quote read."""
    if is_corrupt_money(q.get("value")):
        q["value"] = 0
    stage = q.get("stage")
    if isinstance(stage, (int, float)) or str(stage or "").isdigit():
        q["stage"] = "Quoted"
    q.setdefault("version", 1)
    if not q.get("status"):
        q["status"] = quote_status(q)
    return q


def enrich_quote(q: dict) -> dict:
    """Attach the derived fields the UI renders. Never persisted, computed per read."""
    q = sanitize_quote(dict(q))
    q["derived_status"] = quote_status(q)
    q["age_days"] = quote_age_days(q)
    q["due_flag"] = quote_due_flag(q)
    q["is_open"] = quote_is_open(q)
    return q


def quote_view_predicate(view: str, q: dict, me: str = "") -> bool:
    """The saved-view chips on the quote list."""
    if view in ("", "all"):
        return True
    status, age = quote_status(q), quote_age_days(q)
    if view == "myopen":
        return quote_is_open(q) and (q.get("by_user") == me or not me)
    if view == "awaiting":
        return status == "Sent" and age is not None and 3 <= age <= 7
    if view == "hot":
        return quote_is_open(q) and money(q.get("value")) > 200000
    if view == "overdue":
        due = days_until(q.get("next_action_date"))
        return quote_is_open(q) and (
            (due is not None and due < 0) or (status == "Sent" and age is not None and age > 7)
        )
    if view == "wonmtd":
        d = parse_date(q.get("date"))
        first = date.today().replace(day=1)
        return status == "Won" and d is not None and d >= first
    return True


# ------------------------------------------------------------- quote lines
def calc_line(line: dict) -> dict:
    """sft = W×H×qty (feet in, square feet out); amount bills by area when there is one."""
    w, h = money(line.get("w")), money(line.get("h"))
    qty, rate = money(line.get("qty")), money(line.get("rate"))
    line["sft"] = round(w * h * (qty or 1), 2) if w > 0 and h > 0 else 0
    line["amount"] = round((line["sft"] or qty or 0) * rate, 2)
    return line


def lines_subtotal(lines: Iterable[dict]) -> float:
    return round(sum(money(l.get("amount")) for l in lines), 2)


def needs_approval(subtotal: float, discount: float) -> bool:
    return subtotal > 0 and money(discount) > subtotal * APPROVAL_DISC_PCT / 100


def quote_total(subtotal: float, discount: float, tax_pct: float) -> dict:
    """Roll lines → subtotal → discount → tax → grand total. Discount is an absolute ₹."""
    sub = round(money(subtotal), 2)
    disc = min(money(discount), sub)            # a discount never exceeds the subtotal
    taxable = round(sub - disc, 2)
    tax = round(taxable * money(tax_pct) / 100, 2)
    return {"subtotal": sub, "discount": round(disc, 2), "tax_total": tax,
            "grand_total": round(taxable + tax, 2), "value": round(taxable, 2)}


# ------------------------------------------------------------- D&W surveys
def calc_opening(opening: dict) -> dict:
    """W and H are captured in INCHES in the field; area is square feet."""
    w, h = money(opening.get("w")), money(opening.get("h"))
    qty = money(opening.get("qty"))
    opening["area"] = round(w * h * (qty or 1) / 144, 2) if w > 0 and h > 0 else 0
    return opening


# --------------------------------------------------------------- reporting
def report_range(period: str) -> tuple[Optional[date], date, str]:
    """(start, end, label). Weeks start Monday. start=None means all time."""
    today = date.today()
    dow = today.weekday()  # Monday = 0
    if period == "thisweek":
        s = today - timedelta(days=dow)
        return s, today, f"This Week ({s:%d %b} → today)"
    if period == "lastweek":
        e = today - timedelta(days=dow + 1)
        s = e - timedelta(days=6)
        return s, e, f"Last Week ({s:%d %b} – {e:%d %b})"
    if period == "thismonth":
        s = today.replace(day=1)
        return s, today, f"This Month ({s:%B %Y})"
    if period == "lastmonth":
        e = today.replace(day=1) - timedelta(days=1)
        s = e.replace(day=1)
        return s, e, f"Last Month ({s:%B %Y})"
    return None, today, "All Time"


def _blank_row() -> dict:
    return {"leads": 0, "quotes": 0, "qval": 0.0, "won": 0, "wval": 0.0, "collected": 0.0, "due": 0.0}


def build_report(period, leads, quotes, sales, payments) -> dict:
    """Division rollup for the period. Outstanding is deliberately all-time, not periodised —
    an open balance does not stop being owed because the week rolled over."""
    start, end, label = report_range(period)

    def in_range(value) -> bool:
        d = parse_date(value)
        if not d:
            return False
        return (start is None or d >= start) and d <= end

    rows = {d: _blank_row() for d in DIVISIONS + ["Other", "TOTAL"]}

    def add(division, key, amount):
        rows[norm_division(division)][key] += amount
        rows["TOTAL"][key] += amount

    for l in leads:
        if in_range(l.get("intake_date") or l.get("date")):
            add(l.get("division"), "leads", 1)
    for q in quotes:
        if in_range(q.get("date")):
            add(q.get("division"), "quotes", 1)
            add(q.get("division"), "qval", money(q.get("value")))
    for s in sales:
        if in_range(s.get("date")):
            add(s.get("division"), "won", 1)
            add(s.get("division"), "wval", money(s.get("value")))
            add(s.get("division"), "collected", money(s.get("paid")))
        add(s.get("division"), "due", max(0.0, money(s.get("balance"))))
    for p in payments:
        if in_range(p.get("date")) and p.get("direction") != "Refund":
            add(p.get("division"), "collected", money(p.get("amount")))

    return {"period": period, "label": label,
            "start": start.isoformat() if start else None, "end": end.isoformat(),
            "divisions": rows}


def whatsapp_summary(report: dict) -> str:
    """The WhatsApp-pasteable digest the team sends every Monday."""
    rows, icons = report["divisions"], {"Furniture": "🛋", "MAP": "🎨", "D&W": "🚪"}

    def fmt(n: float) -> str:
        n = float(n or 0)
        if abs(n) >= 1e7:
            return f"₹{n / 1e7:.2f}Cr"
        if abs(n) >= 1e5:
            return f"₹{n / 1e5:.2f}L"
        if abs(n) >= 1e3:
            return f"₹{n / 1e3:.1f}k"
        return f"₹{n:.0f}"

    lines = [f"📊 *MADIO {report['label']}*"]
    for d in DIVISIONS:
        r = rows[d]
        if not any((r["leads"], r["quotes"], r["won"], r["collected"])):
            continue
        lines.append(
            f"{icons[d]} *{d}*: {r['leads']} leads | {r['quotes']} quotes ({fmt(r['qval'])})"
            f" | {r['won']} sales ({fmt(r['wval'])}) | collected {fmt(r['collected'])}"
        )
    t = rows["TOTAL"]
    lines += [
        "━━━━━━━━━",
        f"Σ *TOTAL*: {t['leads']} leads | {t['quotes']} quotes ({fmt(t['qval'])})"
        f" | {t['won']} sales ({fmt(t['wval'])}) | collected {fmt(t['collected'])}",
        f"⚠ Outstanding: {fmt(t['due'])}",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------- outstanding
AGING_BUCKETS = ["0-30", "31-60", "61-90", "90+"]


def aging_bucket(days: Optional[int]) -> str:
    if days is None:
        return "90+"
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def sale_phone(sale: dict, quotes_by_no: dict) -> str:
    """Imported won-deals carry no phone of their own; fall back to the linked quote.
    Without this, payment reminders silently reach nobody."""
    direct = norm_phone(sale.get("phone"))
    if len(direct) >= 10:
        return direct
    ref = sale.get("quote_ref")
    if ref and ref in quotes_by_no:
        return norm_phone(quotes_by_no[ref].get("phone"))
    return ""


def balance_is_meaningful(sale: dict) -> bool:
    """Legacy rows carry paid=0, bal=0 meaning 'settled, never itemised'. Recomputing
    balance = value - paid on those resurrects lakhs of phantom outstanding, so a
    zero-paid legacy row is never treated as a balance discrepancy."""
    return money(sale.get("paid")) > 0


# ------------------------------------------------------------------ alerts
def build_alerts(leads, navaki, sales, quotes, inventory, max_no_date: int = 25) -> list[dict]:
    """Grouped follow-up + money + stock alerts, ordered overdue → today → week → money → nodate."""
    alerts: list[dict] = []
    follow_ups = []

    for l in leads:
        if str(l.get("stage") or "") in LEAD_CLOSED:
            continue
        follow_ups.append({
            "name": l.get("name"), "phone": l.get("phone"),
            "date": l.get("next_action_date"), "stage": l.get("stage"),
            "src": f"Lead ({l.get('source') or ''})", "coll": "leads", "id": l.get("id"),
        })
    for n in navaki:
        follow_ups.append({
            "name": n.get("name"), "phone": n.get("phone"),
            "date": n.get("follow_up_date") or n.get("fu_date"), "stage": n.get("stage"),
            "src": "Navaki", "coll": "navaki", "id": n.get("id"),
        })

    no_date = 0
    for f in follow_ups:
        first = str(f.get("name") or "").split(" ")[0]
        base = {"name": f["name"], "phone": f["phone"], "coll": f["coll"], "record_id": f["id"]}
        if f["date"]:
            diff = days_until(f["date"])
            if diff is None:
                continue
            if diff < 0:
                alerts.append({**base, "group": "overdue", "severity": "danger", "icon": "🔴",
                               "title": f["name"],
                               "detail": f"{f['src']} · was due {abs(diff)}d ago · stage: {f.get('stage') or '—'}",
                               "wa_text": f"Hi {first}, hope you are doing well. Following up on your enquiry — can we schedule a visit?"})
            elif diff == 0:
                alerts.append({**base, "group": "today", "severity": "warn", "icon": "⚡",
                               "title": f["name"],
                               "detail": f"{f['src']} · follow-up today · stage: {f.get('stage') or '—'}",
                               "wa_text": f"Hi {first}, today is our scheduled follow-up. How can we assist you?"})
            elif diff <= 7:
                alerts.append({**base, "group": "week", "severity": "info", "icon": "📅",
                               "title": f["name"],
                               "detail": f"{f['src']} · due in {diff}d · stage: {f.get('stage') or '—'}",
                               "wa_text": f"Hi {first}, just a reminder — we have a follow-up scheduled."})
        elif str(f.get("stage") or "") in ("New", "New Lead", "Follow-Up", "Contacted", "Qualified"):
            no_date += 1
            if no_date <= max_no_date:
                alerts.append({**base, "group": "nodate", "severity": "info", "icon": "🆕",
                               "title": f["name"],
                               "detail": f"{f['src']} · stage {f.get('stage')} · no follow-up date — set one"})
    if no_date > max_no_date:
        alerts.append({"group": "nodate", "severity": "info", "icon": "🆕",
                       "title": f"… and {no_date - max_no_date} more without a date",
                       "detail": "Open Leads to triage the rest"})

    quotes_by_no = {q.get("quote_no"): q for q in quotes if q.get("quote_no")}
    for s in sales:
        bal = money(s.get("balance"))
        if bal <= 50000:
            continue
        first = str(s.get("customer") or "").split(" ")[0]
        alerts.append({"group": "money", "severity": "danger", "icon": "⚠",
                       "title": f"{s.get('customer')} — balance ₹{bal:,.0f}",
                       "detail": f"{s.get('sale_no')} · sale value ₹{money(s.get('value')):,.0f} · {s.get('stage') or ''}",
                       "coll": "sales", "record_id": s.get("id"),
                       "phone": sale_phone(s, quotes_by_no), "name": s.get("customer"),
                       "amount": bal,
                       "wa_text": f"Hi {first}, this is a friendly reminder about the pending balance of "
                                  f"₹{bal:,.0f} for your order {s.get('sale_no')}. Please let us know a "
                                  f"convenient time for payment."})

    for q in quotes:
        if money(q.get("value")) <= 200000:
            continue
        if str(q.get("stage") or "") not in ("Quoted", "Site Not Ready", "Rescheduled"):
            continue
        first = str(q.get("customer") or "").split(" ")[0]
        alerts.append({"group": "money", "severity": "warn", "icon": "💰",
                       "title": f"₹{money(q.get('value')):,.0f} quote unclosed — {q.get('customer')}",
                       "detail": f"{q.get('quote_no')} · {q.get('stage')} · {q.get('by_user') or ''}",
                       "coll": "quotes", "record_id": q.get("id"),
                       "phone": norm_phone(q.get("phone")), "name": q.get("customer"),
                       "wa_text": f"Hi {first}, this is {q.get('by_user') or 'MADIO'}. Following up on your "
                                  f"quote {q.get('quote_no')}. Can we discuss next steps?"})

    dead = [i for i in inventory
            if i.get("status") == "Available"
            and (days_since(i.get("date_added")) or 0) >= 90]
    if dead:
        idle = sum(money(i.get("mrp")) for i in dead)
        alerts.append({"group": "money", "severity": "warn", "icon": "📦",
                       "title": f"Dead stock: {len(dead)} items unsold 90+ days",
                       "detail": f"₹{idle:,.0f} MRP idle — see Inventory Analytics"})

    order = {"overdue": 0, "today": 1, "week": 2, "money": 3, "nodate": 4}
    alerts.sort(key=lambda a: order.get(a.get("group"), 9))
    return alerts


# ----------------------------------------------------------------- journey
def build_journey(phone: Any, *, visitors, leads, quotes, sales, payments, activities) -> dict:
    """Customer-360: every record for one phone number, on one timeline.
    Phone is the only identifier shared by all six datasets."""
    key = phone_key(phone)
    if not key:
        return {"phone": "", "events": [], "totals": {}, "linked": {}}

    def matches(value) -> bool:
        return bool(key) and phone_key(value) == key

    events, quoted, sold, balance, collected = [], 0.0, 0.0, 0.0, 0.0
    linked_quotes = [q for q in quotes if matches(q.get("phone"))]
    linked_quote_nos = {q.get("quote_no") for q in linked_quotes}

    for v in visitors:
        if matches(v.get("phone")):
            events.append({"date": v.get("date"), "icon": "🚶", "kind": "Walk-in visit",
                           "title": f"{v.get('requirement') or 'Visit'} · attended by {v.get('attend_person') or '—'}",
                           "detail": latest_remark_text(v.get("remarks")), "link": "/visitors"})
    for l in leads:
        if matches(l.get("phone")):
            events.append({"date": l.get("intake_date") or l.get("date"), "icon": "⚇",
                           "kind": f"Lead ({l.get('source') or ''})",
                           "title": f"{l.get('lead_id') or ''} · {l.get('division') or ''} · Stage: {l.get('stage') or ''}",
                           "detail": l.get("remarks") or "", "link": "/leads"})
    for q in linked_quotes:
        val = money(q.get("value"))
        quoted += val
        events.append({"date": q.get("date"), "icon": "◇", "kind": "Quotation",
                       "title": f"{q.get('quote_no')} · {q.get('division') or ''} · ₹{val:,.0f}",
                       "detail": f"Stage: {q.get('stage') or ''}",
                       "link": f"/quotes/{q.get('id')}", "value": val})
    linked_sales = [s for s in sales
                    if matches(s.get("phone")) or (s.get("quote_ref") in linked_quote_nos)]
    for s in linked_sales:
        val, paid, bal = money(s.get("value")), money(s.get("paid")), money(s.get("balance"))
        sold += val
        balance += bal
        events.append({"date": s.get("date"), "icon": "◆", "kind": "Sale",
                       "title": f"{s.get('sale_no')} · ₹{val:,.0f}"
                                + (f" (from {s.get('quote_ref')})" if s.get("quote_ref") else ""),
                       "detail": f"Paid ₹{paid:,.0f} · Balance ₹{bal:,.0f} · {s.get('stage') or ''}",
                       "link": "/sales", "value": val})
    for p in payments:
        if matches(p.get("phone")) or p.get("against_quote_no") in linked_quote_nos:
            amt = money(p.get("amount"))
            collected += amt
            events.append({"date": p.get("date"), "icon": "₹", "kind": "Payment",
                           "title": f"₹{amt:,.0f} · {p.get('mode') or ''} · {p.get('kind') or ''}",
                           "detail": (f"Against {p.get('against_quote_no')}" if p.get("against_quote_no") else "")
                                     + (f" · by {p.get('received_by')}" if p.get("received_by") else ""),
                           "link": "/outstanding"})
    for a in activities:
        if matches(a.get("phone")):
            events.append({"date": a.get("date"), "icon": "⚐", "kind": a.get("type") or "Activity",
                           "title": f"{a.get('outcome') or ''}"
                                    + (f" · {a.get('ref_id')}" if a.get("ref_id") else ""),
                           "detail": f"by {a.get('by_user')}" if a.get("by_user") else "", "link": "/tasks"})

    events.sort(key=lambda e: (parse_date(e.get("date")) or date(1970, 1, 1)))
    lead = next((l for l in leads if matches(l.get("phone"))), None)
    name = next((e for e in (
        (lead or {}).get("name"),
        next((s.get("customer") for s in linked_sales), None),
        next((q.get("customer") for q in linked_quotes), None),
    ) if e), "")

    return {
        "phone": key, "name": name,
        "lead_stage": (lead or {}).get("stage"),
        "divisions": sorted({d for d in (
            [q.get("division") for q in linked_quotes] + [s.get("division") for s in linked_sales]
        ) if d}),
        "totals": {"quoted": quoted, "sold": sold, "collected": collected or
                   sum(money(s.get("paid")) for s in linked_sales), "balance": balance},
        "linked": {"quotes": linked_quotes, "sales": linked_sales},
        "events": events,
    }


# ------------------------------------------------------------- stock ledger
# Movement types and the sign each applies to on-hand quantity. A transfer is
# modelled as two rows (an Issue from one warehouse + a Receipt into another) so
# the global on-hand nets to zero while per-warehouse balances move.
STOCK_MOVE_TYPES = ["Receipt", "Issue", "Transfer", "Adjustment", "Return"]
_MOVE_SIGN = {"Receipt": 1, "Return": 1, "Issue": -1, "Transfer": -1, "Adjustment": 1}


def next_movement_id(moves: Iterable[dict]) -> str:
    return _next_dated_id(moves, "movement_no", "MV")


def signed_qty(move: dict) -> float:
    """Quantity contribution to on-hand. Adjustment keeps its own sign (can be negative)."""
    q = money(move.get("qty"))
    t = str(move.get("type") or "")
    if t == "Adjustment":
        return q
    return _MOVE_SIGN.get(t, 0) * abs(q)


def stock_on_hand(movements: Iterable[dict]) -> dict:
    """product_id → net on-hand quantity across every movement."""
    on_hand: dict = {}
    for m in movements:
        pid = m.get("product_id")
        if not pid:
            continue
        on_hand[pid] = on_hand.get(pid, 0) + signed_qty(m)
    return on_hand


def stock_summary(movements, inventory) -> dict:
    """On-hand per product joined to its inventory name, plus movement-type counts."""
    on_hand = stock_on_hand(movements)
    by_name = {i.get("sku"): i.get("name") for i in inventory}
    rows = [{"product_id": pid, "name": by_name.get(pid, pid), "on_hand": round(qty, 2)}
            for pid, qty in sorted(on_hand.items())]
    type_counts: dict = {}
    for m in movements:
        t = str(m.get("type") or "?")
        type_counts[t] = type_counts.get(t, 0) + 1
    return {"products": rows, "total_movements": len(list(movements) if not isinstance(movements, list) else movements),
            "by_type": type_counts}


# ------------------------------------------------------------- CSV I/O
# Data-Centre import/export. Every exported cell is guarded against CSV formula
# injection — a cell that starts with = + - @ (or a control char) is prefixed with
# an apostrophe so a spreadsheet treats it as text, not a formula.
_CSV_DANGEROUS = ("=", "+", "-", "@")


def csv_cell(value: Any) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if s and s[0] in _CSV_DANGEROUS:
        s = "'" + s
    return s


def to_csv(rows: list[dict], fields: list[str]) -> str:
    """Serialise rows to CSV text using exactly `fields` as the header/column order."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields)
    for r in rows:
        writer.writerow([csv_cell(r.get(f)) for f in fields])
    return buf.getvalue()


def from_csv(text: str) -> list[dict]:
    """Parse CSV text (first row = header) into a list of dicts. Strips a leading
    apostrophe guard so a round-trip is lossless."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    out = []
    for raw in rows[1:]:
        if not any(c.strip() for c in raw):        # skip blank lines
            continue
        rec = {}
        for i, key in enumerate(header):
            val = raw[i] if i < len(raw) else ""
            if val.startswith("'") and len(val) > 1 and val[1] in _CSV_DANGEROUS:
                val = val[1:]
            rec[key] = val
        out.append(rec)
    return out
