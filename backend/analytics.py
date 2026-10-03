"""Analytics hub aggregations: sales, leads, calls, attendance, vendors & projects.

Pure functions over already-fetched, already-tenant-scoped documents — no db,
no FastAPI — so every figure on the Analytics screen is unit-testable. server.py
fetches (through tenancy.scope) and applies the caller's visibility (admins see
everyone; anyone else sees their own records only) before calling in here.

Dates in this dataset arrive in many formats (see lifecycle.parse_date), so
every date goes through lc.parse_date and money through lc.money.

Each summary returns:
  kpis    [{key, label, value, prev, format}]  prev = same-length period just before
  series  {name: [{bucket, label, <values>}]}  zero-filled, one row per bucket
  tables  {name: [row, ...]}
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

import lifecycle as lc

MAX_RANGE_DAYS = 3 * 366


# ── ranges and buckets ─────────────────────────────────────────────────────
def parse_range(start: str, end: str, today: Optional[date] = None) -> tuple[date, date]:
    """Inclusive [start, end]; defaults to the last 30 days. Raises ValueError."""
    today = today or date.today()
    e = lc.parse_date(end) if end else today
    s = lc.parse_date(start) if start else (e - timedelta(days=29))
    if not s or not e:
        raise ValueError("start and end must be dates (YYYY-MM-DD)")
    if s > e:
        raise ValueError("start must be on or before end")
    if (e - s).days > MAX_RANGE_DAYS:
        raise ValueError("the range can be at most 3 years")
    return s, e


def previous_range(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    return start - timedelta(days=span), start - timedelta(days=1)


def granularity(start: date, end: date) -> str:
    days = (end - start).days + 1
    if days <= 45:
        return "day"
    if days <= 200:
        return "week"
    return "month"


def bucket_of(d: date, gran: str) -> str:
    if gran == "day":
        return d.isoformat()
    if gran == "week":
        return (d - timedelta(days=d.weekday())).isoformat()   # Monday
    return d.strftime("%Y-%m")


def bucket_label(key: str, gran: str) -> str:
    if gran == "month":
        return datetime.strptime(key, "%Y-%m").strftime("%b %Y")
    d = date.fromisoformat(key)
    return d.strftime("%d %b") if gran == "day" else f"Wk of {d.strftime('%d %b')}"


def bucket_keys(start: date, end: date, gran: str) -> list[str]:
    keys, d = [], start
    while d <= end:
        k = bucket_of(d, gran)
        if not keys or keys[-1] != k:
            keys.append(k)
        d += timedelta(days=1)
    return keys


def _series(start: date, end: date, gran: str, rows: Iterable[tuple[date, dict]],
            fields: list[str]) -> list[dict]:
    acc = {k: {f: 0 for f in fields} for k in bucket_keys(start, end, gran)}
    for d, vals in rows:
        slot = acc.get(bucket_of(d, gran))
        if slot is None:
            continue
        for f in fields:
            slot[f] += vals.get(f, 0)
    return [{"bucket": k, "label": bucket_label(k, gran),
             **{f: round(v, 2) if isinstance(v, float) else v for f, v in vals.items()}}
            for k, vals in acc.items()]


def within(docs: Iterable[dict], field: str | Callable[[dict], Any],
           start: date, end: date) -> list[tuple[date, dict]]:
    """(parsed date, doc) for every doc whose date falls in [start, end]."""
    get = field if callable(field) else (lambda d: d.get(field))
    out = []
    for doc in docs:
        d = lc.parse_date(get(doc))
        if d and start <= d <= end:
            out.append((d, doc))
    return out


def kpi(key: str, label: str, value, prev=None, fmt: str = "number") -> dict:
    return {"key": key, "label": label, "value": value, "prev": prev, "format": fmt}


def pct(part: float, whole: float) -> Optional[float]:
    return round(100.0 * part / whole, 1) if whole else None


def _name(v: Any, fallback: str) -> str:
    s = str(v or "").strip()
    return s or fallback


def _division_ok(doc: dict, division: str) -> bool:
    return not division or lc.norm_division(doc.get("division")) == division


# ── sales ──────────────────────────────────────────────────────────────────
def sales_summary(sales: list[dict], start: date, end: date, *, division: str = "") -> dict:
    sales = [s for s in sales if _division_ok(s, division)]
    gran = granularity(start, end)
    cur = within(sales, "date", start, end)
    prev = within(sales, "date", *previous_range(start, end))

    def totals(rows):
        value = sum(lc.money(s.get("value")) for _, s in rows)
        paid = sum(lc.money(s.get("paid")) for _, s in rows)
        balance = sum(lc.money(s.get("balance")) for _, s in rows)
        return value, paid, balance, len(rows)

    v, p, b, n = totals(cur)
    pv, pp, pb, pn = totals(prev)
    kpis = [
        kpi("revenue", "Sales value", round(v), round(pv), "money"),
        kpi("orders", "Orders", n, pn),
        kpi("aov", "Average order", round(v / n) if n else 0, round(pv / pn) if pn else 0, "money"),
        kpi("collected", "Collected", round(p), round(pp), "money"),
        kpi("outstanding", "Outstanding", round(b), round(pb), "money"),
    ]
    trend = _series(start, end, gran, ((d, {"value": lc.money(s.get("value")), "orders": 1})
                                       for d, s in cur), ["value", "orders"])

    by_div, by_rep, by_cust = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0, 0.0]), defaultdict(float)
    for _, s in cur:
        val = lc.money(s.get("value"))
        dv = by_div[lc.norm_division(s.get("division"))]
        dv[0] += val
        dv[1] += 1
        rp = by_rep[_name(s.get("by_user"), "Unassigned")]
        rp[0] += val
        rp[1] += 1
        rp[2] += lc.money(s.get("paid"))
        by_cust[_name(s.get("customer"), "Unknown")] += val
    divisions = [{"name": k, "value": round(x[0]), "orders": x[1]}
                 for k, x in sorted(by_div.items(), key=lambda kv: -kv[1][0])]
    reps = [{"name": k, "value": round(x[0]), "orders": x[1], "collected": round(x[2])}
            for k, x in sorted(by_rep.items(), key=lambda kv: -kv[1][0])]
    customers = [{"name": k, "value": round(x)}
                 for k, x in sorted(by_cust.items(), key=lambda kv: -kv[1])[:10]]
    return {"granularity": gran, "kpis": kpis, "series": {"trend": trend},
            "tables": {"by_division": divisions, "by_rep": reps, "top_customers": customers}}


# ── leads ──────────────────────────────────────────────────────────────────
def _stage_index(stages: list, value: Any) -> Optional[int]:
    v = str(value or "").strip().lower()
    for i, s in enumerate(stages):
        if s["label"].lower() == v or s["key"] == lc_key(v):
            return i
    return None


def lc_key(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", v).strip("_")


def leads_summary(leads: list[dict], stages: list[dict], start: date, end: date) -> dict:
    """`stages` is the tenant's lead workflow (tenancy stage dicts, in order)."""
    gran = granularity(start, end)
    cur = within(leads, "date", start, end)
    prev = within(leads, "date", *previous_range(start, end))
    won_keys = {s["key"] for s in stages if s.get("won")}
    lost_keys = {s["key"] for s in stages if s.get("terminal") and not s.get("won")}

    def outcome(doc) -> str:
        i = _stage_index(stages, doc.get("stage"))
        if i is None:
            return "open"
        k = stages[i]["key"]
        return "won" if k in won_keys else "lost" if k in lost_keys else "open"

    def counts(rows):
        c = Counter(outcome(d) for _, d in rows)
        return len(rows), c["won"], c["lost"]

    n, w, l_ = counts(cur)
    pn, pw, pl = counts(prev)
    value = sum(lc.money(d.get("value")) for _, d in cur)
    kpis = [
        kpi("new", "New leads", n, pn),
        kpi("won", "Won", w, pw),
        kpi("win_rate", "Win rate", pct(w, w + l_), pct(pw, pw + pl), "percent"),
        kpi("open", "Still open", n - w - l_, pn - pw - pl),
        kpi("pipeline", "Lead value", round(value), None, "money"),
    ]
    trend = _series(start, end, gran, ((d, {"leads": 1, "won": 1 if outcome(doc) == "won" else 0})
                                       for d, doc in cur), ["leads", "won"])

    # Funnel: how many leads created in the range reached at least each open
    # stage (from stage_history when present, else the current stage). A won
    # lead has passed every open stage; a lost lead counts up to where it got.
    open_stages = [s for s in stages if not s.get("terminal")]
    open_idx = {s["key"]: i for i, s in enumerate(open_stages)}
    reached = [0] * len(open_stages)
    won_total = 0
    for _, doc in cur:
        if outcome(doc) == "won":
            won_total += 1
            for i in range(len(open_stages)):
                reached[i] += 1
            continue
        visited = [h.get("to") for h in doc.get("stage_history") or []] + [doc.get("stage")]
        best = -1
        for v in visited:
            i = _stage_index(stages, v)
            if i is not None and stages[i]["key"] in open_idx:
                best = max(best, open_idx[stages[i]["key"]])
        for i in range(best + 1):
            reached[i] += 1
    funnel = [{"name": s["label"], "value": reached[i]} for i, s in enumerate(open_stages)]
    funnel.append({"name": next((s["label"] for s in stages if s.get("won")), "Won"), "value": won_total})

    by_source, by_owner = defaultdict(Counter), defaultdict(Counter)
    for _, doc in cur:
        o = outcome(doc)
        for bucket in (by_source[_name(doc.get("source"), "Unknown")],
                       by_owner[_name(doc.get("assigned_to"), "Unassigned")]):
            bucket["leads"] += 1
            bucket[o] += 1

    def rows(groups):
        return [{"name": k, "leads": c["leads"], "won": c["won"], "lost": c["lost"],
                 "win_rate": pct(c["won"], c["won"] + c["lost"])}
                for k, c in sorted(groups.items(), key=lambda kv: -kv[1]["leads"])]

    return {"granularity": gran, "kpis": kpis, "series": {"trend": trend},
            "tables": {"funnel": funnel, "by_source": rows(by_source), "by_owner": rows(by_owner)}}


