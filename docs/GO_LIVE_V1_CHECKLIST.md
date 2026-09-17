# Go-Live Checklist — Canonical CRM v1

Repo: `C:\Users\jagad\Projects\CRMNew`. This feature is additive (new files
+ two edits to `backend/server.py`), so go-live risk is limited to "the new
routes work" — existing routes are unaffected by construction.

## Pre-deploy

- [ ] From `C:\Users\jagad\Projects\CRMNew\backend`, syntax-check the new
      files:
      ```
      python -c "import py_compile; [py_compile.compile(f, doraise=True) for f in ['models_canonical.py','modules_loader.py','api_canonical.py','server.py']]; print('OK')"
      ```
- [ ] Confirm the manifests parse and merge correctly:
      ```
      python -c "import modules_loader as ml; import json; print(json.dumps(ml.load_brand_config('madio_doors_windows'), indent=2))"
      python -c "import modules_loader as ml; import json; print(json.dumps(ml.load_brand_config('map_paints'), indent=2))"
      ```
- [ ] Confirm the app imports and mounts `/api/v1` without touching a live
      database (uses FastAPI's TestClient, no Mongo connection needed):
      ```
      python -c "from fastapi.testclient import TestClient; import server; c=TestClient(server.app); r=c.get('/openapi.json'); print(sorted(p for p in r.json()['paths'] if p.startswith('/api/v1')))"
      ```
- [ ] Apply the indexes in `docs/MONGO_INDEXES.md` to the target Mongo
      deployment (staging first, then production) before the deploy that
      exposes `/api/v1` — an index build on an empty collection is instant,
      no downtime risk, and doing it first avoids an unindexed collection
      ever taking traffic.
- [ ] Review `git diff` on `backend/server.py` — the only existing file this
      feature touches — confirm it's exactly the two lines documented in
      `docs/CRM_CANONICAL_PRD.md` (one import, one `include_router` call).

## Deploy

- [ ] Standard deploy for this repo (same process as any other backend
      change — no new environment variables, no new services, no schema
      migration to run).
- [ ] `backend/modules/` must ship with the deploy artifact (it's plain
      files under `backend/`, so a normal `git`-based deploy already
      includes it — nothing extra to configure).

## Post-deploy

- [ ] `curl https://<host>/api/v1/leads -H "Authorization: Bearer <token>"`
      for a known test tenant returns `200 []` (empty list, not an error) —
      confirms the router mounted and tenant scoping didn't break auth.
- [ ] Create one test lead, convert it, confirm an opportunity appears:
      ```
      curl -X POST https://<host>/api/v1/leads -H "Authorization: Bearer <token>" \
        -H "Content-Type: application/json" -d '{"name":"Go-live smoke test"}'
      # then POST /api/v1/leads/{id}/convert with the returned id
      ```
- [ ] Confirm `/api` (existing routes) still work unchanged — hit any
      existing endpoint your team already monitors (e.g. `/api/health`).
- [ ] Watch application logs for `crm_leads`/`crm_opportunities` Mongo
      errors in the first hour of traffic.

## Rollback

Additive feature, so rollback is a plain revert:

- [ ] Revert the two `backend/server.py` lines (`import api_canonical` and
      `app.include_router(api_canonical.router)`) or redeploy the previous
      commit — either way `/api/v1` disappears and every other route is
      unaffected, since nothing else changed.
- [ ] No data cleanup needed — `crm_leads`/`crm_opportunities` documents
      created during the incident can be left in place (they're isolated,
      unindexed-by-anything-else collections) or dropped:
      `db.crm_leads.drop(); db.crm_opportunities.drop();` — safe because
      nothing else reads these collections.

## Operator Checks — multi-tenancy and brand isolation

- [ ] As a user in tenant A, `GET /api/v1/leads` after creating a lead in
      tenant B (different login/token) must NOT show tenant B's lead —
      confirms `tenancy.scope()` is being applied (it's registered for
      `crm_leads`/`crm_opportunities` in `api_canonical.py` at import time;
      verify with `python -c "import api_canonical, tenancy; print('crm_leads' in tenancy.TENANT_COLLECTIONS, 'crm_opportunities' in tenancy.TENANT_COLLECTIONS)"` → both `True`).
- [ ] A request with no valid token gets `401`, not an empty list — a
      caller must be authenticated to reach the fail-closed tenant filter
      at all.
- [ ] `POST /api/v1/leads/{id}/move_stage` with a `lead_status` not in the
      caller's brand's manifest returns `400` with the valid list in the
      error — confirms brand-specific pipeline validation is live, not
      silently accepting any string.
- [ ] Two different brands' `move_stage` calls accept different valid
      values (e.g. `madio_doors_windows`'s Opportunity pipeline includes
      `site_survey`; `map_paints`'s does not) — confirms manifests are
      actually brand-specific, not all resolving to `core_crm`.
