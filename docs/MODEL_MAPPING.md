# Model Mapping — legacy `models.py` → canonical `models_canonical.py`

`brand_id` in the PRD/spec is `tenant_id` everywhere in code — this repo's
existing multi-tenancy field (`tenancy.py`). The canonical layer reuses it
rather than adding a second tenancy key.

| Legacy (`models.py`) | Collection | Canonical (`models_canonical.py`) | Collection | Notes |
|---|---|---|---|---|
| `Lead` | `leads` | `Lead` | `crm_leads` | Legacy `Lead.stage` (New/Contacted/Qualified/Quoted/Won/Lost, tenant-configurable via `tenancy.DEFAULT_WORKFLOWS`) → canonical `lead_status` (`LEAD_STATUSES`, brand-configurable via `modules/<brand>/manifest.json`). Legacy carries rich CRM-ops fields (remarks_history, confidence_level, follow_up_date, assigned_to); canonical Lead is deliberately thinner — a pre-qualification record that converts into an Opportunity. |
| `Architect` | `architects` | `Contact` | `crm_contacts` | Architect was a narrow "referral contact" concept; canonical Contact generalizes it (any person, optionally tied to an Account). |
| *(none — no company/organization entity)* | — | `Account` | `crm_accounts` | New concept. Legacy `Quote`/`Sale`/`Project` store `customer` as a free-text name; canonical introduces a real Account record so history rolls up. |
| `Quote` | `quotes` | `Quotation` | `crm_quotations` | Legacy `Quote` is MADIO-specific (division, GST, quote_lines collection, PDF via `quotation_templates.py`). Canonical `Quotation` is a thinner cross-brand shape (`lines` embedded, `template_id` still points at `quotation_templates.py`). Not a replacement — PDF generation and tax logic stay on the legacy path for v1. |
| `Sale` | `sales` | *(none yet — Opportunity.is_won covers "deal closed")* | — | A canonical Sale/Order model is out of scope for v1; `Opportunity.is_won=True` is the v1 signal that a deal closed. |
| `InventoryItem` | `inventory` | `Product` | `crm_products` | Legacy inventory tracks stock/floor/warehouse (a physical-goods concern); canonical Product is a sellable catalog item (name/sku/price), matching Salesforce/Odoo's `product.product`. The two can coexist — a Product may reference an InventoryItem via `custom_data` if a brand needs that link. |
| *(none — no unified deal-stage entity)* | — | `Opportunity` | `crm_opportunities` | New concept, closest to what `Lead.stage in {Quoted, Won}` and `Quote`/`Sale` together represent today, unified into one entity with `stage_id`, `probability`, `close_date` — the Salesforce/Dynamics/Odoo `crm.opportunity` shape. |
| `Task`, `Meet`, `RecordContact` (as a log) | `tasks`, `meets`, `record_contacts` | `Activity` | `crm_activities` | Canonical Activity unifies call/email/meeting/task/note against any related entity (`related_type`/`related_id`), matching Salesforce's Activity/Task/Event model. Legacy Task/Meet keep their specialized fields (assignee, due date, calendar) for now. |

## What did *not* get a canonical counterpart in v1

- `Vendor`, `Floor`, `PurchaseOrder`, `ManufacturerOrder`, `Invoice`,
  `PettyCash`, `Cashbook*`, `Site`, `Team`, `Role` — these are
  operations/finance concerns specific to MADIO's furniture/D&W business,
  not part of the canonical sales-CRM object model. They stay exactly as
  they are; nothing here changes them.
- `Project` — MADIO's post-sale execution tracker. A canonical Project/
  fulfillment object is a plausible v1.1/v2 addition once Opportunity→Sale
  conversion exists, but is out of scope now.

## Migration path (not done in v1)

v1 ships the canonical collections empty, running in parallel. A future
migration script would, per tenant:

1. Read `leads` → write `crm_leads`, mapping `stage` → `lead_status` via
   the tenant's configured stage labels (see `tenancy.resolve_stage`).
2. Read `quotes` linked to a won `Lead` → write one `crm_opportunities`
   record with `is_won=True`.
3. Leave the legacy collections in place (read-only for the migrated
   tenant) rather than deleting — reversible, auditable.

This is deliberately not automated in v1: the mapping above needs a real
tenant's data to validate the `stage` → `lead_status` translation before it
runs against anything live.