# ── calls ──────────────────────────────────────────────────────────────────
CALL_OUTCOMES = ["Interested", "Callback", "Not interested", "No answer", "Busy", "Wrong number"]
CALL_CONNECTED = {"Interested", "Callback", "Not interested"}


def calls_summary(calls: list[dict], start: date, end: date, *, division: str = "") -> dict:
    calls = [c for c in calls if _division_ok(c, division)]
    gran = granularity(start, end)
    cur = within(calls, "date", start, end)
    prev = within(calls, "date", *previous_range(start, end))

    def counts(rows):
        n = len(rows)
        conn = sum(1 for _, c in rows if c.get("outcome") in CALL_CONNECTED)
        inter = sum(1 for _, c in rows if c.get("outcome") == "Interested")
        conv = sum(1 for _, c in rows if c.get("lead_id"))
        return n, conn, inter, conv

    n, conn, inter, conv = counts(cur)
    pn, pconn, pinter, pconv = counts(prev)
    days = (end - start).days + 1
    kpis = [
        kpi("calls", "Calls", n, pn),
        kpi("per_day", "Calls per day", round(n / days, 1), round(pn / days, 1), "decimal"),
        kpi("connect_rate", "Connect rate", pct(conn, n), pct(pconn, pn), "percent"),
        kpi("interested", "Interested", inter, pinter),
        kpi("converted", "Converted to leads", conv, pconv),
        kpi("conversion", "Call → lead rate", pct(conv, n), pct(pconv, pn), "percent"),
    ]
    trend = _series(start, end, gran, (
        (d, {"connected": 1 if c.get("outcome") in CALL_CONNECTED else 0,
             "not_connected": 0 if c.get("outcome") in CALL_CONNECTED else 1})
        for d, c in cur), ["connected", "not_connected"])
    oc = Counter(c.get("outcome") for _, c in cur)
    outcomes = [{"name": o, "value": oc.get(o, 0)} for o in CALL_OUTCOMES]
    per = defaultdict(Counter)
    for _, c in cur:
        p = per[_name(c.get("by_user"), "Unknown")]
        p["calls"] += 1
        p["connected"] += c.get("outcome") in CALL_CONNECTED
        p["interested"] += c.get("outcome") == "Interested"
        p["converted"] += bool(c.get("lead_id"))
    callers = [{"name": k, "calls": v["calls"], "per_day": round(v["calls"] / days, 1),
                "connect_rate": pct(v["connected"], v["calls"]), "interested": v["interested"],
                "converted": v["converted"]}
               for k, v in sorted(per.items(), key=lambda kv: -kv[1]["calls"])]
    return {"granularity": gran, "kpis": kpis, "series": {"trend": trend},
            "tables": {"outcomes": outcomes, "by_caller": callers}}


