"""
Endpoint-level tenant isolation — does the API actually scope its reads AND writes?

Why this exists
---------------
test_tenancy.py unit-tests tenancy.scope() and tenancy.stamp() in isolation. It
proves those helpers are correct; it proves nothing about whether an endpoint
remembers to call them. Isolation was enforced on the generic make_crud routes
but bypassed by hand-written ones, and the unit suite passed the whole time.

This drives real HTTP instead, against two independent tenants that are each
seeded with exactly one record per collection — so every check is a real
before/after comparison, not "the owner happened to have some seed data."

    python backend/tests/test_tenant_isolation_api.py
    python backend/tests/test_tenant_isolation_api.py --base http://127.0.0.1:8899

Endpoints whose collections are empty on both sides cannot be judged either way
and are reported as UNPROVEN rather than silently counted as passing — an empty
collection hides a missing scope until the day someone adds a record.

`activities` is one of the nine collections a P0 patch was asked to prove
isolation for, but the live app has no endpoint that writes to it (it is only
ever read, inside /api/journey/{phone}) — there is nothing to seed through
HTTP, and adding a write endpoint just to test one is out of scope for a
security patch. It is reported as SKIPPED, not silently dropped.
"""
import argparse
import datetime
import json
import sys
import urllib.error
import urllib.request
import uuid

ADMIN = {"username": "admin", "pin": "1234"}
TODAY = datetime.date.today().isoformat()

# endpoint -> key holding the list, or None when the body is itself a list
ENDPOINTS = [
    ("/api/quotes", None), ("/api/sales", None), ("/api/leads", None),
    ("/api/visitors", None), ("/api/inventory", None), ("/api/architects", None),
    ("/api/tasks", None), ("/api/invoices", None), ("/api/meets", None),
    ("/api/petty-cash", None), ("/api/projects", None), ("/api/payments", None),
    ("/api/stock-movements", None), ("/api/dw-surveys", None),
    ("/api/outstanding", "*"), ("/api/reports", "*"), ("/api/alerts", "*"),
    ("/api/analytics/inventory", "*"), ("/api/dashboard/stats", "*"),
    # Canonical CRM v1 + HR (backend/api_canonical.py, backend/api_hr.py) —
    # same tenant_id chokepoint, added when those routers were built.
    ("/api/v1/leads?brand_id=navaki", None),
    ("/api/v1/attendance", None),
    ("/api/v1/payroll", None),
    ("/api/v1/accounts?brand_id=navaki", None),
    ("/api/v1/contacts?brand_id=navaki", None),
]

