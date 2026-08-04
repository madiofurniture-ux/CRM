"""
Endpoint-level tenant isolation — does the API actually scope its reads?

Why this exists
---------------
test_tenancy.py unit-tests tenancy.scope() and tenancy.stamp() in isolation. It
proves those helpers are correct; it proves nothing about whether an endpoint
remembers to call them. Isolation was enforced on the generic make_crud routes
but bypassed by hand-written ones, and the unit suite passed the whole time.

This drives real HTTP instead. A second tenant is created with no records of its
own, so any non-empty response it receives is another business's data.

    python backend/tests/test_tenant_isolation_api.py
    python backend/tests/test_tenant_isolation_api.py --base http://127.0.0.1:8899

Endpoints whose collections are empty on both sides cannot be judged either way
and are reported as UNPROVEN rather than silently counted as passing — an empty
collection hides a missing scope until the day someone adds a record.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

ADMIN = {"username": "admin", "pin": "1234"}

# endpoint -> key holding the list, or None when the body is itself a list
ENDPOINTS = [
    ("/api/quotes", None), ("/api/sales", None), ("/api/leads", None),
    ("/api/visitors", None), ("/api/inventory", None), ("/api/architects", None),
    ("/api/tasks", None), ("/api/invoices", None), ("/api/meets", None),
    ("/api/petty-cash", None), ("/api/projects", None), ("/api/payments", None),
    ("/api/stock-movements", None), ("/api/dw-surveys", None),
    ("/api/outstanding", "*"), ("/api/reports", "*"), ("/api/alerts", "*"),
    ("/api/analytics/inventory", "*"), ("/api/dashboard/stats", "*"),
]


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
    owner = d["token"]

    name = "Isolation Probe " + uuid.uuid4().hex[:6]
    s, t = call(base, "POST", "/api/tenants", {"name": name}, owner)
    if s != 200 or not t or "admin_username" not in t:
        print(f"  could not create a probe tenant ({s}) — is the caller an admin?")
        return 1
    s, lg = call(base, "POST", "/api/auth/login",
                 {"username": t["admin_username"], "pin": str(t["admin_pin"])})
    if s != 200:
        print(f"  probe tenant admin cannot log in ({s})")
        return 1
    probe = lg["token"]
    print(f"probe tenant: {t['tenant']['id']} (owns no records)\n")

    leaks, unproven, ok = [], [], []
    for path, key in ENDPOINTS:
        s1, mine = call(base, "GET", path, None, probe)
        s2, theirs = call(base, "GET", path, None, owner)
        if s1 >= 400 or s2 >= 400:
            unproven.append((path, f"HTTP {s1}/{s2}"))
            continue
        a, b = count(mine, key), count(theirs, key)
        if b == 0:
            unproven.append((path, "owner has no records to leak"))
        elif a == 0:
            ok.append((path, f"{a} vs {b}"))
        else:
            leaks.append((path, f"probe sees {a}, owner has {b}"))

    for p, why in ok:
        print(f"  PASS   {p:<28} isolated ({why})")
    for p, why in unproven:
        print(f"  UNPROVEN {p:<26} {why}")
    for p, why in leaks:
        print(f"  LEAK   {p:<28} {why}")

    print(f"\nisolated {len(ok)}   leaking {len(leaks)}   unproven {len(unproven)}")
    if leaks:
        print("\nA leaking endpoint returns another business's records to a tenant that\n"
              "owns none. Wrap its queries in tenancy.scope(query, collection, user).")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
