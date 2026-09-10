"""Unit tests for the data-health invariant audit (pure logic, no Mongo/FastAPI)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lifecycle as lc


def _all_passed(results):
    return all(r["status"] == "passed" for r in results)


def test_clean_data_passes_every_check():
    results = lc.data_health_checks(
        inventory=[{"sku": "SKU-1", "qty": 5}],
        invoices=[{"invoice_no": "INV-1", "subtotal": 100, "discount_total": 0,
                   "cgst": 9, "sgst": 9, "igst": 0, "total": 118, "paid": 100, "balance": 18}],
        sales=[{"sale_no": "S-1", "value": 500, "paid": 200, "balance": 300}],
        leads=[{"name": "Asha", "stage": "Won"}],
    )
    assert len(results) == 6
    assert _all_passed(results)


def test_negative_stock_is_flagged():
    results = lc.data_health_checks(
        inventory=[{"sku": "SKU-BAD", "qty": -3}], invoices=[], sales=[], leads=[])
    check = next(r for r in results if r["name"] == "Stock quantity never negative")
    assert check["status"] == "failed"
    assert "SKU-BAD" in check["message"]


def test_invoice_balance_mismatch_is_flagged():
    results = lc.data_health_checks(
        inventory=[], invoices=[{"invoice_no": "INV-2", "total": 100, "paid": 40, "balance": 999}],
        sales=[], leads=[])
    check = next(r for r in results if r["name"] == "Balance equals total minus paid")
    assert check["status"] == "failed"
    assert "INV-2" in check["message"]


def test_overpaid_sale_is_flagged():
    results = lc.data_health_checks(
        inventory=[], invoices=[], sales=[{"sale_no": "S-9", "value": 100, "paid": 150, "balance": -50}],
        leads=[])
    check = next(r for r in results if r["name"] == "Paid never exceeds sale value")
    assert check["status"] == "failed"
    assert "S-9" in check["message"]


def test_unknown_lead_stage_is_flagged():
    results = lc.data_health_checks(
        inventory=[], invoices=[], sales=[], leads=[{"name": "Ravi", "stage": "Ghosted"}])
    check = next(r for r in results if r["name"] == "Stage is a known funnel value")
    assert check["status"] == "failed"
    assert "Ravi" in check["message"]
