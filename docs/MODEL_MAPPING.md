# Model Mapping: `backend/models.py` → `backend/models_canonical.py`

Both layers run in parallel in v1 — nothing below is a migration that has happened; it is the map a future migration would follow.

| Existing (`models.py`) | Canonical (`models_canonical.py`) | Notes |
|---|---|---|
| `Customer` | `Account` | `Customer.division` → `Account.brand_id`. No `type` field existed; canonical adds `prospect/customer/partner/vendor`, default `"prospect"`. |
| `Architect` | `Contact` | An Architect is a referral contact, closest existing analog to a standalone person record. `Architect.firm` has no canonical field yet (candidate for `custom_data`). |
| `Lead` | `Lead` | Closest 1:1 mapping. `Lead.stage` ("New/Contacted/Qualified/Quoted/Won/Lost") → `Lead.lead_status` (canonical set: New/Contacted/Qualified/Converted/Lost — "Quoted" and "Won" collapse into the Opportunity/Quotation lifecycle instead of staying lead-level statuses). `Lead.value` → `estimated_value`. `Lead.architect_id`/`visitor_id` have no canonical equivalent yet (candidates for `custom_data`). |
| `Quote` | `Opportunity` + `Quotation` (split) | `models.py` conflates deal-tracking and the priced document into one `QuoteBase`. Canonical splits them: `Opportunity` carries `stage_id`/`probability`/`amount`/`close_date`; `Quotation` carries `line_items`/`subtotal`/`tax_total`/`grand_total`/`status`, and points back at its `opportunity_id`. `Quote.division` → both entities' `brand_id`. |
| `Sale` | *(not yet canonical)* | A won Opportunity + accepted Quotation together cover what `Sale` represents (order confirmed, payment tracked). v1 does not add a canonical "Order" entity — `Sale` keeps running as-is; revisit if/when Quotation status transitions need their own order-fulfillment fields. |
| `InventoryItem` | `Product` | `InventoryItem`'s stock-ledger fields (floor, stock_movements) have no canonical equivalent — `Product` is deliberately just the sellable-item shape (name/sku/category/price), not inventory tracking. |
| `Task` + `Meet` | `Activity` | Canonical unifies both into one `Activity` with a `type` field (`call`/`email`/`meeting`/`note`/`task`). `Task`/`Meet` keep running unchanged in v1; no data migration performed. |

## Fields every canonical entity adds that `models.py` records don't uniformly have

- `brand_id` (required) — see `docs/CRM_CANONICAL_PRD.md` §2 for why this is separate from `tenant_id`.
- `custom_data` (dict, default `{}`) — where a brand module's manifest-declared custom fields (e.g. Doors & Windows' `survey_id`) actually live on the record, instead of being ad-hoc top-level fields like `models.py`'s `custom_fields: dict` pattern already does for Lead/Customer/Project.
- `updated_at` — `models.py` records mostly only have `created_at`; canonical records track both.
