# Madio Canonical CRM v1 – PRD (ECC PLAN-PRD pattern)

## Problem Statement & Goals

Madio's CRM (`backend/models.py`, `server.py`, `tenancy.py`, `quotation_templates.py`, `lifecycle.py`) already has real multi-tenant bones — `tenant_id` scoping, per-tenant workflow stages, per-tenant custom fields (`tenancy.py`) — but its **entity vocabulary is Madio-specific**: `Lead`, `Visitor`, `Quote`, `DWOpening`/`DWSurvey` (doors & windows survey fields), `Division` hardcoded to `["Furniture", "MAP", "D&W"]` (`lifecycle.py`), Tally voucher mapping tuned to Madio's chart of accounts (`tally.py`). A sister brand in paints or a different manufacturing vertical cannot onboard without a code fork.

**Goals for v1:**
- Introduce a canonical object model (Account, Contact, Lead, Opportunity, Product, Quotation, Activity) that Madio's existing entities map onto without a rewrite.
- Let a second brand configure itself (pipelines, custom fields, terminology) as **data**, not code — reusing the pattern `tenancy.py` already proved for stages/custom fields.
- Preserve every existing Madio workflow (petty cash, commissions, D&W survey, Tally export, agent tasks) as a **module** layered on the canonical core, not deleted.
- Keep the stack: Next.js frontend, Python backend, MongoDB, Vercel hosting. No re-platforming.

**Non-goal:** achieving Salesforce/Dynamics/Odoo feature parity. The goal is *shape compatibility* (so integrations, imports, and future engineers reason about the data the same way), not clone parity.

## Target Users

| User | Need |
|---|---|
| Madio internal (sales, ops, finance, admin) | Zero regression — same UI/URLs/data continue working through and after the migration. |
| Sister brands (retail, manufacturing, interiors — doors/windows, paints) | Stand up a tenant with their own pipeline stages, product catalog shape, and terminology without a code change or fork. |
| Future external customers (v2+, out of scope for v1) | Eventually self-serve provisioning. v1 only needs the data model and tenancy to not *block* this later. |

## Canonical Entities & Relationships

Mapped to existing models where one already exists; net-new where it doesn't.

| Canonical object | Maps to today | Relationship |
|---|---|---|
| **Account** | *New* — currently implicit in `Customer`/`Architect`/`Vendor` as separate flat entities | An Account is a company or household. Contacts, Opportunities, and Quotations belong to one. |
| **Contact** | `Customer`, `Architect`, `RecordContact`, `Visitor.reference_id` | A person, optionally linked to an Account. `RecordContactBase` (`models.py:1074`) already generalizes "a contact attached to some record" — canonical Contact absorbs this. |
| **Lead** | `Lead` (`models.py:154`), `Visitor` (`models.py:108`) | Pre-Opportunity interest. `Visitor` is effectively a walk-in Lead subtype today; v1 keeps them distinct types feeding the same Lead pipeline rather than forcing a merge that would break walk-in-specific fields (`customer_type`, `site_visit`). |
| **Opportunity** | `Quote`/`QuoteBase` (`models.py:275`) + `Sale` (`models.py:338`) | A Quote *is* the Opportunity once a Lead is qualified; `Sale` is its Closed-Won terminal state. Canonical model treats Quote-stage progression (`lifecycle.py` `QUOTE_STAGES`) as the Opportunity pipeline. |
| **Product** | `InventoryItem` (`models.py:383`), `ProductConfig` (`models.py:1644`) | Catalog line. Division-specific attributes (fabric, finish, glass spec) live as module extensions, not core fields. |
| **Quotation** | `Quote` + `QuoteLine` (`models.py:1417`) | Line items reference Product; header references Opportunity/Account/Contact. |
| **Activity** | `Meet` (`models.py:759`), `Task` (`models.py:446`), `RemarkEntry`/`log[]` fields scattered across Lead/Quote/AgentTask | Currently every entity carries its own ad hoc log array. Canonical Activity is a first-class, polymorphic (`subject_type`/`subject_id`) timeline entry — same shape `agent_bridge.py`'s conversation log and `tenancy.WORKFLOW_ENTITIES` already assume, generalized. |

**Relationships:** Account 1—N Contact; Account/Contact 1—N Lead; Lead 1—1 (on conversion) Opportunity; Opportunity N—N Product (via Quotation line items); Account/Opportunity/Lead 1—N Activity.

## Multi-Brand Requirements

