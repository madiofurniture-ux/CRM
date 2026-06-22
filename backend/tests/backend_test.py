"""MADIO CRM - Backend API tests (pytest)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://crm-builder-125.preview.emergentagent.com").rstrip("/")


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "1234"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def user_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "raghu", "pin": "2222"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_h(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_login_wrong_pin(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "0000"})
        assert r.status_code == 401

    def test_login_admin_returns_token_user(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "pin": "1234"})
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["role"] == "admin"
        assert d["user"].get("pages") is None
        assert "pin_hash" not in d["user"]

    def test_login_user_returns_pages(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "raghu", "pin": "2222"})
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["role"] == "user"
        assert isinstance(d["user"].get("pages"), list)
        assert len(d["user"]["pages"]) > 0

    def test_me_with_token(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/auth/me", headers=admin_h)
        assert r.status_code == 200
        assert r.json()["username"] == "admin"

    def test_me_no_token(self, s):
        r = s.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_admin_list_users(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/auth/users", headers=admin_h)
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 4
        unames = {u["username"] for u in users}
        assert {"admin", "raghu", "nenmu", "gowtham"}.issubset(unames)

    def test_nonadmin_cannot_list_users(self, s, user_h):
        r = s.get(f"{BASE_URL}/api/auth/users", headers=user_h)
        assert r.status_code == 403


# ---------- Seed Data Counts ----------
class TestSeedData:
    @pytest.mark.parametrize("ep,minimum", [
        ("visitors", 25),
        ("inventory", 100),
        ("sales", 50),
        ("leads", 15),
        ("quotes", 15),
        ("architects", 10),
        ("tasks", 10),
    ])
    def test_seed_counts(self, s, admin_h, ep, minimum):
        r = s.get(f"{BASE_URL}/api/{ep}", headers=admin_h)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= minimum, f"{ep}: expected >= {minimum}, got {len(data)}"


# ---------- Dashboard / Analytics ----------
class TestDashboard:
    def test_dashboard_stats(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/dashboard/stats", headers=admin_h)
        assert r.status_code == 200
        d = r.json()
        for k in ["pipeline_value", "total_sales", "outstanding", "stock_mrp",
                  "active_leads", "by_stage", "division_split", "monthly_revenue"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["by_stage"], list) and len(d["by_stage"]) == 6
        assert isinstance(d["division_split"], list)
        assert isinstance(d["monthly_revenue"], list)

    def test_inventory_analytics(self, s, admin_h):
        r = s.get(f"{BASE_URL}/api/analytics/inventory", headers=admin_h)
        assert r.status_code == 200
        d = r.json()
        for k in ["total_items", "by_category", "by_vendor", "by_location", "top_items"]:
            assert k in d
        assert d["total_items"] > 0
        assert len(d["top_items"]) > 0


# ---------- CRUD: Quotes ----------
class TestQuotesCRUD:
    def test_full_crud(self, s, admin_h):
        payload = {
            "quote_no": "TEST-Q-9999", "date": "2026-01-15",
            "customer": "TEST_Customer", "reference": "TEST", "phone": "9999999999",
            "division": "Furniture", "by_user": "admin", "stage": "New",
            "value": 100000, "cash": 0, "bank": 0, "mode": "Walk-in", "remarks": "test"
        }
        r = s.post(f"{BASE_URL}/api/quotes", headers=admin_h, json=payload)
        assert r.status_code == 200, r.text
        qid = r.json()["id"]
        assert r.json()["customer"] == "TEST_Customer"

        # update
        r = s.put(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h, json={"stage": "Won"})
        assert r.status_code == 200
        assert r.json()["stage"] == "Won"

        # get reflects
        r = s.get(f"{BASE_URL}/api/quotes", headers=admin_h)
        item = next((q for q in r.json() if q["id"] == qid), None)
        assert item and item["stage"] == "Won"

        # delete
        r = s.delete(f"{BASE_URL}/api/quotes/{qid}", headers=admin_h)
        assert r.status_code == 200

        r = s.get(f"{BASE_URL}/api/quotes", headers=admin_h)
        assert not any(q["id"] == qid for q in r.json())


# ---------- CRUD: Leads, Visitors, Tasks, Inventory ----------
class TestOtherCRUD:
    def _crud(self, s, h, ep, create):
        r = s.post(f"{BASE_URL}/api/{ep}", headers=h, json=create)
        assert r.status_code == 200, f"create {ep}: {r.text}"
        iid = r.json()["id"]
        r = s.put(f"{BASE_URL}/api/{ep}/{iid}", headers=h, json={"remarks": "updated_test"})
        # Note: tasks/inventory may not have remarks but accept dict
        assert r.status_code == 200
        r = s.delete(f"{BASE_URL}/api/{ep}/{iid}", headers=h)
        assert r.status_code == 200

    def test_leads(self, s, admin_h):
        self._crud(s, admin_h, "leads", {
            "date": "2026-01-15", "name": "TEST_Lead", "phone": "9111111111",
            "source": "Walk-in", "stage": "New", "follow_up_date": "2026-02-01",
            "remarks": "test", "assigned_to": "admin", "value": 50000
        })

    def test_visitors(self, s, admin_h):
        self._crud(s, admin_h, "visitors", {
            "date": "2026-01-15", "name": "TEST_Visitor", "location": "X",
            "reference": "X", "phone": "9111111111", "requirement": "Sofa",
            "attend_person": "admin", "site_visit": "", "remarks": "test",
            "status": "New", "stage": "New", "ticket_value": 100000
        })

    def test_tasks(self, s, admin_h):
        self._crud(s, admin_h, "tasks", {
            "title": "TEST_Task", "priority": "Low", "due_date": "2026-02-01",
            "assigned_to": "admin", "category": "Admin", "ref": "", "notes": "",
            "done": False, "created_by": "admin"
        })

    def test_inventory(self, s, admin_h):
        self._crud(s, admin_h, "inventory", {
            "sku": "TEST-INV-001", "name": "TEST_Item", "category": "Test",
            "vendor": "V1", "model_no": "M1", "qty": 1, "cost": 100, "mrp": 200,
            "margin": 100, "status": "In Stock", "location": "Warehouse A", "image_url": ""
        })


# ---------- Admin User Management ----------
class TestUserMgmt:
    def test_admin_create_update_delete_user(self, s, admin_h):
        payload = {
            "username": "test_temp_user", "name": "TEST_TempUser", "pin": "9999",
            "role": "user", "icon": "TT", "color": "#000000",
            "pages": ["dashboard"]
        }
        r = s.post(f"{BASE_URL}/api/auth/users", headers=admin_h, json=payload)
        if r.status_code == 400 and "exists" in r.text.lower():
            # cleanup existing
            users = s.get(f"{BASE_URL}/api/auth/users", headers=admin_h).json()
            uid = next(u["id"] for u in users if u["username"] == "test_temp_user")
            s.delete(f"{BASE_URL}/api/auth/users/{uid}", headers=admin_h)
            r = s.post(f"{BASE_URL}/api/auth/users", headers=admin_h, json=payload)
        assert r.status_code == 200, r.text
        uid = r.json()["id"]

        r = s.put(f"{BASE_URL}/api/auth/users/{uid}", headers=admin_h, json={"name": "TEST_Renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Renamed"

        r = s.delete(f"{BASE_URL}/api/auth/users/{uid}", headers=admin_h)
        assert r.status_code == 200

    def test_nonadmin_cannot_create_user(self, s, user_h):
        r = s.post(f"{BASE_URL}/api/auth/users", headers=user_h, json={
            "username": "x", "name": "x", "pin": "1234", "role": "user",
            "icon": "X", "color": "#000", "pages": []
        })
        assert r.status_code == 403