# One record seeded into tenant A per collection named in the P0 patch spec
# (minus "activities" — see module docstring). Each entry can also carry a
# PUT/DELETE path for the cross-tenant write-safety checks; collections with
# no update endpoint (payments, stock_movements) omit "put".
WRITE_ENDPOINTS = {
    "leads": {
        "create": "/api/leads",
        "payload": lambda tag: {"date": TODAY, "name": f"Iso Lead {tag}", "phone": f"90000{tag[-5:]}",
                                 "source": "Walk-in", "reference": "Isolation Test"},
        "put": lambda i: f"/api/leads/{i}", "delete": lambda i: f"/api/leads/{i}",
    },
    "quotes": {
        "create": "/api/quotes",
        "payload": lambda tag: {"quote_no": f"Q-ISO-{tag}", "date": TODAY, "customer": f"Iso {tag}"},
        "put": lambda i: f"/api/quotes/{i}", "delete": lambda i: f"/api/quotes/{i}",
    },
    "sales": {
        "create": "/api/sales",
        "payload": lambda tag: {"sale_no": f"S-ISO-{tag}", "date": TODAY, "customer": f"Iso {tag}"},
        "put": lambda i: f"/api/sales/{i}", "delete": lambda i: f"/api/sales/{i}",
    },
    "visitors": {
        "create": "/api/visitors",
        "payload": lambda tag: {"date": TODAY, "name": f"Iso Visitor {tag}"},
        "put": lambda i: f"/api/visitors/{i}", "delete": lambda i: f"/api/visitors/{i}",
    },
    "projects": {
        "create": "/api/projects",
        "payload": lambda tag: {"project_no": f"P-ISO-{tag}", "customer": f"Iso {tag}"},
        "put": lambda i: f"/api/projects/{i}", "delete": lambda i: f"/api/projects/{i}",
    },
    "dw_surveys": {
        "create": "/api/dw-surveys",
        "payload": lambda tag: {"customer": f"Iso {tag}"},
        "put": lambda i: f"/api/dw-surveys/{i}", "delete": lambda i: f"/api/dw-surveys/{i}",
    },
    "payments": {
        "create": "/api/payments",
        "payload": lambda tag: {"date": TODAY, "amount": 100},
        "delete": lambda i: f"/api/payments/{i}",
    },
    "stock_movements": {
        "create": "/api/stock-movements",
        "payload": lambda tag: {"product_id": f"SKU-{tag}", "qty": 1},
        "delete": lambda i: f"/api/stock-movements/{i}",
    },
    "crm_leads": {
        # brand_id is a required query param on GET /api/v1/leads (used both
        # to create below and to re-list for the write-safety check further
        # down); harmless on POST, which reads brand_id from the JSON body.
        "create": "/api/v1/leads?brand_id=navaki",
        "payload": lambda tag: {"brand_id": "navaki", "name": f"Iso CRM Lead {tag}"},
        "put": lambda i: f"/api/v1/leads/{i}",
    },
    "crm_accounts": {
        "create": "/api/v1/accounts?brand_id=navaki",
        "payload": lambda tag: {"brand_id": "navaki", "name": f"Iso CRM Account {tag}"},
        "put": lambda i: f"/api/v1/accounts/{i}",
    },
    "crm_contacts": {
        # account_id is intentionally omitted here — cross-tenant account_id
        # rejection is proven separately below (own account, real; other
        # tenant's account, must 400), not through this generic seed loop.
        "create": "/api/v1/contacts?brand_id=navaki",
        "payload": lambda tag: {"brand_id": "navaki", "name": f"Iso CRM Contact {tag}"},
        "put": lambda i: f"/api/v1/contacts/{i}",
    },
    "hr_attendance_logs": {
        "create": "/api/v1/attendance",
        "payload": lambda tag: {"employee_id": f"iso-emp-{tag}", "date": TODAY,
                                 "check_in": f"{TODAY}T09:00:00+00:00"},
    },
}

# Curated collections the Data Centre CSV export covers (backend/server.py's
# DC_COLLECTIONS) that also appear in WRITE_ENDPOINTS above, so we can prove
# export is both admin-gated (Task 2) and tenant-scoped with real data.
EXPORT_NAMES = ["leads", "quotes", "sales", "visitors", "payments", "projects"]


def call(base, method, path, body=None, token=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "null")
        except Exception:
            return e.code, None


def _records(v):
    """
    Business records inside a list, ignoring fixed-shape aggregates.

    A report's aging buckets or stage breakdown are the same four or five
    entries whether or not the caller owns any data, so counting them raw makes
    a correctly-isolated endpoint look like a leak. Real records carry an id.
    """
    if not isinstance(v, list):
        return 0
    return sum(1 for x in v if isinstance(x, dict) and ("id" in x or "_id" in x))


def count(payload, key):
    """How many business records a response carries."""
    if payload is None:
        return 0
    if isinstance(payload, list):
        return _records(payload)
    if isinstance(payload, dict):
        if key and key != "*":
            return _records(payload.get(key))
        total = 0
        for v in payload.values():
            if isinstance(v, list):
                total += _records(v)
            elif isinstance(v, dict):
                total += sum(_records(x) for x in v.values())
        return total
    return 0


