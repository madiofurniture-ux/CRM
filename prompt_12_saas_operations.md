# Prompt 12: Running it as a service — indexes, limits, monitoring, deploy config (P2)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

The app was built for one company on one deployment. With many companies on
one backend (`render.yaml`, MongoDB Atlas, Netlify frontend), a few things
that were fine for one tenant become risks:

- `auth.get_current_user` now reads the `tenants` collection on **every**
  request (`enforce_subscription`), but there is no index on `tenants.id`
  (startup indexes in `server.py` ~line 10079 cover customers/leads/quotes only).
- Request rate limits exist for login only; one busy tenant can starve others.
- `render.yaml` doesn't declare the new env vars (`LOGIN_PROFILE_TILES`,
  `DEFAULT_TENANT`, `PUBLIC_SIGNUP`…), so a fresh deploy can't be configured
  from the blueprint.
- No per-tenant usage numbers for the platform owner (storage, records, API
  calls), and no error monitoring.

## Goal

The backend stays fast and fair as companies are added, deploys are
reproducible from the repo, and the owner can see each company's usage and
any errors.

## Scope

1. Indexes at startup: `tenants.id` (unique), `users.username` (unique),
   `users.tenant_id`, and `(tenant_id, …)` compound indexes for the hottest
   list queries of every collection in `tenancy.TENANT_COLLECTIONS` (check
   `docs/MONGO_INDEXES.md` and update it).
2. Cache the tenant's plan state for ~30 s in-process in
   `enforce_subscription` (invalidated by `PATCH /platform/tenants/{id}`), so
   it costs no DB read on most requests.
3. Per-tenant rate limiting middleware (token bucket keyed by tenant id,
   generous defaults, 429 with `Retry-After`); exempt health checks.
4. Usage metering: a daily job storing per-tenant counts (users, records per
   main collection, file storage bytes) shown on Platform → Customers.
5. `render.yaml` and `netlify.toml`: declare every env var the code reads, with
   comments; `docs/go-live-netlify-godaddy-hostinger.md` gains a "Multi-tenant
   deploy" section.
6. Optional Sentry (or similar) via `SENTRY_DSN`, with the tenant id as a tag
   and no personal data in events.
7. A `/api/health/deep` check (Mongo ping, storage backend reachable) for the
   uptime monitor.

## Tests

Index creation is idempotent; rate limiter isolates two tenants; the plan
cache returns fresh state after a platform update; health check reports a
failing dependency.

## Out of scope

Moving off Render/Atlas, per-tenant databases.