- **Tenant isolation** — already load-bearing (`tenancy.py` fail-closed scoping). v1 requirement: every canonical + module collection is added to `TENANT_COLLECTIONS`; no new collection ships without scoping, enforced by the same chokepoint, not per-endpoint checks.
- **Brand config** — extend `TenantBusinessProfile` (`models.py:1243`) to carry: canonical-entity display labels (e.g. "Opportunity" → "Quote" for Madio, "Order" for a retail brand), active modules list, division/category list (replacing the hardcoded `lifecycle.DIVISIONS`).
- **Pipelines** — reuse `tenancy.WORKFLOW_ENTITIES`/`make_stage` unchanged; extend `WORKFLOW_ENTITIES` to cover canonical `opportunity` instead of only `quote`/`lead`/etc., so a new tenant defines its own stage list at signup, not in code.
- **Custom fields** — reuse `CustomFieldDefBase` (`models.py:1808`) unchanged; extend `CUSTOM_FIELD_ENTITIES` to the canonical set (`account`, `contact`, `lead`, `opportunity`, `product`).
- **Module extensions** — brand-specific data (D&W survey fields, paint batch/shade fields, furniture fabric specs) live in a per-module collection keyed by the canonical record's id, not as ever-growing optional columns on the core model. `DWOpening`/`DWSurvey` become the reference implementation of "module extends Opportunity."

## Integration Requirements

- **AI agents (`agent_bridge.py`, `agent_tasks.py`)** — `AgentConversation`/`AgentTask` already use `subject_type`/`subject_id` polymorphism. v1 requirement: canonical entities (Account, Contact, Opportunity, Activity) are valid `subject_type` values with no bridge code change — this module is already generalized correctly; it just needs the new type strings registered.
- **Tally (`tally.py`)** — voucher generation depends on ledger names/GST rules that are Madio's chart of accounts. v1 requirement: the voucher-builder functions stay pure/tenant-agnostic (already true — no DB, no FastAPI per the module's own docstring); the *mapping* from canonical Quotation/Payment → ledger name becomes tenant-configurable data, not a code constant, so a sister brand with a different Tally company can reuse the same envelope builder.
- **CSV engine (`csv_engine.py`)** — import/export column mapping must key off canonical field names with a per-tenant alias table, so each brand's spreadsheet vocabulary (already handled once for Madio's messy date/number formats in `lifecycle.py`) doesn't require a new parser per brand.
- **Notifications (`notifications.py`)** — no schema change expected; consumes canonical Activity/Opportunity stage-change events the same way it consumes today's Lead/Quote events.

## Non-Functional Requirements

- **Performance** — canonical-model queries must not regress existing indexed lookups (tenant_id + entity-type compound indexes carry over unchanged).
- **Security** — tenant fail-closed guarantee in `tenancy.py` is non-negotiable and must cover every new/renamed collection from day one of the migration, not backfilled after.
- **Auditability** — `AuditLog` (`models.py:1871`) already exists; canonical Activity model should not duplicate it — Activity is the user-facing timeline, AuditLog is the compliance trail of field-level changes. Keep them distinct.
- **Extensibility** — a new brand module must be addable by (a) a new Pydantic model, (b) a `TENANT_COLLECTIONS` entry, (c) optional workflow/custom-field registration — no core canonical model or server route changes required for a module-only addition.

## Phased Rollout Plan

- **Phase 0 — Core model:** Introduce Account and canonical Activity as new collections; add compatibility field aliases so `Quote`→Opportunity, `Customer`/`Architect`→Contact read/write through canonical names without breaking existing Madio UI. No data migration yet — additive only.
- **Phase 1 — Modules:** Carve D&W (`DWOpening`, `DWSurvey`) and petty cash/cashbook into explicit "modules" behind the module-registration pattern from Multi-Brand Requirements above, proving the pattern on Madio's own real data before a second brand uses it.
- **Phase 2 — Migration:** Backfill Account records from existing Customer/Architect/Vendor data; migrate `Lead.log`/`Quote.log` ad hoc arrays into canonical Activity records; deprecate (not delete) legacy flat fields once frontend reads exclusively from canonical shape.
- **Phase 3 — Commercialization:** Tenant self-provisioning flow (pipeline/custom-field/module selection at signup), billing hooks, external-customer-facing surfaces. Explicitly deferred past v1.

### In scope for v1
Canonical Account/Contact/Lead/Opportunity/Product/Quotation/Activity models; brand config extensions to `TenantBusinessProfile`; module pattern proven on D&W; agent bridge subject-type registration; Tally/CSV mapping made tenant-configurable.

### Deferred (not v1)
Self-serve tenant provisioning UI; external customer portal; billing/metering; deleting or hard-migrating legacy field names (Phase 2 is additive/backfill, not a breaking cutover); any new sister-brand's actual onboarding (v1 proves the *pattern* on Madio, doesn't onboard brand #2).

## Open Questions

- Should `Visitor` be merged into canonical `Lead` in v1, or stay a distinct walk-in subtype permanently? (Leaning: stay distinct — different capture flow, same pipeline.)
- Does `Sale` remain a separate terminal-state entity, or collapse into Opportunity.stage = "Won" once canonical Activity/Opportunity ship?
- Who owns the tenant-configurable Tally ledger-mapping UI — finance team tooling, or admin settings? Not yet assigned.
- Minimum viable "module registration" mechanism — a Python registry dict, or does it need to be data-driven (Mongo-stored) to support Phase 3 self-provisioning later? Affects Phase 1 design, TBD before `/plan`.

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