def create_tenant(base, root_token, label):
    name = f"{label} " + uuid.uuid4().hex[:6]
    s, t = call(base, "POST", "/api/tenants", {"name": name}, root_token)
    if s != 200 or not t or "admin_username" not in t:
        return None, f"could not create tenant '{name}' ({s})"
    s, lg = call(base, "POST", "/api/auth/login",
                 {"username": t["admin_username"], "pin": str(t["admin_pin"])})
    if s != 200:
        return None, f"tenant '{name}' admin cannot log in ({s})"
    return {"token": lg["token"], "id": t["tenant"]["id"], "name": name}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8899")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    print(f"Tenant isolation across the API\ntarget: {base}\n")

    s, d = call(base, "POST", "/api/auth/login", ADMIN)
    if s != 200:
        print(f"  cannot authenticate as admin ({s}). Set SEED_PINS so admin/1234 exists.")
        return 1
    root_token = d["token"]

    tenant_a, err = create_tenant(base, root_token, "Isolation A")
    if err:
        print(f"  {err}")
        return 1
    tenant_b, err = create_tenant(base, root_token, "Isolation B")
    if err:
        print(f"  {err}")
        return 1
    token_a, token_b = tenant_a["token"], tenant_b["token"]
    print(f"tenant A: {tenant_a['id']}\ntenant B: {tenant_b['id']} (starts with no records)\n")

    # ── seed exactly one record per named collection into tenant A only ────
    # Hex (uuid4().hex), not decimal — the leads payload below builds a phone
    # number from tag[-5:], which normalize_indian_phone() rejects whenever
    # the hex happens to contain a letter (a-f). Digits only avoids that.
    tag = str(uuid.uuid4().int)[:8]
    created, seed_failures = {}, []
    for coll, spec in WRITE_ENDPOINTS.items():
        s, resp = call(base, "POST", spec["create"], spec["payload"](tag), token_a)
        if s != 200 or not isinstance(resp, dict) or "id" not in resp:
            seed_failures.append((coll, s))
            continue
        created[coll] = resp["id"]

    print("SKIPPED  activities                 no write endpoint exists in the live app\n")

    if seed_failures:
        print("Could not seed test data — aborting:")
        for coll, s in seed_failures:
            print(f"  {coll:<16} POST failed ({s})")
        return 1

    # ── read isolation: tenant B must never see tenant A's records ─────────
    leaks, unproven, ok = [], [], []
    for path, key in ENDPOINTS:
        s1, mine = call(base, "GET", path, None, token_b)
        s2, theirs = call(base, "GET", path, None, token_a)
        if s1 >= 400 or s2 >= 400:
            unproven.append((path, f"HTTP {s1}/{s2}"))
            continue
        a, b = count(mine, key), count(theirs, key)
        if b == 0:
            unproven.append((path, "tenant A has no records to leak"))
        elif a == 0:
            ok.append((path, f"{a} vs {b}"))
        else:
            leaks.append((path, f"tenant B sees {a}, tenant A has {b}"))

    # ── export isolation + admin gating (Task 2) ────────────────────────────
    for name in EXPORT_NAMES:
        path = f"/api/data-centre/export/{name}"
        s1, mine = call(base, "GET", path, None, token_b)
        s2, theirs = call(base, "GET", path, None, token_a)
        if s1 >= 400 or s2 >= 400:
            unproven.append((path, f"HTTP {s1}/{s2}"))
            continue
        a, b = (mine or {}).get("count", 0), (theirs or {}).get("count", 0)
        if b == 0:
            unproven.append((path, "tenant A has no records to leak"))
        elif a == 0:
            ok.append((path, f"{a} vs {b}"))
        else:
            leaks.append((path, f"tenant B sees {a}, tenant A has {b}"))

    for p, why in ok:
        print(f"  PASS   {p:<32} isolated ({why})")
    for p, why in unproven:
        print(f"  UNPROVEN {p:<30} {why}")
    for p, why in leaks:
        print(f"  LEAK   {p:<32} {why}")

    # ── write safety: tenant B must not be able to touch tenant A's records
    #    by id (cross-tenant PUT/DELETE must 404, not silently no-op-succeed
    #    or, worse, actually mutate/delete) ───────────────────────────────
    write_fail = []
    for coll, item_id in created.items():
        spec = WRITE_ENDPOINTS[coll]
        if spec.get("put"):
            s, _ = call(base, "PUT", spec["put"](item_id),
                        {"remarks": "cross-tenant-write-should-not-land"}, token_b)
            if s != 404:
                write_fail.append((coll, "PUT", s))
        if spec.get("delete"):
            s, _ = call(base, "DELETE", spec["delete"](item_id), None, token_b)
            if s != 404:
                write_fail.append((coll, "DELETE", s))

    # Integrity check: after the attempted cross-tenant writes above, tenant
    # A's records must still exist, unmodified. A wrongly-scoped update_one
    # would report 404 correctly but a wrongly-scoped delete_one would not —
    # this catches both by re-reading tenant A's own view.
    for coll, item_id in created.items():
        path = WRITE_ENDPOINTS[coll]["create"]
        s, rows = call(base, "GET", path, None, token_a)
        if s >= 400 or not isinstance(rows, list):
            write_fail.append((coll, "post-check GET", s))
            continue
        rec = next((r for r in rows if r.get("id") == item_id), None)
        if rec is None:
            write_fail.append((coll, "record vanished after cross-tenant DELETE attempt", "-"))
        elif rec.get("remarks") == "cross-tenant-write-should-not-land":
            write_fail.append((coll, "record mutated by cross-tenant PUT attempt", "-"))

    print()
    if not write_fail:
        print(f"  cross-tenant PUT/DELETE correctly rejected for {len(created)} collections")

    # ── payroll cross-tenant employee lookup (backend/api_hr.py) ───────────
    # POST /api/v1/payroll/calculate looks up the employee by id on the
    # "users" collection, which tenancy.scope() does NOT filter (users is
    # deliberately excluded from TENANT_COLLECTIONS — see tenancy.py). A
    # missing hand-written tenant_id filter there would let tenant B
    # calculate payroll — i.e. read salary figures — for tenant A's staff by
    # guessing/knowing their user id. This is a regression test for exactly
    # that bug (found and fixed in api_hr.py's payroll_calculate).
    s, my_users = call(base, "GET", "/api/auth/users", None, token_a)
    a_employee_id = my_users[0]["id"] if s == 200 and my_users else None
    if not a_employee_id:
        write_fail.append(("payroll_cross_tenant", "could not fetch tenant A's own user id", s))
    else:
        s_self, _ = call(base, "POST", "/api/v1/payroll/calculate",
                          {"employee_id": a_employee_id, "period_start": TODAY, "period_end": TODAY}, token_a)
        if s_self != 200:
            write_fail.append(("payroll_cross_tenant", "tenant A calculating its OWN payroll failed", s_self))
        s_cross, body_cross = call(base, "POST", "/api/v1/payroll/calculate",
                                    {"employee_id": a_employee_id, "period_start": TODAY, "period_end": TODAY}, token_b)
        if s_cross != 404:
            write_fail.append(("payroll_cross_tenant",
                                f"tenant B calculated payroll for tenant A's employee_id (got {s_cross}, expected 404)",
                                body_cross))
        else:
            print(f"  cross-tenant payroll employee lookup correctly rejected (404)")

    # ── chain-integrity: a record must never be creatable pointing at
    #    another tenant's parent record (backend/api_canonical.py) ────────
    a_account_id = created.get("crm_accounts")
    if a_account_id:
        s, body = call(base, "POST", "/api/v1/contacts",
                        {"brand_id": "navaki", "account_id": a_account_id, "name": "Cross Tenant Contact"},
                        token_b)
        if s == 200:
            write_fail.append(("chain_integrity", "contact created with another tenant's account_id", body))
        else:
            print(f"  cross-tenant Contact.account_id correctly rejected ({s})")

        s, body = call(base, "POST", "/api/v1/activities",
                        {"brand_id": "navaki", "related_entity": "account", "related_id": a_account_id,
                         "type": "note", "subject": "Cross Tenant Activity"},
                        token_b)
        if s == 200:
            write_fail.append(("chain_integrity", "activity created against another tenant's account", body))
        else:
            print(f"  cross-tenant Activity.related_id correctly rejected ({s})")

    if write_fail:
        for coll, op, s in write_fail:
            print(f"  WRITE-LEAK  {coll:<20} {op:<50} {s}")

    print(f"\nisolated {len(ok)}   leaking {len(leaks)}   unproven {len(unproven)}   "
          f"write-leaks {len(write_fail)}")
    if leaks or write_fail:
        print("\nA leaking endpoint returns another business's records to a tenant that\n"
              "owns none. Wrap its queries in tenancy.scope(query, collection, user).\n"
              "A write-leak lets one tenant modify or delete another tenant's record by\n"
              "id — the selector must be tenancy.scope({'id': item_id}, collection, user).")
    return 1 if (leaks or write_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
