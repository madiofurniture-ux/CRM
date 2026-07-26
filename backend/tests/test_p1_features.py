"""P1 features tests: invoices, meets, petty-cash, outstanding, office settings, attendance."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_h(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "1234"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def raghu_ctx(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "raghu", "pin": "2222"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {
        "h": {"Authorization": f"Bearer {data['token']}", "Content-Type": "application/json"},
        "user_id": data["user"]["id"],
    }


# ---------- Invoices ----------
class TestInvoices:
    def test_seed_count(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/invoices", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 5, f"Expected >=5 invoices, got {len(data)}"
        # shape check
        inv = data[0]
        for k in ["line_items", "subtotal", "cgst", "sgst", "igst", "total", "balance"]:
            assert k in inv, f"invoice missing key {k}"
        assert isinstance(inv["line_items"], list)

    def test_full_crud(self, s, admin_h):
        payload = {
            "invoice_no": "TEST-INV-9999", "date": "2026-01-15", "customer": "TEST_C",
            "line_items": [{"description": "Sofa", "hsn": "9403", "qty": 2, "rate": 50000, "tax_pct": 18}],
            "subtotal": 100000, "cgst": 9000, "sgst": 9000, "igst": 0,
            "total": 118000, "balance": 118000,
        }
        r = s.post(f"{BASE_URL}/api/invoices", headers=admin_h, json=payload)
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert r.json()["total"] == 118000

        r = s.put(f"{BASE_URL}/api/invoices/{iid}", headers=admin_h, json={"status": "Sent"})
        assert r.status_code == 200
        assert r.json()["status"] == "Sent"

        r = s.delete(f"{BASE_URL}/api/invoices/{iid}", headers=admin_h)
        assert r.status_code == 200


# ---------- Meets ----------
class TestMeets:
    def test_seed_count(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/meets", headers=admin_h)
        assert r.status_code == 200
        assert len(r.json()) >= 7

    def test_full_crud(self, s, admin_h):
        payload = {"title": "TEST_Meet", "date": "2026-02-01", "start_time": "10:00", "end_time": "11:00"}
        r = s.post(f"{BASE_URL}/api/meets", headers=admin_h, json=payload)
        assert r.status_code == 200
        mid = r.json()["id"]
        r = s.put(f"{BASE_URL}/api/meets/{mid}", headers=admin_h, json={"status": "Done"})
        assert r.status_code == 200
        assert r.json()["status"] == "Done"
        r = s.delete(f"{BASE_URL}/api/meets/{mid}", headers=admin_h)
        assert r.status_code == 200


# ---------- Petty Cash ----------
class TestPettyCash:
    def test_seed_count(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/petty-cash", headers=admin_h)
        assert r.status_code == 200
        assert len(r.json()) >= 10

    def test_full_crud(self, s, admin_h):
        payload = {"date": "2026-01-15", "kind": "Out", "category": "Fuel",
                   "description": "TEST petrol", "amount": 500, "mode": "Cash"}
        r = s.post(f"{BASE_URL}/api/petty-cash", headers=admin_h, json=payload)
        assert r.status_code == 200
        pid = r.json()["id"]
        r = s.put(f"{BASE_URL}/api/petty-cash/{pid}", headers=admin_h, json={"amount": 600})
        assert r.status_code == 200
        assert r.json()["amount"] == 600
        r = s.delete(f"{BASE_URL}/api/petty-cash/{pid}", headers=admin_h)
        assert r.status_code == 200


# ---------- Outstanding ----------
class TestOutstanding:
    def test_shape(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/outstanding", headers=admin_h)
        assert r.status_code == 200
        d = r.json()
        for k in ["sales_outstanding", "invoice_outstanding", "hot_pipeline",
                  "aging", "outstanding_sales", "outstanding_invoices", "hot_quotes"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["aging"], list) and len(d["aging"]) == 4
        buckets = {a["bucket"] for a in d["aging"]}
        assert buckets == {"0-30", "31-60", "61-90", "90+"}
        assert d["hot_pipeline"] >= 0


# ---------- Office Settings ----------
class TestOfficeSettings:
    def test_get_defaults(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/settings/office", headers=admin_h)
        assert r.status_code == 200
        d = r.json()
        # If DB was fresh, defaults should be set; if changed by tests, still valid schema
        assert "lat" in d and "lng" in d and "radius_m" in d

    def test_admin_update(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/settings/office", headers=admin_h)
        orig = r.json()
        new_data = {**orig, "lat": 17.4065, "lng": 78.4772, "radius_m": 250,
                    "name": orig.get("name", "MADIO Head Office"),
                    "address": orig.get("address", "Hyderabad"),
                    "gstin": orig.get("gstin", ""),
                    "invoice_prefix": orig.get("invoice_prefix", "MAD")}
        r = s.put(f"{BASE_URL}/api/settings/office", headers=admin_h, json=new_data)
        assert r.status_code == 200
        assert r.json()["radius_m"] == 250

        # verify persist
        r = s.get(f"{BASE_URL}/api/settings/office", headers=admin_h)
        assert r.json()["radius_m"] == 250

        # restore
        s.put(f"{BASE_URL}/api/settings/office", headers=admin_h,
              json={**new_data, "radius_m": 200, "lat": 17.4065, "lng": 78.4772})

    def test_nonadmin_cannot_update(self, s, raghu_ctx):
        r = s.put(f"{BASE_URL}/api/settings/office", headers=raghu_ctx["h"],
                  json={"name": "hack", "lat": 0, "lng": 0, "radius_m": 1,
                        "address": "", "gstin": "", "invoice_prefix": "X"})
        assert r.status_code == 403


# ---------- Attendance ----------
class TestAttendance:
    def test_full_flow(self, s, admin_h):
        # ensure clean: delete today's record from DB via a workaround - can't; but backend permits repeat check-in only if record has no check_in_at
        # instead: query today first
        r = s.get(f"{BASE_URL}/api/attendance/today", headers=admin_h)
        assert r.status_code == 200
        today = r.json()
        # Clean up: if admin has checked in today from a previous test, skip
        if today is not None and today.get("check_in_at"):
            pytest.skip("admin already checked in today from previous run; skipping check-in test")

        # Check-in within radius (office lat/lng)
        r = s.post(f"{BASE_URL}/api/attendance/check-in", headers=admin_h,
                   json={"lat": 17.4065, "lng": 78.4772})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["check_in_within"] is True
        assert d["check_in_distance"] < 10

        # Repeat check-in should fail
        r = s.post(f"{BASE_URL}/api/attendance/check-in", headers=admin_h,
                   json={"lat": 17.4065, "lng": 78.4772})
        assert r.status_code == 400
        assert "already" in r.text.lower()

        # Today endpoint returns record
        r = s.get(f"{BASE_URL}/api/attendance/today", headers=admin_h)
        assert r.status_code == 200 and r.json() is not None

        # Check-out
        r = s.post(f"{BASE_URL}/api/attendance/check-out", headers=admin_h,
                   json={"lat": 17.4065, "lng": 78.4772})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("check_out_at")
        assert "duration_min" in d

    def test_check_in_outside_radius(self, s, raghu_ctx):
        # need clean state — check if raghu already checked-in
        r = s.get(f"{BASE_URL}/api/attendance/today", headers=raghu_ctx["h"])
        if r.json() and r.json().get("check_in_at"):
            pytest.skip("raghu already checked in today")
        # Bangalore coords - way outside Hyderabad office
        r = s.post(f"{BASE_URL}/api/attendance/check-in", headers=raghu_ctx["h"],
                   json={"lat": 12.9716, "lng": 77.5946})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["check_in_within"] is False
        assert d["check_in_distance"] > 100000  # ~500km

    def test_nonadmin_cannot_query_other(self, s, admin_h, raghu_ctx):
        # get admin's id
        users = s.get(f"{BASE_URL}/api/auth/users", headers=admin_h).json()
        admin_id = next(u["id"] for u in users if u["username"] == "admin")
        r = s.get(f"{BASE_URL}/api/attendance?user_id={admin_id}", headers=raghu_ctx["h"])
        assert r.status_code == 403

    def test_nonadmin_gets_only_own(self, s, raghu_ctx):
        r = s.get(f"{BASE_URL}/api/attendance", headers=raghu_ctx["h"])
        assert r.status_code == 200
        for rec in r.json():
            assert rec["user_id"] == raghu_ctx["user_id"]


# ---------- raghu permissions ----------
class TestRaghuPerms:
    def test_users_forbidden(self, s, raghu_ctx):
        r = s.get(f"{BASE_URL}/api/auth/users", headers=raghu_ctx["h"])
        assert r.status_code == 403
