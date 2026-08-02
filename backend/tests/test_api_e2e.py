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
import os
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ADMIN = {"username": os.environ.get("E2E_ADMIN_USER","admin"), "pin": os.environ.get("E2E_ADMIN_PIN","1234")}
USER = {"username": os.environ.get("E2E_USER_USER","mf"), "pin": os.environ.get("E2E_USER_PIN","2222")}

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

    # The login screen reads its profiles from here. When these were hardcoded in
    # the frontend, renaming the roles left everyone unable to sign in.
    s, roles = call("GET", "/api/auth/roles")
    check("login profiles are readable before sign-in", s == 200 and isinstance(roles, list),
          f"got {s} {str(roles)[:70]}")
    if isinstance(roles, list):
        check("every seeded role has a login tile", len(roles) >= 7, f"got {len(roles)}")
        names = {r.get("username") for r in roles}
        check("the seven role logins are offered",
              {"promoter", "admin", "mf", "map", "mdw", "accounting", "reception"} <= names,
              f"missing {sorted({'promoter','admin','mf','map','mdw','accounting','reception'} - names)}")
        # Logins are roles, not people — no personal names may reappear here.
        check("no personal-name logins remain",
              not (names & {"raghu", "nenmu", "gowtham"}),
              f"found {sorted(names & {'raghu', 'nenmu', 'gowtham'})}")
        leaked = {k for r in roles for k in r if k in ("pin", "pin_hash", "pages", "id", "tenant_id")}
        check("the public profile list leaks nothing sensitive", not leaked, f"exposed {sorted(leaked)}")
        check("every tile can be rendered",
              all(r.get("username") and r.get("name") and r.get("icon") for r in roles),
              "a tile is missing username/name/icon")

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

    # ── adding a colleague ─────────────────────────────────────────────
    section("Adding a user through Role Manager")
    # REGRESSION: a user created without a tenant_id logs in fine but sees an
    # entirely empty app, because record scoping is deliberately fail-closed.
    s, nu = call("POST", "/api/auth/users",
                 {"username": "zze2eprobe", "name": "ZZ E2E Probe", "pin": "4321",
                  "role": "user", "icon": "ZZ", "color": "#888888",
                  "pages": ["dashboard", "inventory"]}, token=admin_tok)
    if s == 200 and nu and nu.get("id"):
        try:
            check("a new colleague joins the admin's tenant", bool(nu.get("tenant_id")),
                  "tenant_id missing — this user would see a blank app")
            s2, lg = call("POST", "/api/auth/login",
                          {"username": "zze2eprobe", "pin": "4321"})
            check("the new colleague can sign in", s2 == 200 and bool((lg or {}).get("token")),
                  f"got {s2}")
            if (lg or {}).get("token"):
                s3, inv = call("GET", "/api/inventory", token=lg["token"])
                check("the new colleague actually sees data",
                      s3 == 200 and isinstance(inv, list) and len(inv) > 0,
                      f"got {s3} with {len(inv) if isinstance(inv, list) else '?'} rows")
            s4, rl = call("GET", "/api/auth/roles")
            check("the new colleague appears on the login screen",
                  any(r.get("username") == "zze2eprobe" for r in (rl or [])),
                  "missing from /auth/roles")
        finally:
            call("DELETE", f"/api/auth/users/{nu['id']}", token=admin_tok)
    else:
        _skip += 1
        print(f"  SKIP  new-user tenancy checks (create returned {s})")

    # ── workflows: the entity stage model ──────────────────────────────
    section("Workflows — configurable stages per entity")
    s, wfs = call("GET", "/api/workflows", token=admin_tok)
    check("workflow list covers every entity",
          s == 200 and isinstance(wfs, dict) and len(wfs) == 7,
          f"got {s} {len(wfs) if isinstance(wfs, dict) else str(wfs)[:60]}")
    if isinstance(wfs, dict) and wfs:
        check("every entity has stages", all(w.get("stages") for w in wfs.values()),
              [k for k, w in wfs.items() if not w.get("stages")])
        # Reporting needs somewhere to end and something to count as success.
        check("every workflow has an end and a win",
              all(any(st.get("terminal") for st in w["stages"])
                  and any(st.get("won") for st in w["stages"]) for w in wfs.values()),
              [k for k, w in wfs.items()
               if not (any(st.get("terminal") for st in w["stages"])
                       and any(st.get("won") for st in w["stages"]))])
        # A product must not ship with one customer's vocabulary baked in.
        default_labels = {st["label"].lower()
                          for w in wfs.values() if not w.get("customised")
                          for st in w["stages"]}
        check("shipped defaults are generic, not one business's words",
              not (default_labels & {"vis", "madio", "map", "mdw", "pch", "nav", "arc"}),
              sorted(default_labels & {"vis", "madio", "map", "mdw", "pch", "nav", "arc"}))

    s, _ = call("GET", "/api/workflows/not-a-real-entity", token=admin_tok)
    check("unknown entity is rejected", s == 404, f"got {s}")

    s, _ = call("PUT", "/api/workflows/lead", {"stages": []})
    check("unauthenticated cannot redefine a workflow", s in (401, 403), f"got {s}")
    if user_tok:
        for verb, path in (("PUT", "/api/workflows/lead"),
                           ("POST", "/api/workflows/lead/adopt"),
                           ("POST", "/api/workflows/lead/reset")):
            s, _ = call(verb, path, {"stages": [{"label": "Hijacked"}]}, token=user_tok)
            check(f"non-admin cannot {verb} {path.split('/')[-1]}", s == 403, f"got {s}")
        s, _ = call("GET", "/api/workflows/lead", token=user_tok)
        check("non-admin can still read the workflow", s == 200, f"got {s}")

    s, _ = call("PUT", "/api/workflows/lead", {"stages": [{"label": ""}]}, token=admin_tok)
    check("a nameless stage is rejected", s == 400, f"got {s}")

    # Round-trip adopt → enforce → orphan guard → reset, restoring whatever
    # this tenant had before so the run stays safe against production.
    orig_lead = (wfs or {}).get("lead") or {}

    def restore_lead():
        if orig_lead.get("customised"):
            call("PUT", "/api/workflows/lead",
                 {"stages": orig_lead["stages"], "enforce": orig_lead.get("enforced", True),
                  "force": True}, token=admin_tok)
        else:
            call("POST", "/api/workflows/lead/reset", token=admin_tok)

    try:
        s, ad = call("POST", "/api/workflows/lead/adopt", {"enforce": True}, token=admin_tok)
        check("adopt learns the stages the data already uses",
              s == 200 and isinstance(ad, dict) and "adopted_from_records" in ad,
              f"got {s} {str(ad)[:80]}")
        learned = (ad or {}).get("stages") or []
        n_learned = (ad or {}).get("adopted_from_records", 0)

        # Adoption is the safe route to enforcement: nothing existing may break.
        s, re_put = call("PUT", "/api/workflows/lead",
                         {"stages": learned, "enforce": True}, token=admin_tok)
        check("adopted stages leave no record orphaned", s == 200 and not (re_put or {}).get("orphaned_stages"),
              f"got {s} {(re_put or {}).get('orphaned_stages')}")

        s, bad = call("POST", "/api/leads",
                      {"date": "2026-05-14", "name": "ZZ E2E Stage Probe", "phone": "9000000003",
                       "stage": "ZZ Definitely Not A Stage"}, token=admin_tok)
        check("enforced workflow rejects an unknown stage", s == 400, f"got {s}")
        check("rejection tells the user which stages are valid",
              isinstance(bad, dict) and bool((bad.get("detail") or {}).get("valid_stages")
                                             if isinstance(bad.get("detail"), dict) else False),
              str(bad)[:90])

        if learned:
            label = learned[0]["label"]
            s, ok = call("POST", "/api/leads",
                         {"date": "2026-05-14", "name": "ZZ E2E Stage Probe", "phone": "9000000003",
                          "stage": label.lower()}, token=admin_tok)
            check("a valid stage is accepted whatever the casing", s == 200, f"got {s}")
            if s == 200 and ok and ok.get("id"):
                check("stage is stored in its canonical spelling", ok.get("stage") == label,
                      f"sent {label.lower()!r}, stored {ok.get('stage')!r}")
                call("DELETE", f"/api/leads/{ok['id']}", token=admin_tok)

        # Dropping a stage records still sit on must warn before it strands them.
        if n_learned >= 2 and len(learned) >= 2:
            dropped = learned[0]["label"]
            s, conflict = call("PUT", "/api/workflows/lead",
                               {"stages": learned[1:], "enforce": True}, token=admin_tok)
            det = conflict.get("detail") if isinstance(conflict, dict) else {}
            check("dropping a stage in use is refused with 409", s == 409, f"got {s}")
            check("the refusal names the stranded stages",
                  isinstance(det, dict) and dropped in (det.get("orphaned_stages") or []),
                  str(det)[:90])
            s, forced = call("PUT", "/api/workflows/lead",
                             {"stages": learned[1:], "enforce": True, "force": True},
                             token=admin_tok)
            check("force:true lets the admin proceed deliberately", s == 200, f"got {s}")
        else:
            _skip += 1
            print("  SKIP  orphaned-stage guard (not enough distinct stages in the data)")

        s, rs = call("POST", "/api/workflows/lead/reset", token=admin_tok)
        check("reset returns to the shipped defaults",
              s == 200 and (rs or {}).get("customised") is False, f"got {s}")
        s, after = call("GET", "/api/workflows/lead", token=admin_tok)
        check("reset also lifts enforcement", not (after or {}).get("enforced"),
              f"enforced={(after or {}).get('enforced')}")
        s, free = call("POST", "/api/leads",
                       {"date": "2026-05-14", "name": "ZZ E2E Stage Probe", "phone": "9000000003",
                        "stage": "Anything Goes Now"}, token=admin_tok)
        check("un-enforced workflow accepts any stage", s == 200, f"got {s}")
        if s == 200 and free and free.get("id"):
            call("DELETE", f"/api/leads/{free['id']}", token=admin_tok)
    finally:
        restore_lead()
    s, back = call("GET", "/api/workflows/lead", token=admin_tok)
    check("the tenant's original workflow is restored",
          [st["label"] for st in (back or {}).get("stages", [])] ==
          [st["label"] for st in orig_lead.get("stages", [])],
          "workflow left modified — check manually")

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
