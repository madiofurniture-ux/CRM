"""Iter 5 regression: outstanding, dashboard/stats, analytics/inventory field checks."""
import os
import requests
import pytest
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "1234"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_outstanding_shape(headers):
    r = requests.get(f"{BASE_URL}/api/outstanding", headers=headers)
    assert r.status_code == 200
    d = r.json()
    for k in ("sales_outstanding", "invoice_outstanding", "hot_pipeline",
              "aging", "outstanding_sales", "outstanding_invoices", "hot_quotes"):
        assert k in d, f"Missing key {k}"
    assert isinstance(d["sales_outstanding"], (int, float))
    assert isinstance(d["invoice_outstanding"], (int, float))
    assert isinstance(d["hot_pipeline"], (int, float))
    # aging buckets
    bucket_names = {b["bucket"] for b in d["aging"]}
    assert bucket_names == {"0-30", "31-60", "61-90", "90+"}
    # per-item shape
    if d["outstanding_sales"]:
        s = d["outstanding_sales"][0]
        for k in ("id", "sale_no", "customer", "date", "balance"):
            assert k in s, f"sales missing {k}"
        # server-side filter check
        for s in d["outstanding_sales"]:
            assert (s.get("balance") or 0) > 0
    if d["outstanding_invoices"]:
        s = d["outstanding_invoices"][0]
        for k in ("id", "invoice_no", "customer", "date", "total", "paid", "balance"):
            assert k in s, f"invoice missing {k}"
        for s in d["outstanding_invoices"]:
            assert (s.get("balance") or 0) > 0
    if d["hot_quotes"]:
        q = d["hot_quotes"][0]
        for k in ("id", "quote_no", "customer", "stage", "value"):
            assert k in q, f"quote missing {k}"
        for q in d["hot_quotes"]:
            assert q["stage"] in ("Quoted", "Negotiation")
            assert (q.get("value") or 0) >= 100000


def test_dashboard_stats_shape(headers):
    r = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
    assert r.status_code == 200
    d = r.json()
    for k in ("pipeline_value", "total_sales", "total_paid", "outstanding",
              "stock_mrp", "stock_cost", "active_leads", "todays_visitors",
              "overdue_followups", "by_stage", "division_split", "monthly_revenue"):
        assert k in d, f"Missing key {k}"
    # non-zero for seeded DB
    assert d["pipeline_value"] > 0, "pipeline_value should be non-zero"
    assert d["total_sales"] > 0, "total_sales should be non-zero"
    assert d["stock_mrp"] > 0, "stock_mrp should be non-zero"
    assert d["stock_cost"] > 0, "stock_cost should be non-zero"
    assert d["active_leads"] > 0, "active_leads should be non-zero"
    assert isinstance(d["by_stage"], list) and len(d["by_stage"]) > 0
    assert isinstance(d["division_split"], list)
    assert isinstance(d["monthly_revenue"], list)


def test_inventory_analytics_shape(headers):
    r = requests.get(f"{BASE_URL}/api/analytics/inventory", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert d["total_items"] == 120, f"expected 120 items, got {d['total_items']}"
    assert d["total_qty"] > 0
    assert d["total_mrp"] > 0
    assert d["total_cost"] > 0, "total_cost should be > 0 (projection may have dropped cost field!)"
    for k in ("by_category", "by_vendor", "by_location", "by_status", "top_items"):
        assert k in d
    assert len(d["top_items"]) > 0
    it = d["top_items"][0]
    for k in ("sku", "name", "vendor", "qty", "mrp"):
        assert k in it, f"top_items missing {k}"
