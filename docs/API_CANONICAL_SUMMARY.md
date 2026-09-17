# Canonical CRM API (v1) — `/api/v1`

All routes require the same `Authorization: Bearer <token>` as the existing `/api` router (`auth.get_current_user`). Every route is scoped by the caller's `tenant_id` (from their user record, unchanged tenancy behavior) and, for entity routes, an explicit `brand_id`.

| Method | Path | Purpose | Main fields |
|---|---|---|---|
| GET | `/api/v1/brands` | List every onboarded brand_id | — |
| GET | `/api/v1/brands/{brand_id}/config` | Merged manifest (core_crm + brand) | `custom_fields`, `pipelines`, `quotations`, `permissions` |
| GET | `/api/v1/leads?brand_id=&q=&lead_status=` | Search leads | — |
| POST | `/api/v1/leads` | Create a lead | `brand_id`*, `name`*, `phone`, `email`, `source`, `estimated_value` |
| GET | `/api/v1/leads/{id}` | Read one lead | — |
| PUT | `/api/v1/leads/{id}` | Update a lead | any Lead field except `id`/`tenant_id`/`brand_id`/`created_at` |
| POST | `/api/v1/leads/{id}/move_stage` | Move to a `lead_status` valid for the lead's brand pipeline | `lead_status`* |
| POST | `/api/v1/leads/{id}/convert` | Convert lead → Account (matched or new) + Opportunity | — (idempotent; re-calling returns the existing conversion) |
| GET | `/api/v1/opportunities?brand_id=&q=&stage_id=&account_id=&status=` | Search opportunities | — |
| POST | `/api/v1/opportunities` | Create an opportunity | `brand_id`*, `name`*, `account_id`* (must exist), `amount`, `close_date` |
| GET | `/api/v1/opportunities/{id}` | Read one opportunity | — |
| PUT | `/api/v1/opportunities/{id}` | Update an opportunity | any Opportunity field except `id`/`tenant_id`/`brand_id`/`created_at` |
| POST | `/api/v1/opportunities/{id}/set_won` | Close won — sets `status=won`, `probability=100`, `stage_id` to the brand's `won` pipeline stage | — |
| POST | `/api/v1/opportunities/{id}/set_lost` | Close lost — sets `status=lost`, `probability=0`, `stage_id` to the brand's terminal non-won stage | — |

\* required

## Not yet exposed (models exist, routes deferred to v1.1)

Contact, Product, Quotation, Activity — see `docs/CRM_CANONICAL_PRD.md` §9.

## Minimal Accounts path

There is no `/api/v1/accounts` search/list endpoint yet. Accounts are created two ways in v1: automatically by `/leads/{id}/convert` (matches an existing Account via the lead's `matched_account_id`, or creates a new one from the lead's name/phone/email), or you can insert directly into `crm_accounts` for a seed/test setup. A dedicated Accounts CRUD surface is v1.1 scope.
