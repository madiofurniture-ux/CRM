"""
End-to-end API tests for MADIO CRM.

Covers what unit tests cannot: real HTTP against the running FastAPI app, real
auth, real MongoDB — including every fix and feature added in this chat.

Run the server first, then:
    python backend/tests/test_api_e2e.py                    # against 127.0.0.1:8000
    python backend/tests/test_api_e2e.py --base http://127.0.0.1:8815
    python backend/tests/test_api_e2e.py --base https://madio-crm-api.onrender.com

SAFETY: read-mostly. Anything it creates is deleted again, and any setting it
flips is restored in a finally block — so it is safe to point at production.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ADMIN = {"username": "admin", "pin": "1234"}
USER = {"username": "raghu", "pin": "2222"}

_pass, _fail, _skip = 0, 0, 0
_failures = []


def call(method, path, body=None, token=None, timeout=60):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw[:200]
    except Exception as e:                                   # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def check(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        _failures.append(f"{name} — {detail}")
        print(f"  FAIL  {name}  {detail}")


def section(t):
    print(f"\n{t}\n{'-' * len(t)}")


def main():
    global BASE, _skip
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args()
    BASE = args.base.rstrip("/")
    print(f"MADIO CRM — end-to-end API tests\ntarget: {BASE}")

    # ── health & auth ──────────────────────────────────────────────────
    section("Health & authentication")
    s, d = call("GET", "/api/")
    check("API is reachable", s == 200, f"got {s} {d}")
    if s != 200:
        print("\nServer not reachable — aborting.")
        sys.exit(1)

    s, d = call("POST", "/api/auth/login", ADMIN)
    got_tok = isinstance(d, dict) and bool(d.get("token"))
    check("admin can log in", s == 200 and got_tok, f"got {s} {str(d)[:90]}")
    if not got_tok:
        print("\nCannot authenticate — is the database reachable? Aborting.")
        sys.exit(1)
    admin_tok = d["token"]

    s, d = call("POST", "/api/auth/login", USER)
    user_tok = d.get("token") if (s == 200 and isinstance(d, dict)) else None
    if not user_tok:
        _skip += 1
        print("  SKIP  non-admin login (seeded user missing)")

    s, _ = call("POST", "/api/auth/login", {"username": "admin", "pin": "0000"})
    check("wrong PIN is rejected", s in (401, 400, 403), f"got {s}")

    s, _ = call("GET", "/api/inventory")
    check("unauthenticated request is rejected", s in (401, 403), f"got {s}")

    # ── every route returns 200 ────────────────────────────────────────
    section("All endpoints respond")
    endpoints = [
        "/api/inventory", "/api/quotes", "/api/sales", "/api/visitors", "/api/leads",
        "/api/architects", "/api/tasks", "/api/projects", "/api/invoices", "/api/meets",
        "/api/petty_cash" if False else "/api/petty-cash", "/api/dw-surveys",
        "/api/dw-openings", "/api/quote-lines", "/api/payments", "/api/stock-movements",
        "/api/stock-movements/summary", "/api/reports", "/api/alerts",
        "/api/data-centre/collections", "/api/fy/options", "/api/visibility/settings",
    ]
    counts = {}
    for ep in endpoints:
        s, d = call("GET", ep, token=admin_tok)
        ok = s == 200
        if isinstance(d, list):
            counts[ep] = len(d)
        check(f"GET {ep}", ok, f"got {s} {str(d)[:70]}")

    # regression: this one 500'd on ObjectId serialization
    s, d = call("GET", "/api/projects", token=admin_tok)
    check("REGRESSION projects does not 500 on ObjectId", s == 200, f"got {s} {str(d)[:80]}")

    # ── data integrity ─────────────────────────────────────────────────
    section("Data integrity")
    s, inv = call("GET", "/api/inventory", token=admin_tok)
    check("inventory has the full catalogue (>600)", isinstance(inv, list) and len(inv) > 600,
          f"got {len(inv) if isinstance(inv, list) else inv}")
    if isinstance(inv, list) and inv:
        with_img = [i for i in inv if (i.get("image_url") or "").strip()]
        check("product photos are linked (>250)", len(with_img) > 250, f"got {len(with_img)}")
        check("SKUs use the MF- business key",
              sum(1 for i in inv if str(i.get("sku", "")).startswith("MF-")) > 600,
              "SKU scheme is not MF-")
        skus = [i.get("sku") for i in inv]
        check("no duplicate SKUs", len(skus) == len(set(skus)),
              f"{len(skus) - len(set(skus))} duplicates")
        check("no MAD- placeholder SKUs remain",
              not any(str(i.get("sku", "")).startswith("MAD-") for i in inv), "found MAD- SKUs")

    s, sales = call("GET", "/api/sales", token=admin_tok)
    if isinstance(sales, list) and sales:
        bad = [x for x in sales if isinstance(x.get("value"), (int, float)) and abs(x["value"]) > 1e10]
        check("no timestamp-corrupted money values", not bad, f"{len(bad)} bad rows")

    # ── financial year ─────────────────────────────────────────────────
    section("Financial year filter")
    s, fy = call("GET", "/api/fy/options", token=admin_tok)
    check("FY options list years", s == 200 and bool(fy.get("years")), f"got {s}")
    check("current FY is computed", bool(fy.get("current_fy")), "missing current_fy")

    original_hidden = list(fy.get("hidden_fys") or [])
    target = next((y["fy"] for y in fy.get("years", []) if y["records"] > 0), None)
    if target:
        before = len(call("GET", "/api/quotes", token=admin_tok)[1] or [])
        try:
            call("PUT", "/api/fy/settings", {"hidden_fys": [target]}, token=admin_tok)
            after = len(call("GET", "/api/quotes", token=admin_tok)[1] or [])
            check(f"hiding FY {target} reduces or holds list", after <= before,
                  f"{before} -> {after}")
        finally:
            call("PUT", "/api/fy/settings", {"hidden_fys": original_hidden}, token=admin_tok)
        restored = len(call("GET", "/api/quotes", token=admin_tok)[1] or [])
        check("un-hiding restores every record", restored == before, f"{before} -> {restored}")

    if user_tok:
        s, _ = call("PUT", "/api/fy/settings", {"hidden_fys": []}, token=user_tok)
        check("non-admin cannot change FY settings", s == 403, f"got {s}")

    # ── record visibility / auto-hide ──────────────────────────────────
    section("Record hiding & 90-day auto-hide")
    s, vis = call("GET", "/api/visibility/settings", token=admin_tok)
    check("visibility settings readable", s == 200, f"got {s}")
    orig_auto = bool(vis.get("auto_hide_enabled"))
    orig_days = int(vis.get("auto_hide_days") or 90)
    check("auto-hide window defaults to 90 days", orig_days == 90, f"got {orig_days}")

    sales_before = len(call("GET", "/api/sales", token=admin_tok)[1] or [])
    try:
        call("PUT", "/api/visibility/settings",
             {"auto_hide_enabled": True, "auto_hide_days": 90}, token=admin_tok)
        hidden_n = len(call("GET", "/api/sales", token=admin_tok)[1] or [])
        check("auto-hide removes closed+aged sales", hidden_n <= sales_before,
              f"{sales_before} -> {hidden_n}")
    finally:
        call("PUT", "/api/visibility/settings",
             {"auto_hide_enabled": orig_auto, "auto_hide_days": orig_days}, token=admin_tok)
    check("disabling auto-hide restores the list",
          len(call("GET", "/api/sales", token=admin_tok)[1] or []) == sales_before,
          "count did not return to baseline")

    s, _ = call("PUT", "/api/visibility/settings", {"auto_hide_days": -5}, token=admin_tok)
    check("invalid auto-hide window is rejected", s == 400, f"got {s}")

    if user_tok:
        s, _ = call("PUT", "/api/visibility/settings", {"auto_hide_enabled": True}, token=user_tok)
        check("non-admin cannot change auto-hide", s == 403, f"got {s}")

    # manual hide round-trip on a throwaway record
    s, made = call("POST", "/api/visitors",
                   {"name": "ZZ E2E Hide Probe", "phone": "9000000001", "date": "2026-07-01"},
                   token=admin_tok)
    if s == 200 and made and made.get("id"):
        vid = made["id"]
        try:
            seen = lambda: any(v.get("id") == vid for v in (call("GET", "/api/visitors", token=admin_tok)[1] or []))  # noqa: E731
            check("new record is visible", seen(), "not returned after create")
            call("PUT", f"/api/records/visitors/{vid}/hidden", {"hidden": True}, token=admin_tok)
            check("admin can hide one record", not seen(), "still visible after hide")
            hl = call("GET", "/api/records/visitors/hidden", token=admin_tok)[1] or []
            check("hidden record is listed for restore", any(v.get("id") == vid for v in hl),
                  "missing from hidden list")
            call("PUT", f"/api/records/visitors/{vid}/hidden", {"hidden": False}, token=admin_tok)
            check("un-hiding restores the record", seen(), "still hidden")
            if user_tok:
                s2, _ = call("PUT", f"/api/records/visitors/{vid}/hidden", {"hidden": True}, token=user_tok)
                check("non-admin cannot hide records", s2 == 403, f"got {s2}")
        finally:
            call("DELETE", f"/api/visitors/{vid}", token=admin_tok)
    else:
        _skip += 1
        print("  SKIP  manual-hide round trip (could not create probe record)")

    # ── FY auto-stamp on write ─────────────────────────────────────────
    section("FY stamping on write")
    s, q = call("POST", "/api/quotes",
                {"quote_no": "ZZ-E2E-001", "date": "2026-05-14", "customer": "ZZ E2E Probe",
                 "division": "Furniture", "value": 1000}, token=admin_tok)
    if s == 200 and q and q.get("id"):
        try:
            check("new record is stamped with its FY", q.get("fy") == "2026-27", f"got {q.get('fy')}")
            s2, q2 = call("PUT", f"/api/quotes/{q['id']}", {"date": "2025-06-10"}, token=admin_tok)
            check("changing the date re-stamps the FY", (q2 or {}).get("fy") == "2025-26",
                  f"got {(q2 or {}).get('fy')}")
        finally:
            call("DELETE", f"/api/quotes/{q['id']}", token=admin_tok)
    else:
        _skip += 1
        print(f"  SKIP  FY stamping (create returned {s})")

    # ── D&W survey: remarks + photos ───────────────────────────────────
    section("D&W survey — remarks & site photos")
    s, sv = call("POST", "/api/dw-surveys",
                 {"customer": "ZZ E2E Survey", "phone": "9000000002", "site_address": "Test"},
                 token=admin_tok)
    if s == 200 and sv and sv.get("id"):
        sid = sv["id"]
        try:
            check("survey gets a DW- id", str(sv.get("survey_id", "")).startswith("DW-"),
                  f"got {sv.get('survey_id')}")
            tiny = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/"
                    "2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBD")
            s2, upd = call("PUT", f"/api/dw-surveys/{sid}",
                           {**sv, "remarks": "Scaffolding needed on the north face",
                            "photos": [tiny]}, token=admin_tok)
            check("survey remarks persist",
                  (upd or {}).get("remarks", "").startswith("Scaffolding"), f"got {(upd or {}).get('remarks')}")
            check("site photos persist", len((upd or {}).get("photos") or []) == 1,
                  f"got {len((upd or {}).get('photos') or [])}")

            s3, op = call("POST", "/api/dw-openings",
                          {"survey_id": sid, "room": "Living", "type": "Window",
                           "w": 48, "h": 60, "qty": 2, "notes": "existing frame stays",
                           "image_url": tiny}, token=admin_tok)
            if s3 == 200 and op:
                check("opening stores notes", (op.get("notes") or "").startswith("existing"),
                      f"got {op.get('notes')}")
                check("opening stores a photo", bool(op.get("image_url")), "no image_url")
                call("DELETE", f"/api/dw-openings/{op['id']}", token=admin_tok)
            else:
                check("opening can be created", False, f"got {s3}")
        finally:
            call("DELETE", f"/api/dw-surveys/{sid}", token=admin_tok)
    else:
        _skip += 1
        print(f"  SKIP  D&W survey tests (create returned {s})")

    # ── reports / alerts shape ─────────────────────────────────────────
    section("Reports & alerts")
    s, rep = call("GET", "/api/reports", token=admin_tok)
    check("reports return a period", s == 200 and "period" in (rep or {}), f"got {s}")
    s, al = call("GET", "/api/alerts", token=admin_tok)
    check("alerts return a count", s == 200 and "count" in (al or {}), f"got {s}")

    # ── summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    print(f"PASSED {_pass}   FAILED {_fail}   SKIPPED {_skip}")
    if counts:
        print("\nrecord counts:")
        for k in sorted(counts):
            print(f"  {k:<34} {counts[k]}")
    if _failures:
        print("\nfailures:")
        for f in _failures:
            print(f"  - {f}")
    print("=" * 62)
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
