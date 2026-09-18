# Phase 2 — Sales Record Chain: Plan + Result

## Scope decision (before implementation)

Phase 2 as specified is large (Account/Contact APIs, Teams/assignment,
visitor-attribution, typed quotation lines with discount gates, won-quote ->
Sales Order with immutable IDs, activity timeline, chain-integrity tests).
Per the same judgment applied in Phase 1 — and per `docs/
ODOO_MADIO_DECISION.md`'s explicit finding that quotation logic should
**extend the working legacy `quotes` engine, not fork a second one from the
canonical stub** — this pass scopes to the parts that are additive,
low-risk, and don't touch financial arithmetic:

**In this pass:**
1. `/api/v1/accounts` and `/api/v1/contacts` — models already existed
   (`models_canonical.py`) with no router. Mirrors `api_canonical.py`'s
   existing Lead/Opportunity CRUD pattern exactly.
2. `/api/v1/activities` — same situation (model existed, no router).
   Generic timeline entries against any canonical entity.
3. Tenant-isolation + duplicate/chain-integrity tests for all of the above,
   extending `test_tenant_isolation_api.py` again.

**Explicitly deferred, not implemented this pass** (documented, not silently
dropped):
- **Team / owner / assignment routing** — genuinely new entity with design
  decisions (round-robin? manual? per-brand?) that deserve their own
  scoping conversation, not a rushed default.
- **Opportunity -> versioned Quotation with typed lines, discount gates,
  won -> Sales Order** — per `ODOO_MADIO_DECISION.md`, this should extend
  the legacy `quotes`/`sales` collections (add `brand_id`, expose under
  `/api/v1/quotations` as a wrapper), not be built fresh against the
  canonical `Quotation` stub. That is real, careful surgery on the
  financial engine every quote in production runs through — it needs its
  own session with its own test pass, not a slice at the end of this one.
- **Visitor-to-lead conversion attribution** — the legacy `visitors`
  collection and canonical `crm_leads` are unrelated today; wiring
  attribution between them is a data-modeling decision (does a canonical
  Lead gain a `visitor_id` field? Does conversion become a legacy-side
  concern instead?) better made deliberately.
- **Follow-up tasks** tied to the activity timeline — `Activity.type`
  already includes `"task"`; a dedicated follow-up/reminder mechanism on
  top of that is new scope, not implemented.

## What was implemented

### `backend/api_canonical.py` — two new resource families

- `POST/GET /api/v1/accounts`, `GET/PUT /api/v1/accounts/{id}` — full CRUD
  on `Account`, mirroring the existing Lead/Opportunity pattern exactly
  (`_insert`/`_apply_update`/`_get_or_404` helpers, `tenancy.scope`/`stamp`,
  `_require_brand`).
- `POST/GET /api/v1/contacts`, `GET/PUT /api/v1/contacts/{id}` — same
  pattern. `POST` validates `account_id` refers to a real, same-tenant
  Account (mirrors the existing `opportunities_create`'s `account_id`
  validation).
- `POST/GET /api/v1/activities`, `GET /api/v1/activities/{id}` — timeline
  entries. `POST` validates `related_entity`/`related_id` refers to a real
  record in the corresponding collection (accounts/contacts/leads/
  opportunities/quotations), so an activity can never point at a
  non-existent or cross-tenant record. No `PUT` — activities are an
  append-only log by design (matches "chatter" semantics from the Odoo
  comparison), so there is nothing to edit; a mistaken activity gets a new
  correcting entry, not a silent rewrite.

No changes to `models_canonical.py` — the models already had everything
needed (`AccountCreate`, `ContactCreate`, `ActivityCreate` were already
defined, just unused).

### Tests

Extended `backend/tests/test_tenant_isolation_api.py`:
- `crm_accounts` (`/api/v1/accounts`) and `crm_contacts`
  (`/api/v1/contacts`) added to the write-seed + read-isolation +
  cross-tenant PUT-rejection loop (same pattern as `crm_leads` in Phase 1).
- A dedicated chain-integrity check: creating a Contact with an
  `account_id` belonging to a DIFFERENT tenant must fail (`400`/`404`, not
  silently succeed with a dangling cross-tenant reference) — this is the
  "duplicate conversion and tenant isolation" chain-integrity concern the
  mission calls out specifically for Phase 2.
- A dedicated activity-integrity check: creating an Activity with
  `related_id` pointing at another tenant's Account must fail the same way.

## Verification run this pass

```
cd backend
python -m py_compile api_canonical.py
python -m pytest tests/ -q                                                # full suite
python tests/test_tenant_isolation_api.py --base http://127.0.0.1:8000    # extended isolation
```

Results and live curl smoke tests are in the final chat summary for this
pass, not duplicated here.