# ── attendance ─────────────────────────────────────────────────────────────
def worked_minutes(rec: dict) -> Optional[float]:
    """duration_min when recorded; else computed from the check-in/out times
    (every check-out before the timezone fix stored 0)."""
    dur = rec.get("duration_min")
    if isinstance(dur, (int, float)) and dur > 0:
        return float(dur)
    ci, co = rec.get("check_in_at"), rec.get("check_out_at")
    if not ci or not co:
        return None
    try:
        a = datetime.fromisoformat(str(ci).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(co).replace("Z", "+00:00"))
    except ValueError:
        return None
    mins = (b - a).total_seconds() / 60
    return mins if 0 < mins < 24 * 60 else None


def attendance_summary(records: list[dict], start: date, end: date, *,
                       staff_count: int = 0, today: Optional[date] = None) -> dict:
    gran = granularity(start, end)
    today = today or date.today()

    def present(r):
        return str(r.get("status") or "") != "absent" and bool(r.get("check_in_at"))

    cur = within(records, "date", start, end)
    prev = within(records, "date", *previous_range(start, end))

    def figures(rows):
        days = [r for _, r in rows if present(r)]
        mins = [m for m in (worked_minutes(r) for r in days) if m is not None]
        out = sum(1 for r in days if r.get("check_in_within") is False
                  or r.get("status") == "flagged_out_of_bounds")
        no_out = sum(1 for r in days if not r.get("check_out_at") and lc.parse_date(r.get("date")) != today)
        return len(days), (sum(mins) / len(mins) / 60) if mins else None, out, no_out

    pdays, avg_h, out, no_out = figures(cur)
    ppdays, pavg_h, pout, pno_out = figures(prev)
    present_today = len({r.get("user_id") for r in records
                         if lc.parse_date(r.get("date")) == today and present(r)})
    kpis = [
        kpi("present_today", "Present today", present_today, None),
        kpi("person_days", "Days present", pdays, ppdays),
        kpi("avg_hours", "Average hours / day", round(avg_h, 1) if avg_h else None,
            round(pavg_h, 1) if pavg_h else None, "hours"),
        kpi("out_of_fence", "Check-ins outside site", out, pout),
        kpi("no_checkout", "Missing check-outs", no_out, pno_out),
    ]
    if staff_count:
        kpis.insert(1, kpi("staff", "Staff", staff_count, None))
    trend = _series(start, end, gran, ((d, {"present": 1 if present(r) else 0,
                                            "absent": 1 if r.get("status") == "absent" else 0})
                                       for d, r in cur), ["present", "absent"])
    per = defaultdict(lambda: {"days": 0, "absent": 0, "mins": [], "out": 0, "no_out": 0})
    for d, r in cur:
        p = per[(r.get("user_id"), _name(r.get("name"), "Unknown"))]
        if r.get("status") == "absent":
            p["absent"] += 1
            continue
        if not present(r):
            continue
        p["days"] += 1
        m = worked_minutes(r)
        if m is not None:
            p["mins"].append(m)
        if r.get("check_in_within") is False or r.get("status") == "flagged_out_of_bounds":
            p["out"] += 1
        if not r.get("check_out_at") and d != today:
            p["no_out"] += 1
    people = [{"name": name, "days": v["days"], "absent": v["absent"],
               "avg_hours": round(sum(v["mins"]) / len(v["mins"]) / 60, 1) if v["mins"] else None,
               "hours": round(sum(v["mins"]) / 60, 1),
               "out_of_fence": v["out"], "no_checkout": v["no_out"]}
              for (_, name), v in sorted(per.items(), key=lambda kv: -kv[1]["days"])]
    return {"granularity": gran, "kpis": kpis, "series": {"trend": trend},
            "tables": {"by_person": people}}


