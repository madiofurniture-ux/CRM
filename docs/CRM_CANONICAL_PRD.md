# PRD: Madio Canonical CRM v1

## 1. Problem Statement & Goals

**Problem.** The CRM (Next.js + FastAPI-style backend + MongoDB) was built for Madio's furniture business first, and its data model reflects that: `LeadBase`, `QuoteBase`, `CustomerBase`, `SaleBase` mix Salesforce-style CRM concepts (lead, opportunity, quote) with Madio-specific vocabulary and a single `division` string ("Furniture" / "MAP" / "D&W") to tell brands apart within one tenant. There is no config-driven way to onboard a genuinely new business (a different tenant, potentially an external SMB customer) without touching Python code.

**Goal.** Ship a **low-cost, multi-tenant CRM** for small/medium businesses: one codebase, one backend, one MongoDB database, tenants and brands distinguished by data, not by deploys. v1 adds a canonical entity layer (Account, Contact, Lead, Opportunity, Product, Quotation, Activity — Salesforce/Dynamics/Odoo-shaped) and a JSON-manifest module system so a new brand is "drop a manifest file," not "fork the repo."

**Non-goal.** v1 does not replace `backend/models.py` or its collections (`leads`, `quotes`, `sales`, `customers`, ...). Those keep running unchanged. The canonical layer is new, additive, and is the target shape for a gradual migration — see `docs/MODEL_MAPPING.md`.

## 2. Two Layers of Multi-Tenancy — the Central Design Decision

The repo already had a real multi-tenancy chokepoint before this work started: `backend/tenancy.py`'s `tenant_id`, stamped/scoped on every write/read, fail-closed (no tenant → matches nothing). That is the **hard security boundary** — it is what will separate one paying SMB customer from another in Phase 3.

Separately, Madio itself runs **three brands under one tenant** (`tenant_id="madio"`), distinguished today by a `division` field ("Furniture" / "MAP" / "D&W"). The task of this v1 is explicitly to give every canonical entity a `brand_id`. Rather than inventing a second, parallel isolation mechanism, v1 treats:

- **`tenant_id`** — who the customer is (a business subscribing to the CRM). Unchanged, reused as-is from `tenancy.py`.
- **`brand_id`** — which brand *within* that tenant a record belongs to (`madio_doors_windows`, `map_paints`, `navaki`, ...). New. Equivalent in spirit to the existing `division` field, but resolved against a **module manifest** (`backend/modules/<brand_id>/manifest.json`) instead of a hardcoded string, so a brand's custom fields, pipeline stages, and quotation templates come from config, not code.

A canonical-entity query is always scoped by both: `tenancy.scope()` for `tenant_id`, plus an explicit `brand_id` filter in `api_canonical.py`. Losing either one must fail closed (empty result), never fall through to "all brands" or "all tenants."

## 3. Canonical Entities (v1)

Implemented in `backend/models_canonical.py`. All seven carry `id`, `tenant_id`, `brand_id`, `created_at`, `updated_at`, `custom_data` (dict, for brand-specific fields the manifest declares).

| Entity | Purpose | Key relationships | Status field |
|---|---|---|---|
| **Account** | Org/person being sold to (Salesforce Account / Odoo `res.partner`) | — | `type`: prospect/customer/partner/vendor |
| **Contact** | A person at an Account | `account_id` → Account | — |
| **Lead** | Unqualified interest (Salesforce Lead) | `matched_account_id` → Account, `converted_opportunity_id` → Opportunity | `lead_status`: New/Contacted/Qualified/Converted/Lost |
| **Opportunity** | A deal in progress (Salesforce Opportunity) | `account_id` → Account (required), `contact_id` → Contact, `lead_id` → Lead | `stage_id` (brand pipeline) + `status`: open/won/lost |
| **Product** | Sellable item (Salesforce Product2 / Odoo `product.product`) | — | `active` bool |
| **Quotation** | Priced document (Odoo `sale.order` draft/sent) | `opportunity_id` → Opportunity (required), `account_id` → Account | `status`: draft/sent/accepted/rejected/expired |
| **Activity** | Logged interaction (Salesforce Activity / Odoo `mail.activity`) | `related_entity` + `related_id` → any of the above | `completed` bool |

See `docs/MODEL_MAPPING.md` for the field-by-field mapping from existing `models.py` classes.

## 4. Module System (Config-Driven Brand Extensions)

