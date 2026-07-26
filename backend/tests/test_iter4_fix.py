"""Iteration 4 regression: inventory_analytics loop variable rename defensive check."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "1234"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_inventory_analytics_shape(admin_token):
    r = requests.get(
        f"{BASE_URL}/api/analytics/inventory",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_items"] == 120, f"expected 120 items, got {data['total_items']}"
    assert isinstance(data["total_qty"], (int, float)) and data["total_qty"] > 0
    assert isinstance(data["total_mrp"], (int, float)) and data["total_mrp"] > 0
    assert isinstance(data["total_cost"], (int, float)) and data["total_cost"] > 0
    for key in ("by_category", "by_vendor", "by_location", "by_status", "top_items"):
        assert key in data, f"missing key {key}"
        assert isinstance(data[key], list), f"{key} not a list"
        assert len(data[key]) > 0, f"{key} is empty"
    # top_items should have inventory item shape (no _id)
    for it in data["top_items"]:
        assert "_id" not in it