# ── vendors & projects ─────────────────────────────────────────────────────
MO_STATUSES = ["Quoted", "Confirmed", "In Production", "Dispatched", "Delivered", "Installed"]
MO_OPEN = {"Confirmed", "In Production", "Dispatched"}
PROJECT_STAGES = ["Survey", "Quoted", "Execution", "Review", "Closure", "Completed"]
PROJECT_DONE = {"Closure", "Completed"}


def vendors_summary(orders: list[dict], projects: list[dict], start: date, end: date, *,
                    division: str = "", vendor_label: Callable[[dict], str] = None,
                    today: Optional[date] = None) -> dict:
    today = today or date.today()
    orders = [o for o in orders if _division_ok(o, division)]
    projects = [p for p in projects if _division_ok(p, division)]
    label = vendor_label or (lambda o: _name(o.get("vendor_code") or o.get("vendor_name"), "Unknown"))
    in_range = [o for _, o in within(orders, "date", start, end)]

    open_orders = [o for o in orders if o.get("status") in MO_OPEN]
    balance = sum(lc.money(o.get("total_balance_due")) for o in orders if o.get("status") != "Quoted")
    overdue = [p for p in projects
               if p.get("stage") not in PROJECT_DONE
               and (lc.parse_date(p.get("target_date")) or date.max) < today]
    active_projects = [p for p in projects if p.get("stage") not in PROJECT_DONE]
    kpis = [
        kpi("orders_placed", "Vendor orders placed", len(in_range), None),
        kpi("open_orders", "Open vendor orders", len(open_orders), None),
        kpi("in_production_value", "Value in production",
            round(sum(lc.money(o.get("final_total")) for o in open_orders)), None, "money"),
        kpi("vendor_balance", "Owed to vendors", round(balance), None, "money"),
        kpi("active_projects", "Active projects", len(active_projects), None),
        kpi("overdue_projects", "Projects past target date", len(overdue), None),
    ]
    status_counts = Counter(o.get("status") for o in orders)
    by_status = [{"name": s, "value": status_counts.get(s, 0)} for s in MO_STATUSES]
    per_vendor = defaultdict(lambda: [0.0, 0, 0.0])
    for o in in_range:
        v = per_vendor[label(o)]
        v[0] += lc.money(o.get("final_total"))
        v[1] += 1
        v[2] += lc.money(o.get("total_balance_due")) if o.get("total_balance_due") is not None else 0
    vendors = [{"name": k, "value": round(x[0]), "orders": x[1], "balance": round(x[2])}
               for k, x in sorted(per_vendor.items(), key=lambda kv: -kv[1][0])[:10]]
    stage_counts = Counter(p.get("stage") for p in projects)
    by_stage = [{"name": s, "value": stage_counts.get(s, 0)} for s in PROJECT_STAGES]
    overdue_rows = sorted(({"name": _name(p.get("customer"), "Unknown"), "project_no": p.get("project_no", ""),
                            "stage": p.get("stage", ""), "target_date": p.get("target_date", ""),
                            "days_late": (today - lc.parse_date(p.get("target_date"))).days}
                           for p in overdue), key=lambda r: -r["days_late"])[:15]
    return {"granularity": granularity(start, end), "kpis": kpis, "series": {},
            "tables": {"orders_by_status": by_status, "top_vendors": vendors,
                       "projects_by_stage": by_stage, "overdue_projects": overdue_rows}}


