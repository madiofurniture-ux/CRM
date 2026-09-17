# Canonical CRM v1 — PRD

## Problem

MADIO runs three brands (Doors & Windows, MAP Paints, Navaki) on one
codebase, but the domain model was written for one business's vocabulary.
Adding a brand today means new hardcoded stage lists and new fields wired
into shared routes. That doesn't scale to "sell this CRM to other SMBs."

## Goal

A **low-cost, multi-tenant CRM**: one codebase, one FastAPI backend, one
MongoDB database, serving every brand (and later, every customer) by
`tenant_id` (referred to as `brand_id` in this PRD — see
[MODEL_MAPPING.md](MODEL_MAPPING.md)). Adding a brand should mean writing a
config file, not shipping code.

## v1 scope

- Canonical entities (`backend/models_canonical.py`): Account, Contact,
  Lead, Opportunity, Product, Quotation, Activity — aligned with
  Salesforce/Dynamics/Odoo's standard objects, kept minimal.
- Config-driven brand extensions (`backend/modules/*/manifest.json` +
  `backend/modules_loader.py`): custom fields, pipeline stages, quotation
  templates and permissions per brand, no code change to add a brand.
- REST API skeleton for the two entities with the most day-to-day traffic —
  Leads and Opportunities — under `/api/v1`, brand-scoped.
- Existing `/api` routes (leads, quotes, sales, projects, ...) are
  untouched; the canonical layer is additive. See MODEL_MAPPING.md for the
  migration path from the old models to these.

## Out of scope for v1

- Account/Contact/Product/Quotation/Activity REST endpoints (models exist;
  API ships once Leads/Opportunities prove the pattern).
- UI for the canonical entities (the existing frontend keeps using the
  legacy `/api` routes for now).
- Automatic backfill/migration of existing `leads`/`quotes` data into the
  canonical collections — that's a deliberate v2 decision once the shape of
  v1 is validated in production.
- Per-tenant billing/plan limits (commercialization concern, not a v1
  blocker for MADIO's own three brands).

## Multi-brand model

One MongoDB database. Every canonical document carries `tenant_id`
(`brand_id`). Reads are scoped, writes are stamped, both via the existing
`tenancy.py` chokepoint — no new tenancy mechanism. A brand's pipeline
stages and custom fields come from `backend/modules/<brand_id>/manifest.json`
via `modules_loader.py`, not from a database row, so a brand is fully
defined by a file an operator can read, diff and version-control.

## Integrations

- `quotation_templates.py` — a Quotation's `template_id` refers to an
  existing template; the canonical layer does not reimplement templating.
- `lifecycle.py` — stage-validation helpers remain the source of truth for
  the legacy collections; canonical Opportunity/Lead stage validation goes
  through `modules_loader.pipeline_for()` instead, since brand-specific
  pipelines are config, not code.

## Non-functional

- **Cost**: no new infrastructure — same Mongo instance, same FastAPI
  process, same deploy. New collections (`crm_leads`, `crm_opportunities`,
  ...) only.
- **Isolation**: fail-closed tenant scoping (a caller with no `tenant_id`
  matches nothing), inherited from `tenancy.py` verbatim.
- **Backward compatibility**: zero changes to existing `/api` routes,
  models, or collections.

## Phased rollout

1. **v1 (this PRD)**: models + module system + Leads/Opportunities API +
   docs. Ship dark — no UI wired to it yet.
2. **v1.1**: Account/Contact/Product/Quotation/Activity endpoints; a real
   frontend surface for at least one brand.
3. **v2**: migrate one brand's legacy `leads`/`quotes` traffic onto the
   canonical collections end-to-end; retire the parallel path for that
   brand once validated.
4. **v3**: external customer onboarding — brand manifest + a signup flow,
   no engineering per customer.

## Open questions

- Do legacy collections (`leads`, `quotes`, `sales`) get migrated in place
  or does the canonical layer become the only path for *new* tenants while
  MADIO's three brands stay on the legacy path indefinitely?
- Where does `permissions.py`'s existing Role/module matrix plug into the
  manifest's `permissions` block — same system, brand-scoped, or a second
  system for canonical-only entities?
