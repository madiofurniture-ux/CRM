"""Unit tests for the pure lifecycle domain logic.

These pin the behaviours the live web CRM depends on: forgiving date parsing, number-vs-string
coercion, timestamp-corruption guards, the derived quote-status axis, and the reporting /
alert / journey aggregations. No Mongo, no FastAPI — just the rules.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc


# -------------------------------------------------------------- date parsing
def test_parse_iso_and_dmy():
    assert lc.parse_date("2026-03-22") == date(2026, 3, 22)
    assert lc.parse_date("22/03/26") == date(2026, 3, 22)
    assert lc.parse_date("22-03-2026") == date(2026, 3, 22)


def test_parse_real_world_typos_never_raise():
    # These exact strings exist in production data.
    assert lc.parse_date("24/o1/2026") == date(2026, 1, 24)   # letter o for zero
    assert lc.parse_date("17/01.2026") == date(2026, 1, 17)   # dot separator
    assert lc.parse_date("18/10/2025/") == date(2025, 10, 18)  # trailing slash
    assert lc.parse_date("garbage") is None
    assert lc.parse_date("") is None
    assert lc.parse_date(None) is None


def test_parse_invalid_day_returns_none_not_crash():
    assert lc.parse_date("45/13/2026") is None


# --------------------------------------------------------- number coercion
def test_norm_phone_accepts_number_type():
    # Sheets round-trips phones as numbers; string ops must still work.
    assert lc.norm_phone(9100000000) == "9100000000"
    assert lc.norm_phone("+91 91000 00000") == "919100000000"


def test_phone_key_folds_country_code():
    assert lc.phone_key("+91 9100000000") == lc.phone_key("09100000000")
    assert lc.phone_key("9100000000") == "9100000000"


def test_money_treats_timestamp_as_zero():
    assert lc.money(150000) == 150000
    assert lc.money(1782764347387) == 0        # a leaked Unix ms timestamp
    assert lc.money("not a number") == 0
    assert lc.money(None) == 0


# ------------------------------------------------------------ document ids
def test_next_quote_no_increments_within_month():
    ym = lc.yymm()
    quotes = [{"quote_no": f"AF-{ym}-001"}, {"quote_no": f"AF-{ym}-004"}, {"quote_no": "AF-0101-099"}]
    assert lc.next_quote_no(quotes) == f"AF-{ym}-005"


def test_next_sale_no_is_one_running_series():
    assert lc.next_sale_no([{"sale_no": "MF 110"}, {"sale_no": "MF 057"}]) == "MF 111"
    assert lc.next_sale_no([]) == "MF 001"


# ------------------------------------------------------- quote status axis
def test_quote_status_derivation():
    assert lc.quote_status({"stage": "Quoted"}) == "Sent"
    assert lc.quote_status({"stage": "Cancelled"}) == "Lost"
    assert lc.quote_status({"stage": "Delivered"}) == "Won"
    assert lc.quote_status({"stage": "Adv Received"}) == "Won"
    assert lc.quote_status({"stage": "Quoted", "status": "Negotiation"}) == "Negotiation"


def test_sanitize_quote_guards_corruption():
    q = lc.sanitize_quote({"value": 1782764347387, "stage": 42})
    assert q["value"] == 0
    assert q["stage"] == "Quoted"
    assert q["status"] == "Sent"
    assert q["version"] == 1


def test_quote_due_flag():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert lc.quote_due_flag({"stage": "Quoted", "next_action_date": yesterday}) == "overdue"
    old = (date.today() - timedelta(days=5)).isoformat()
    assert lc.quote_due_flag({"stage": "Quoted", "date": old}) == "stale"
    assert lc.quote_due_flag({"stage": "Delivered"}) == ""


def test_quote_view_predicates():
    ym = lc.yymm()
    hot = {"stage": "Quoted", "value": 300000}
    assert lc.quote_view_predicate("hot", hot)
    assert not lc.quote_view_predicate("hot", {"stage": "Quoted", "value": 50000})
    won_today = {"stage": "Delivered", "date": date.today().isoformat()}
    assert lc.quote_view_predicate("wonmtd", won_today)


# -------------------------------------------------------------- quote lines
def test_calc_line_bills_by_area_when_dimensioned():
    line = lc.calc_line({"w": 2, "h": 3, "qty": 2, "rate": 100})
    assert line["sft"] == 12            # 2*3*2
    assert line["amount"] == 1200       # 12 sft * 100
    flat = lc.calc_line({"w": 0, "h": 0, "qty": 5, "rate": 20})
    assert flat["sft"] == 0
    assert flat["amount"] == 100        # falls back to qty*rate


def test_needs_approval_threshold():
    assert lc.needs_approval(100000, 15000)      # 15% > 10%
    assert not lc.needs_approval(100000, 5000)   # 5% < 10%
    assert not lc.needs_approval(0, 5000)


# --------------------------------------------------------------- D&W openings
def test_calc_opening_inches_to_sqft():
    o = lc.calc_opening({"w": 48, "h": 60, "qty": 2})
    assert o["area"] == 40.0            # 48*60*2 / 144


# --------------------------------------------------------------- reporting
def test_build_report_rolls_up_by_division():
    today = date.today().isoformat()
    leads = [{"division": "Furniture", "intake_date": today, "stage": "New"}]
    quotes = [{"division": "MAP", "date": today, "value": 200000}]
    sales = [{"division": "Furniture", "date": today, "value": 150000, "paid": 50000, "balance": 100000}]
    payments = [{"division": "Furniture", "date": today, "amount": 20000, "direction": "In"}]
    r = lc.build_report("thismonth", leads, quotes, sales, payments)
    assert r["divisions"]["Furniture"]["leads"] == 1
    assert r["divisions"]["MAP"]["qval"] == 200000
    assert r["divisions"]["Furniture"]["collected"] == 70000   # 50k paid + 20k payment
    assert r["divisions"]["Furniture"]["due"] == 100000
    assert r["divisions"]["TOTAL"]["quotes"] == 1


def test_whatsapp_summary_is_pasteable():
    r = lc.build_report("alltime", [], [{"division": "Furniture", "date": date.today().isoformat(), "value": 100000}], [], [])
    text = lc.whatsapp_summary(r)
    assert "MADIO" in text
    assert "TOTAL" in text
    assert "₹1.00L" in text


# --------------------------------------------------------------- outstanding
def test_aging_bucket():
    assert lc.aging_bucket(15) == "0-30"
    assert lc.aging_bucket(45) == "31-60"
    assert lc.aging_bucket(200) == "90+"
    assert lc.aging_bucket(None) == "90+"


def test_sale_phone_falls_back_to_quote():
    quotes_by_no = {"AF-2603-001": {"phone": "9247709216"}}
    sale = {"phone": "", "quote_ref": "AF-2603-001"}
    assert lc.sale_phone(sale, quotes_by_no) == "9247709216"
    assert lc.sale_phone({"phone": "9100000000"}, {}) == "9100000000"
    assert lc.sale_phone({"phone": "", "quote_ref": "missing"}, {}) == ""


def test_legacy_zero_paid_balance_not_flagged():
    assert not lc.balance_is_meaningful({"paid": 0, "balance": 0, "value": 500000})
    assert lc.balance_is_meaningful({"paid": 50000, "balance": 100000, "value": 150000})


# --------------------------------------------------------------- alerts
def test_build_alerts_orders_and_groups():
    today = date.today()
    leads = [
        {"id": "1", "name": "Overdue Guy", "phone": "9100000001", "stage": "New",
         "next_action_date": (today - timedelta(days=2)).isoformat(), "source": "Walk-in"},
        {"id": "2", "name": "Today Guy", "phone": "9100000002", "stage": "Contacted",
         "next_action_date": today.isoformat(), "source": "Navaki"},
    ]
    sales = [{"id": "s1", "customer": "Big Balance", "sale_no": "MF 001", "phone": "9100000003",
              "value": 500000, "paid": 100000, "balance": 400000, "stage": "Partial"}]
    quotes = [{"id": "q1", "customer": "Fat Quote", "quote_no": "AF-2603-009", "phone": "9100000004",
               "value": 300000, "stage": "Quoted", "by_user": "Raghu"}]
    inventory = [{"status": "Available", "date_added": (today - timedelta(days=120)).isoformat(), "mrp": 50000}]
    alerts = lc.build_alerts(leads, [], sales, quotes, inventory)
    groups = [a["group"] for a in alerts]
    assert groups[0] == "overdue"          # ordering
    assert "money" in groups
    money_alerts = [a for a in alerts if a["group"] == "money"]
    assert any("Dead stock" in a["title"] for a in money_alerts)


# --------------------------------------------------------------- journey
def test_build_journey_joins_by_phone_and_totals():
    ph = "9100000000"
    j = lc.build_journey(
        ph,
        visitors=[{"phone": ph, "date": "2026-01-01", "requirement": "Sofa", "attend_person": "Raghu"}],
        leads=[{"phone": "+91 " + ph, "intake_date": "2026-01-02", "name": "Ravi", "stage": "Qualified", "lead_id": "LD-2601-001", "division": "Furniture"}],
        quotes=[{"phone": ph, "date": "2026-01-05", "quote_no": "AF-2601-001", "value": 150000, "division": "Furniture", "stage": "Quoted"}],
        sales=[{"phone": ph, "date": "2026-01-10", "sale_no": "MF 001", "value": 150000, "paid": 50000, "balance": 100000}],
        payments=[{"phone": ph, "date": "2026-01-10", "amount": 50000, "mode": "Bank", "against_quote_no": "AF-2601-001"}],
        activities=[],
    )
    assert j["name"] == "Ravi"
    assert j["totals"]["quoted"] == 150000
    assert j["totals"]["sold"] == 150000
    assert j["totals"]["balance"] == 100000
    # events sorted chronologically across all datasets
    kinds = [e["kind"] for e in j["events"]]
    assert kinds[0] == "Walk-in visit"
    assert kinds[-1] in ("Sale", "Payment")