# ── division sales tracker (the Paints Sales Tracker, for any division) ────
TRACKER_CATEGORIES = ("Pending", "Active", "Won", "Lost")
_ACTIVE_WORDS = ("negot", "follow", "visit", "sample", "design", "site", "revis", "active", "discuss")


def tracker_category(q: dict, won_quote_ids: set) -> str:
    """Pending → Active → Won / Lost, as the tracker's Category column."""
    status = lc.quote_status(q)
    if q.get("id") in won_quote_ids or status == "Won":
        return "Won"
    if status in ("Lost", "Expired"):
        return "Lost"
    stage = str(q.get("stage") or "").lower()
    if status == "Negotiation" or any(w in stage for w in _ACTIVE_WORDS) or q.get("log"):
        return "Active"
    return "Pending"


def _quarter(d: date) -> str:
    """Indian financial-year quarter: Apr–Jun is Q1."""
    fy = d.year if d.month >= 4 else d.year - 1
    return f"FY{str(fy + 1)[-2:]} Q{(d.month - 4) % 12 // 3 + 1}"


def _last_note(q: dict) -> str:
    log = q.get("log") or []
    for e in reversed(log):
        text = str((e or {}).get("text") or (e or {}).get("note") or (e or {}).get("message") or "").strip()
        if text:
            return text[:160]
    return str(q.get("remarks") or "").strip()[:160]


