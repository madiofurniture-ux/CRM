"""End-to-end money lineage: one deal from visitor to profit, and the company P&L.

Pure functions over already-fetched, tenant-scoped documents (server.py does
the reads). The chain follows the links the records already carry:

    visitor ─(lead.visitor_id / phone)─> lead ─(quote.lead_id)─> quotation
    ─(sale.quote_id)─> sales order ─(project.sale_id)─> project
    ─(project_id)─> vendor orders (manufacturer orders) and purchase orders
    ─(project_id / sale_id / quote_id)─> expenses (cashbook payouts, petty cash,
    money requests) ─(payment.against_sale_id)─> customer payments ─> P&L

Money rules, shared with csv_engine.compute_project_pnl so the two agree:
  * revenue = sales order value; before a sale exists, the project's contract
    value, else the latest quotation (flagged as an estimate);
  * vendor cost = committed POs (grand_total) + committed vendor orders
    (final_total) — drafts, quotes and cancellations are not money owed;
  * expenses = Approved CASH_OUT (excluding vendor-order payouts, which are
    already in vendor cost) + Approved petty-cash Out vouchers;
  * gross margin = revenue − vendor cost (sale value − total PO cost);
    net margin = gross margin − expenses − incentives.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

import lifecycle as lc
from models import MO_COMMITTED_STATUSES, PO_COMMITTED_STATUSES

OPEN_REQUEST_STATUSES = {"Pending review", "Pending transfer"}
# Figures that reveal field-settlement (petty cash) spend. Hidden in privacy
# mode, the same family csv_engine.mask_pnl hides: every figure that would
# let the spend be recomputed goes with it.
DEAL_MASKED_FIELDS = ("expenses", "pending_expenses", "net_margin", "net_margin_pct")
COMPANY_MASKED_FIELDS = ("project_expenses", "overheads", "net_profit", "net_margin_pct")


def _m(v) -> float:
    return lc.money(v)


def entry_cost(entries: Iterable[dict]) -> tuple[float, float]:
    """(approved, pending) CASH_OUT spend, excluding vendor-order payouts."""
    approved = pending = 0.0
    for e in entries:
        if e.get("type") != "CASH_OUT" or e.get("manufacturer_order_id"):
            continue
        if e.get("status") == "Approved":
            approved += _m(e.get("amount"))
        elif e.get("status") == "Pending":
            pending += _m(e.get("amount"))
    return approved, pending


def petty_cost(vouchers: Iterable[dict]) -> tuple[float, float]:
    approved = pending = 0.0
    for v in vouchers:
        if v.get("kind", "Out") != "Out":
            continue
        if v.get("status", "Approved") == "Approved":
            approved += _m(v.get("amount"))
        elif v.get("status") == "Pending":
            pending += _m(v.get("amount"))
    return approved, pending


def vendor_cost(pos: Iterable[dict], mos: Iterable[dict]) -> float:
    return round(sum(_m(p.get("grand_total")) for p in pos if p.get("status") in PO_COMMITTED_STATUSES)
                 + sum(_m(m.get("final_total")) for m in mos if m.get("status") in MO_COMMITTED_STATUSES), 2)


def _pct(part: float, whole: float) -> Optional[float]:
    return round(100.0 * part / whole, 1) if whole else None


def _node(key: str, label: str, *, done: bool, title: str = "", date_: str = "", amount=None,
          detail: str = "", ref: dict = None, items: list = None) -> dict:
    d = lc.parse_date(date_) if date_ else None      # legacy rows carry junk like "nan"
    return {"key": key, "label": label, "done": done, "title": title, "date": d.isoformat() if d else "",
            "amount": amount, "detail": detail, "ref": ref or {}, "items": items or []}


def deal_lineage(*, visitor: Optional[dict], lead: Optional[dict], quotes: list, sales: list,
                 project: Optional[dict], pos: list, mos: list, entries: list, petty: list,
                 requests: list, payments: list, payouts: list) -> dict:
    """The chain and P&L for one deal. Lists are already narrowed to this deal."""
    quotes = sorted(quotes, key=lambda q: str(q.get("date") or q.get("created_at") or ""))
    sales_value = sum(_m(s.get("value")) for s in sales)
    if sales:
        revenue, revenue_basis = sales_value, "sales order"
    elif project and _m(project.get("value")):
        revenue, revenue_basis = _m(project.get("value")), "project contract"
    elif quotes:
        latest = quotes[-1]
        revenue = _m(latest.get("grand_total") or latest.get("value"))
        revenue_basis = "quotation (estimate)"
    else:
        revenue, revenue_basis = 0.0, "none yet"

    v_cost = vendor_cost(pos, mos)
    e_appr, e_pend = entry_cost(entries)
    p_appr, p_pend = petty_cost(petty)
    open_requests = [r for r in requests if r.get("status") in OPEN_REQUEST_STATUSES]
    expenses = round(e_appr + p_appr, 2)
    pending_expenses = round(e_pend + p_pend + sum(_m(r.get("amount")) for r in open_requests), 2)
    incentives = round(sum(_m(p.get("commission_amount")) for p in payouts
                           if p.get("status") in ("Approved", "Paid")), 2)
    received = sum(_m(p.get("amount")) for p in payments if p.get("direction", "In") == "In")
    refunded = sum(_m(p.get("amount")) for p in payments if p.get("direction") in ("Out", "Refund"))
    collected = round(received - refunded, 2) if payments \
        else round(sum(_m(s.get("paid")) for s in sales), 2)
    gross = round(revenue - v_cost, 2)
    net = round(gross - expenses - incentives, 2)
    vendor_paid = round(sum(_m(m.get("total_paid")) for m in mos), 2)
    vendor_due = round(sum(_m(m.get("total_balance_due")) for m in mos
                           if m.get("status") in MO_COMMITTED_STATUSES), 2)

    pnl = {
        "revenue": round(revenue, 2), "revenue_basis": revenue_basis,
        "vendor_cost": v_cost, "gross_margin": gross, "gross_margin_pct": _pct(gross, revenue),
        "expenses": expenses, "pending_expenses": pending_expenses, "incentives": incentives,
        "net_margin": net, "net_margin_pct": _pct(net, revenue),
        "collected": collected, "receivable": round(max(revenue - collected, 0), 2) if sales else None,
        "vendor_paid": vendor_paid, "vendor_due": vendor_due,
    }

    exp_items = (
        [{"date": e.get("approved_at") or e.get("created_at"), "title": e.get("remark") or e.get("category"),
          "category": e.get("category", ""), "amount": _m(e.get("amount")), "status": e.get("status", ""),
          "source": "Money request" if e.get("money_request_id") else "Wallet"}
         for e in entries if e.get("type") == "CASH_OUT" and not e.get("manufacturer_order_id")]
        + [{"date": v.get("date"), "title": v.get("description") or v.get("category"),
            "category": v.get("category", ""), "amount": _m(v.get("amount")),
            "status": v.get("status", "Approved"), "source": "Petty cash"}
           for v in petty if v.get("kind", "Out") == "Out"]
        + [{"date": r.get("date"), "title": r.get("title"), "category": r.get("category", ""),
            "amount": _m(r.get("amount")), "status": r.get("status"), "source": "Open request",
            "request_no": r.get("request_no", "")}
           for r in open_requests])
    exp_items.sort(key=lambda x: str(x.get("date") or ""), reverse=True)

    chain = [
        _node("visitor", "Visitor", done=bool(visitor),
              title=(visitor or {}).get("name", ""), date_=(visitor or {}).get("date", ""),
              detail=(visitor or {}).get("requirement", ""), ref={"id": (visitor or {}).get("id")}),
        _node("lead", "Lead", done=bool(lead), title=(lead or {}).get("name", ""),
              date_=(lead or {}).get("date", ""),
              detail=" · ".join(x for x in ((lead or {}).get("stage", ""), (lead or {}).get("source", "")) if x),
              amount=_m((lead or {}).get("value")) or None, ref={"id": (lead or {}).get("id")}),
        _node("quote", "Quotation", done=bool(quotes),
              title=", ".join(q.get("quote_no", "") for q in quotes[-3:]),
              date_=(quotes[-1] if quotes else {}).get("date", ""),
              amount=_m((quotes[-1] if quotes else {}).get("grand_total")
                        or (quotes[-1] if quotes else {}).get("value")) or None,
              detail=(quotes[-1] if quotes else {}).get("stage", ""),
              items=[{"id": q.get("id"), "no": q.get("quote_no"), "stage": q.get("stage"),
                      "amount": _m(q.get("grand_total") or q.get("value"))} for q in quotes]),
        _node("sale", "Sales order", done=bool(sales), title=", ".join(s.get("sale_no", "") for s in sales),
              date_=(sales[0] if sales else {}).get("date", ""), amount=round(sales_value, 2) if sales else None,
              detail=(sales[0] if sales else {}).get("status", ""),
              items=[{"id": s.get("id"), "no": s.get("sale_no"), "amount": _m(s.get("value")),
                      "paid": _m(s.get("paid")), "status": s.get("status")} for s in sales]),
        _node("vendor", "Vendor orders", done=bool(pos or mos), amount=v_cost or None,
              title=f"{len(mos)} vendor order(s), {len(pos)} PO(s)" if (pos or mos) else "",
              detail=f"Paid ₹{vendor_paid:,.0f} · due ₹{vendor_due:,.0f}" if mos else "",
              items=[{"no": m.get("order_code"), "vendor": m.get("vendor_name") or m.get("vendor_code"),
                      "status": m.get("status"), "amount": _m(m.get("final_total"))} for m in mos]
              + [{"no": p.get("po_no"), "vendor": p.get("vendor_name") or p.get("vendor_code"),
                  "status": p.get("status"), "amount": _m(p.get("grand_total"))} for p in pos]),
        _node("project", "Project", done=bool(project), title=(project or {}).get("project_no", ""),
              date_=(project or {}).get("start_date", ""), detail=(project or {}).get("stage", ""),
              ref={"id": (project or {}).get("id")}),
        _node("expenses", "Expenses", done=bool(exp_items), amount=expenses or None,
              title=f"{len(exp_items)} item(s)" if exp_items else "",
              detail=f"₹{pending_expenses:,.0f} awaiting approval or payout" if pending_expenses else "",
              items=exp_items[:50]),
        _node("payment", "Customer payments", done=bool(payments) or collected > 0, amount=collected or None,
              title=f"{len(payments)} receipt(s)" if payments else "",
              detail=f"₹{pnl['receivable']:,.0f} still to collect" if pnl["receivable"] else "",
              items=[{"date": p.get("date"), "amount": _m(p.get("amount")), "mode": p.get("mode"),
                      "id": p.get("payment_id") or p.get("id")} for p in payments]),
        _node("pnl", "Profit", done=bool(sales), amount=net,
              detail=f"{pnl['net_margin_pct']}% net margin" if pnl["net_margin_pct"] is not None else ""),
    ]
    customer = (sales[0] if sales else {}).get("customer") or (project or {}).get("customer") \
        or (quotes[-1] if quotes else {}).get("customer") or (lead or {}).get("name") or (visitor or {}).get("name", "")
    return {"customer": customer, "chain": chain, "pnl": pnl}


def mask_deal(out: dict) -> dict:
    pnl = {**out["pnl"], **{f: None for f in DEAL_MASKED_FIELDS}}
    chain = []
    for n in out["chain"]:
        if n["key"] == "expenses":
            n = {**n, "amount": None, "detail": "", "items": []}
        elif n["key"] == "pnl":
            n = {**n, "amount": None, "detail": ""}
        chain.append(n)
    return {**out, "pnl": pnl, "chain": chain, "masked": True}


# ── company P&L ────────────────────────────────────────────────────────────
def _in(d: Optional[date], start: date, end: date) -> bool:
    return bool(d) and start <= d <= end


def company_pnl(*, sales: list, pos: list, mos: list, entries: list, petty: list, payouts: list,
                book_project: dict, projects: dict, start: date, end: date, division: str = "") -> dict:
    """Revenue (sales orders by date), direct cost (vendor orders/POs by date,
    project expenses by date), overheads (spend not tied to a project), and
    incentives, for [start, end]. `book_project` maps cashbook id -> project id;
    `projects` maps project id -> project (for division)."""
    def div_ok(doc_div: str) -> bool:
        return not division or lc.norm_division(doc_div) == division

    months: dict[str, dict] = defaultdict(lambda: defaultdict(float))

    def add(d: date, field: str, amount: float):
        months[d.strftime("%Y-%m")][field] += amount

    revenue = 0.0
    by_division = defaultdict(lambda: defaultdict(float))
    for s in sales:
        d = lc.parse_date(s.get("date"))
        if _in(d, start, end) and div_ok(s.get("division")):
            v = _m(s.get("value"))
            revenue += v
            add(d, "revenue", v)
            by_division[lc.norm_division(s.get("division"))]["revenue"] += v

    vendor = 0.0
    for p in pos:
        d = lc.parse_date(p.get("date"))
        if p.get("status") in PO_COMMITTED_STATUSES and _in(d, start, end) and div_ok(p.get("division")):
            v = _m(p.get("grand_total"))
            vendor += v
            add(d, "vendor_cost", v)
            by_division[lc.norm_division(p.get("division"))]["vendor_cost"] += v
    for m in mos:
        d = lc.parse_date(m.get("date"))
        if m.get("status") in MO_COMMITTED_STATUSES and _in(d, start, end) and div_ok(m.get("division")):
            v = _m(m.get("final_total"))
            vendor += v
            add(d, "vendor_cost", v)
            by_division[lc.norm_division(m.get("division"))]["vendor_cost"] += v

    project_exp = overheads = 0.0
    overhead_by_cat: dict[str, float] = defaultdict(float)
    project_by_cat: dict[str, float] = defaultdict(float)

    def spend(d, amount, pid, category, doc_div):
        nonlocal project_exp, overheads
        proj = projects.get(pid) if pid else None
        dv = (proj or {}).get("division") or doc_div
        if not _in(d, start, end) or not div_ok(dv):
            return
        if pid:
            project_exp += amount
            project_by_cat[category or "Other"] += amount
            add(d, "project_expenses", amount)
            by_division[lc.norm_division(dv)]["expenses"] += amount
        else:
            overheads += amount
            overhead_by_cat[category or "Other"] += amount
            add(d, "overheads", amount)

    for e in entries:
        if e.get("type") != "CASH_OUT" or e.get("status") != "Approved" or e.get("manufacturer_order_id"):
            continue
        d = lc.parse_date(e.get("approved_at") or e.get("created_at"))
        pid = e.get("project_id") or book_project.get(e.get("cashbook_id"), "")
        spend(d, _m(e.get("amount")), pid, e.get("category"), "")
    for v in petty:
        if v.get("kind", "Out") != "Out" or v.get("status", "Approved") != "Approved":
            continue
        spend(lc.parse_date(v.get("date")), _m(v.get("amount")), v.get("project_id") or "",
              v.get("category"), "")

    incentives = 0.0
    for p in payouts:
        if p.get("status") not in ("Approved", "Paid"):
            continue
        d = lc.parse_date(p.get("paid_at") or p.get("approved_at") or p.get("created_at"))
        proj = projects.get(p.get("project_id") or "")
        if _in(d, start, end) and div_ok((proj or {}).get("division") or p.get("division")):
            v = _m(p.get("commission_amount"))
            incentives += v
            add(d, "incentives", v)

    gross = revenue - vendor - project_exp
    net = gross - overheads - incentives
    month_keys = []
    y, mth = start.year, start.month
    while (y, mth) <= (end.year, end.month):
        month_keys.append(f"{y:04d}-{mth:02d}")
        y, mth = (y + 1, 1) if mth == 12 else (y, mth + 1)
    series = []
    for k in month_keys:
        row = months.get(k, {})
        r = {f: round(row.get(f, 0.0), 2) for f in
             ("revenue", "vendor_cost", "project_expenses", "overheads", "incentives")}
        r["net_profit"] = round(r["revenue"] - r["vendor_cost"] - r["project_expenses"]
                                - r["overheads"] - r["incentives"], 2)
        r["month"] = k
        r["label"] = date(int(k[:4]), int(k[5:]), 1).strftime("%b %Y")
        series.append(r)
    divisions = [{"name": k, "revenue": round(v["revenue"], 2), "vendor_cost": round(v["vendor_cost"], 2),
                  "expenses": round(v["expenses"], 2),
                  "gross_margin": round(v["revenue"] - v["vendor_cost"] - v["expenses"], 2)}
                 for k, v in sorted(by_division.items(), key=lambda kv: -kv[1]["revenue"])]
    return {
        "statement": {
            "revenue": round(revenue, 2), "vendor_cost": round(vendor, 2),
            "project_expenses": round(project_exp, 2), "gross_profit": round(gross, 2),
            "gross_margin_pct": _pct(gross, revenue),
            "overheads": round(overheads, 2), "incentives": round(incentives, 2),
            "net_profit": round(net, 2), "net_margin_pct": _pct(net, revenue),
        },
        "series": series,
        "by_division": divisions,
        "overheads_by_category": [{"name": k, "amount": round(v, 2)}
                                  for k, v in sorted(overhead_by_cat.items(), key=lambda kv: -kv[1])],
        "project_expenses_by_category": [{"name": k, "amount": round(v, 2)}
                                         for k, v in sorted(project_by_cat.items(), key=lambda kv: -kv[1])],
    }


def mask_company(out: dict) -> dict:
    """Privacy mode: hide spend and everything computed from it. Revenue and
    vendor cost (official, invoiced legs) stay; gross profit includes project
    expenses, so it goes too."""
    st = {**out["statement"], **{f: None for f in COMPANY_MASKED_FIELDS},
          "gross_profit": None, "gross_margin_pct": None}
    series = [{**r, "project_expenses": None, "overheads": None, "net_profit": None} for r in out["series"]]
    divisions = [{**d, "expenses": None, "gross_margin": None} for d in out["by_division"]]
    return {**out, "statement": st, "series": series, "by_division": divisions,
            "overheads_by_category": [], "project_expenses_by_category": [], "masked": True}
