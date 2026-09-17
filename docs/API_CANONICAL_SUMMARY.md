# Canonical CRM API — v1 Summary

Base path: `/api/v1`. Auth: same Bearer JWT as the rest of the app
(`Authorization: Bearer <token>` from `/api/auth/login`). Every route is
scoped to the caller's `tenant_id` (`brand_id`) via `tenancy.py`.

## Leads

| Method | Path | Purpose | Main fields |
|---|---|---|---|
| GET | `/api/v1/leads` | Search/list leads. Query params: `q` (name substring), `lead_status` | — |
| POST | `/api/v1/leads` | Create a lead | `name*, company, phone, email, source, lead_status, owner_id, notes` |
| GET | `/api/v1/leads/{lead_id}` | Read one lead | — |
| PUT | `/api/v1/leads/{lead_id}` | Update a lead (partial) | any Lead field except `id`/`tenant_id`/`created_at` |
| POST | `/api/v1/leads/{lead_id}/convert` | Convert a qualified lead into an Opportunity; marks the lead `converted` | — (server-derived) |
| POST | `/api/v1/leads/{lead_id}/move_stage` | Move a lead to a new `lead_status`, validated against the brand's configured pipeline | `{"lead_status": "..."}` |

## Opportunities

| Method | Path | Purpose | Main fields |
|---|---|---|---|
| GET | `/api/v1/opportunities` | Search/list opportunities. Query params: `q` (name substring), `stage_id`, `account_id` | — |
| POST | `/api/v1/opportunities` | Create an opportunity | `name*, account_id, contact_id, lead_id, stage_id, amount, probability, close_date, owner_id` |
| GET | `/api/v1/opportunities/{opp_id}` | Read one opportunity | — |
| PUT | `/api/v1/opportunities/{opp_id}` | Update an opportunity (partial) | any Opportunity field except `id`/`tenant_id`/`created_at` |
| POST | `/api/v1/opportunities/{opp_id}/set_won` | Mark the opportunity won; stage moves to the brand's `won` (or equivalent) stage, probability → 100 | — |
| POST | `/api/v1/opportunities/{opp_id}/set_lost` | Mark the opportunity lost | `{"lost_reason": "..."}` |

`*` = required.

## Not yet exposed (models exist in `models_canonical.py`, API is v1.1)

Account, Contact, Product, Quotation, Activity — no REST endpoints yet.
Adding one follows the same shape as Leads/Opportunities above: a router
function per verb in `api_canonical.py`, scoped with `tenancy.scope()`/
`tenancy.stamp()`, stage/field lookups (if any) through `modules_loader`.