def division_tracker(quotes: list[dict], sales: list[dict], projects: list[dict], calls: list[dict],
                     sft_by_quote: dict, start: date, end: date, *, division: str = "",
                     today: Optional[date] = None) -> dict:
    """Every sheet of the Paints Sales Tracker from CRM records.

    quotes / sales / calls are counted when dated inside [start, end];
    projects (the applicator / site schedule) when they overlap it or are
    still running. sft_by_quote: {quote id: total sft of its lines}."""
    today = today or date.today()
    quotes = [q for q in quotes if _division_ok(q, division)]
    sales = [s for s in sales if _division_ok(s, division)
             and str(s.get("status") or s.get("stage") or "") != "Cancelled"]
    projects = [p for p in projects if _division_ok(p, division)]
    calls = [c for c in calls if _division_ok(c, division)]
    won_ids = {s.get("quote_id") for s in sales if s.get("quote_id")}
    quote_no = {q.get("id"): q.get("quote_no") for q in quotes if q.get("id")}

    def q_value(q):
        return lc.money(q.get("grand_total")) or lc.money(q.get("value"))

    def sft_of(doc):
        return round(lc.money(sft_by_quote.get(doc.get("quote_id") or doc.get("id"))), 2)

    cur_q = within(quotes, "date", start, end)
    cur_s = within(sales, "date", start, end)

    # Pipeline (prospects)
    pipeline, cats = [], {c: {"category": c, "count": 0, "value": 0.0, "sft": 0.0} for c in TRACKER_CATEGORIES}
    for d, q in sorted(cur_q, key=lambda x: -q_value(x[1])):
        cat = tracker_category(q, won_ids)
        val, sft = q_value(q), sft_of(q)
        c = cats[cat]
        c["count"] += 1
        c["value"] += val
        c["sft"] += sft
        pipeline.append({"id": q.get("id"), "quote_no": q.get("quote_no") or "", "client": _name(q.get("customer"), "—"),
                         "reference": q.get("reference") or "", "next_step": _last_note(q),
                         "next_follow_up": q.get("next_follow_up") or "", "value": round(val), "sft": sft,
                         "stage": q.get("stage") or "", "category": cat, "month": d.strftime("%b %Y"),
                         "priority": q.get("confidence_level") or "", "date": d.isoformat()})
    total_q = sum(c["value"] for c in cats.values())
    breakdown = [{**c, "value": round(c["value"]), "sft": round(c["sft"], 2),
                  "share": pct(c["value"], total_q)} for c in cats.values()]
    open_value = cats["Pending"]["value"] + cats["Active"]["value"]

    # Sales register (confirmed orders)
    register = []
    for d, s in sorted(cur_s, key=lambda x: x[0], reverse=True):
        value, paid = lc.money(s.get("value")), lc.money(s.get("paid"))
        balance = lc.money(s.get("balance")) if s.get("balance") not in (None, "") else max(value - paid, 0)
        register.append({"id": s.get("id"), "sale_no": s.get("sale_no") or "", "client": _name(s.get("customer"), "—"),
                         "quote_no": s.get("quote_ref") or quote_no.get(s.get("quote_id")) or "",
                         "date": d.isoformat(), "value": round(value),
                         "sft": sft_of(s), "advance": round(paid), "balance": round(balance),
                         "collected_pct": pct(paid, value), "status": s.get("stage") or s.get("status") or ""})
    revenue = sum(r["value"] for r in register)
    advance = sum(r["advance"] for r in register)
    balance = sum(r["balance"] for r in register)
    sft_total = round(sum(r["sft"] for r in register), 2)

    # Applicator / site schedule
    schedule = []
    for p in projects:
        s_d = lc.parse_date(p.get("start_date"))
        e_d = lc.parse_date(p.get("completion_date")) or lc.parse_date(p.get("target_date"))
        done = str(p.get("stage") or "") in ("Completed", "Closure")
        if s_d and s_d > end:
            continue
        if e_d and e_d < start and done:
            continue
        if not s_d and done:
            continue
        days = (e_d - s_d).days + 1 if s_d and e_d and e_d >= s_d else None
        schedule.append({"id": p.get("id"), "site": _name(p.get("project_name") or p.get("customer"), "—"),
                         "applicator": p.get("assigned_engineer") or p.get("project_manager") or "",
                         "start": s_d.isoformat() if s_d else "", "end": e_d.isoformat() if e_d else "",
                         "days": days, "sft": sft_of(p), "status": p.get("stage") or "",
                         "overdue": bool(e_d and e_d < today and not done)})
    schedule.sort(key=lambda r: (r["start"] or "9999", r["site"]))

    # Weekly activity log
    log = []
    for d, q in cur_q:
        log.append({"date": d.isoformat(), "client": _name(q.get("customer"), "—"), "activity": "Quotation sent",
                    "quote_value": round(q_value(q)), "order_value": 0, "advance": 0,
                    "status": q.get("stage") or "", "notes": q.get("quote_no") or ""})
        for e in q.get("log") or []:
            ed = lc.parse_date((e or {}).get("at") or (e or {}).get("date"))
            if ed and start <= ed <= end:
                log.append({"date": ed.isoformat(), "client": _name(q.get("customer"), "—"), "activity": "Follow-up",
                            "quote_value": round(q_value(q)), "order_value": 0, "advance": 0,
                            "status": q.get("stage") or "", "notes": _last_note({"log": [e]})})
    for d, s in cur_s:
        log.append({"date": d.isoformat(), "client": _name(s.get("customer"), "—"), "activity": "Order confirmed",
                    "quote_value": 0, "order_value": round(lc.money(s.get("value"))),
                    "advance": round(lc.money(s.get("paid"))), "status": s.get("stage") or s.get("status") or "",
                    "notes": s.get("sale_no") or ""})
    for d, c in within(calls, "date", start, end):
        log.append({"date": d.isoformat(), "client": _name(c.get("name") or c.get("company"), c.get("phone") or "—"),
                    "activity": c.get("call_type") or "Call", "quote_value": 0, "order_value": 0, "advance": 0,
                    "status": c.get("outcome") or "", "notes": str(c.get("notes") or "")[:160]})
    log.sort(key=lambda r: r["date"], reverse=True)
    for r in log:
        r["week"] = date.fromisoformat(r["date"]).isocalendar()[1]
    weeks = defaultdict(lambda: {"activities": 0, "quote_value": 0, "order_value": 0, "advance": 0})
    for r in log:
        y, w, _ = date.fromisoformat(r["date"]).isocalendar()
        k = weeks[f"{y}-W{w:02d}"]
        k["activities"] += 1
        for f in ("quote_value", "order_value", "advance"):
            k[f] += r[f]
    weekly = [{"week": k, **v} for k, v in sorted(weeks.items(), reverse=True)]

    # Monthly and quarterly summaries
    def roll(keyf):
        out = defaultdict(lambda: {"quotes": 0, "quote_value": 0, "orders": 0, "order_value": 0,
                                   "advance": 0, "balance": 0, "sft": 0.0})
        for d, q in cur_q:
            o = out[keyf(d)]
            o["quotes"] += 1
            o["quote_value"] += round(q_value(q))
        for r in register:
            o = out[keyf(date.fromisoformat(r["date"]))]
            o["orders"] += 1
            o["order_value"] += r["value"]
            o["advance"] += r["advance"]
            o["balance"] += r["balance"]
            o["sft"] = round(o["sft"] + r["sft"], 2)
        rows = []
        for k, v in sorted(out.items()):
            rows.append({"period": k, **v, "conversion": pct(v["order_value"], v["quote_value"]),
                         "collection_rate": pct(v["advance"], v["order_value"])})
        return rows

    monthly = roll(lambda d: d.strftime("%Y-%m"))
    for m in monthly:
        m["label"] = datetime.strptime(m["period"], "%Y-%m").strftime("%b %Y")
    quarterly = roll(_quarter)
    top = [r for r in pipeline if r["category"] in ("Pending", "Active")][:10]

    kpis = [
        kpi("pipeline", "Total pipeline", round(open_value), None, "money"),
        kpi("revenue", "Confirmed revenue", round(revenue), None, "money"),
        kpi("advance", "Advance collected", round(advance), None, "money"),
        kpi("balance", "Balance outstanding", round(balance), None, "money"),
        kpi("collection", "Collection rate", pct(advance, revenue), None, "percent"),
        kpi("sft", "Total sft", sft_total, None, "number"),
    ]
    return {"kpis": kpis, "tables": {"breakdown": breakdown, "pipeline": pipeline, "register": register,
                                     "schedule": schedule, "log": log[:500], "weekly": weekly,
                                     "monthly": monthly, "quarterly": quarterly, "top_prospects": top}}
