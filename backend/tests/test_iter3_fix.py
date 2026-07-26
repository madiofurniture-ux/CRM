"""Iteration 3 targeted re-test: attendance check-out duration_min."""
import os
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def raghu_ctx():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "raghu", "pin": "2222"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {
        "h": {"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"},
        "user_id": data["user"]["id"],
    }


def test_check_out_duration_immediate(db, raghu_ctx):
    # Clean today's attendance for raghu
    today = datetime.now(timezone.utc).date().isoformat()
    db.attendance.delete_many({"user_id": raghu_ctx["user_id"], "date": today})

    # Check-in
    r = requests.post(f"{BASE_URL}/api/attendance/check-in",
                     headers=raghu_ctx["h"],
                     json={"lat": 17.4065, "lng": 78.4772})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["check_in_within"] is True
    assert d["check_in_distance"] < 10

    time.sleep(2)

    # Check-out immediate
    r = requests.post(f"{BASE_URL}/api/attendance/check-out",
                     headers=raghu_ctx["h"],
                     json={"lat": 17.4065, "lng": 78.4772})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["check_out_within"] is True
    assert "duration_min" in d
    assert isinstance(d["duration_min"], (int, float))
    print(f"Immediate duration_min = {d['duration_min']}")
    assert d["duration_min"] >= 0


def test_check_out_duration_synthetic_30min(db, raghu_ctx):
    # Reset and simulate check-in 30 min ago
    today = datetime.now(timezone.utc).date().isoformat()
    db.attendance.delete_many({"user_id": raghu_ctx["user_id"], "date": today})

    # Create a check-in
    r = requests.post(f"{BASE_URL}/api/attendance/check-in",
                     headers=raghu_ctx["h"],
                     json={"lat": 17.4065, "lng": 78.4772})
    assert r.status_code == 200, r.text

    # Backdate check_in_at by 30 min
    past = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    result = db.attendance.update_one(
        {"user_id": raghu_ctx["user_id"], "date": today},
        {"$set": {"check_in_at": past}}
    )
    assert result.modified_count == 1

    r = requests.post(f"{BASE_URL}/api/attendance/check-out",
                     headers=raghu_ctx["h"],
                     json={"lat": 17.4065, "lng": 78.4772})
    assert r.status_code == 200, r.text
    d = r.json()
    print(f"Synthetic 30-min duration_min = {d['duration_min']}")
    assert 28 <= d["duration_min"] <= 32, f"expected ~30 min, got {d['duration_min']}"

    # Cleanup
    db.attendance.delete_many({"user_id": raghu_ctx["user_id"], "date": today})
