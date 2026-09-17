# Go-Live Checklist — Canonical CRM v1

Working directory for every command below: `C:\Users\jagad\Projects\CRMNew`.

## Pre-Deploy

- [ ] Confirm the new files are present:
  ```
  Get-ChildItem backend\models_canonical.py, backend\api_canonical.py, backend\modules_loader.py
  Get-ChildItem backend\modules -Recurse -Filter manifest.json
  ```
- [ ] Sanity-check every manifest parses and merges cleanly:
  ```
  cd backend
  python -c "import modules_loader as ml; [print(b, ml.load_for_brand(b)['pipelines'].keys()) for b in ml.list_brands()]"
  ```
- [ ] Confirm the app still imports and both routers are mounted:
  ```
  python -c "import server; print(len(server.api.routes), len(server.api_canonical.router.routes))"
  ```
- [ ] Run the existing test suite — this change must not regress it:
  ```
  python -m pytest tests -q
  ```
- [ ] Create the new indexes from `docs/MONGO_INDEXES.md` against the target Mongo instance (staging first, always).

## Deploy

- [ ] Standard deploy path for this repo (no new dependencies were added — `requirements.txt`/`requirements-prod.txt` unchanged, `pydantic`/`fastapi`/`pymongo` already present).
- [ ] Restart the backend process (`modules_loader`'s manifest cache is per-process — a running process will not pick up a manifest edited after it started).

## Post-Deploy Smoke Test

```
# replace <TOKEN> with a real login token from POST /api/auth/login
curl -s https://<host>/api/v1/brands
curl -s -H "Authorization: Bearer <TOKEN>" "https://<host>/api/v1/leads?brand_id=madio_doors_windows"
curl -s -X POST -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"brand_id":"madio_doors_windows","name":"Smoke Test Lead","phone":"9999999999"}' \
  https://<host>/api/v1/leads
```
- [ ] `/api/v1/brands` returns `["madio_doors_windows","map_paints","navaki"]`.
- [ ] The created lead round-trips with `id`, `tenant_id`, `created_at`, `updated_at` populated.
- [ ] Existing `/api/*` routes (e.g. `/api/leads`, `/api/quotes`) still respond normally — this deploy must not have touched their behavior.

## Operator Checks — Multi-Tenancy and Brand Isolation

- [ ] **Brand isolation**: create a lead with `brand_id=madio_doors_windows`, then `GET /api/v1/leads?brand_id=map_paints` — it must NOT appear.
- [ ] **Unknown brand rejected**: `GET /api/v1/leads?brand_id=not_a_real_brand` must return `400`, never an empty-but-successful list (an unregistered brand silently returning "no results" would look like a working brand with zero data).
- [ ] **Tenant isolation** (unchanged mechanism, still worth re-checking after this deploy): a user from a different `tenant_id` must get `404` reading another tenant's lead by `id`, not the record.
- [ ] **Convert idempotency**: call `/leads/{id}/convert` twice on the same lead; the second call must return the same `opportunity_id` as the first, not create a second Opportunity.

## Rollback

This deploy is purely additive at the code level (new files + two small edits to `tenancy.py`'s `TENANT_COLLECTIONS` set and `server.py`'s router mounting). Rollback is a straight revert of the commit(s):

```
git log --oneline -5                       # find the commit(s) to revert
git revert <commit-sha>                    # or: git checkout <previous-sha> -- backend/server.py backend/tenancy.py
```

No data migration ran, so there is nothing to roll back at the database level — the `crm_*` collections simply stop being written to once the code reverts. Deleting them is optional cleanup, never required for rollback safety:
```
# optional, only if you want to remove the test data these smoke tests created
mongosh $env:MONGO_URL --eval "db.getSiblingDB('madio_crm').crm_leads.drop(); db.getSiblingDB('madio_crm').crm_opportunities.drop(); db.getSiblingDB('madio_crm').crm_accounts.drop();"
```