A **module** is one `backend/modules/<name>/manifest.json`. `core_crm` is the base module every brand depends on; a brand module (`madio_doors_windows`, `map_paints`, `navaki`) declares `depends: ["core_crm"]` plus its own `custom_fields`, `pipelines`, `quotations.templates`, and `permissions`. `backend/modules_loader.py` merges core + brand at request time (`load_for_brand(brand_id)`) — no database round-trip, no build step.

**Adding a new brand is: write a new manifest.json. No Python changes.** See `docs/MODULES_ARCHITECTURE.md` for the operator walkthrough.

## 5. API (v1)

`backend/api_canonical.py`, mounted at `/api/v1` alongside the existing `/api` router (unchanged). v1 ships Leads and Opportunities end-to-end (search/create/read/update/convert_lead/move_stage, and search/create/read/update/set_won/set_lost respectively), plus a minimal Accounts create/lookup path since Opportunities require a valid `account_id`, and `/api/v1/brands` to read a brand's merged manifest. See `docs/API_CANONICAL_SUMMARY.md` for the full table.

Contact/Product/Quotation/Activity have models but no dedicated `/api/v1` routes yet — deferred to v1.1 (§7); nothing about the module or tenancy design would need to change to add them.

## 6. Integration Requirements — What Stays As-Is

- **Existing `/api/*` routes, `models.py`, `server.py`'s `make_crud`** — untouched. `api_canonical.py` deliberately avoids importing `server.py` (it reads `request.app.state.db` directly, the same way `auth.get_current_user` already does) so there is no circular-import risk and no chance of destabilizing the existing router.
- **`tenancy.py`** — one additive edit: the seven new `crm_*` collections were added to `TENANT_COLLECTIONS` so `scope()`/`stamp()` cover them automatically. No existing behavior changed.
- **AI agents, Tally, CSV engine, notifications** — untouched; out of scope for v1.

## 7. Non-Functional Requirements

- **Performance**: new `crm_*` collections need `{tenant_id, brand_id}`-leading indexes — see `docs/MONGO_INDEXES.md`. No change to existing collections' performance profile.
- **Security**: `tenant_id` remains the hard isolation boundary (`tenancy.py`, unchanged, fail-closed). `brand_id` is validated against the module manifest on every `/api/v1` call (`_require_brand`) — an unregistered `brand_id` 400s rather than silently defaulting to `core_crm`'s config.
- **Low ops**: single Mongo database, single backend process, no per-brand deploy. A brand is data (a manifest file), not infrastructure.

## 8. Phased Rollout

- **Phase 1 (this PRD's scope, shipped)** — canonical models, module manifests for the three Madio brands, `/api/v1` for Leads + Opportunities, docs.
- **Phase 2** — Contact/Product/Quotation/Activity CRUD under `/api/v1`; wire the module manifest's `custom_fields` into a generic form-rendering contract for the frontend.
- **Phase 3** — onboard a real second *tenant* (not just brand) — a design partner or Madio's own second legal entity — to prove tenant isolation end-to-end, not just brand isolation within `tenant_id="madio"`.
- **Phase 4** — commercialization: self-service tenant signup, billing, external customers. v1's tenant/brand split is deliberately already shaped for this; nothing here should require redesigning it.

## 9. Scope: v1 vs Deferred

**In scope for v1 (shipped):** canonical models (7 entities), module manifest schema + loader, 3 brand manifests, `/api/v1/leads` + `/api/v1/opportunities` + minimal accounts + `/api/v1/brands`, docs.

**Deferred to v1.1+:** Contact/Product/Quotation/Activity API routes; permissions enforcement from the manifest's `permissions` block (currently declared but not yet checked in `api_canonical.py` — v1 relies on the same `get_current_user` auth as the rest of the app, no role gating on the new routes yet); migrating existing `leads`/`quotes`/`customers` data into the `crm_*` collections (v1 runs both in parallel, no migration).

## 10. Open Questions

- Should the existing `division` field on `models.py` records eventually just *become* `brand_id` (a rename/migration), or do the two stay separate indefinitely because the legacy collections are never migrated?
- Who validates a new brand's manifest before it ships (schema validation is structural only right now — a manifest with a bad pipeline shape fails at request time, not at file-save time)?
- Does Phase 3's second tenant need its own MongoDB database for compliance reasons, or does the "one database, multi-tenant by tenant_id" model hold even for external paying customers?
