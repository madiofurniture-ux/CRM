# MongoDB Indexes — Canonical CRM Collections

None of these exist yet — v1 ships the model/API layer; creating the indexes is a deploy-time step (see `docs/GO_LIVE_V1_CHECKLIST.md`). Every index leads with `tenant_id` (the hard isolation boundary, unchanged from the rest of the app), then `brand_id`, matching how `api_canonical.py` actually queries.

```js
// crm_leads
db.crm_leads.createIndex({ tenant_id: 1, brand_id: 1, created_at: -1 })
db.crm_leads.createIndex({ tenant_id: 1, brand_id: 1, lead_status: 1 })
db.crm_leads.createIndex({ tenant_id: 1, id: 1 }, { unique: true })

// crm_opportunities
db.crm_opportunities.createIndex({ tenant_id: 1, brand_id: 1, created_at: -1 })
db.crm_opportunities.createIndex({ tenant_id: 1, brand_id: 1, stage_id: 1 })
db.crm_opportunities.createIndex({ tenant_id: 1, account_id: 1 })
db.crm_opportunities.createIndex({ tenant_id: 1, id: 1 }, { unique: true })

// crm_accounts
db.crm_accounts.createIndex({ tenant_id: 1, brand_id: 1, created_at: -1 })
db.crm_accounts.createIndex({ tenant_id: 1, id: 1 }, { unique: true })

// crm_contacts
db.crm_contacts.createIndex({ tenant_id: 1, brand_id: 1, account_id: 1 })
db.crm_contacts.createIndex({ tenant_id: 1, id: 1 }, { unique: true })

// crm_products, crm_quotations, crm_activities — same shape, not yet
// exercised by /api/v1 routes but worth creating up front since they're
// one-line additions once those routes ship:
db.crm_products.createIndex({ tenant_id: 1, brand_id: 1, sku: 1 })
db.crm_quotations.createIndex({ tenant_id: 1, opportunity_id: 1 })
db.crm_activities.createIndex({ tenant_id: 1, related_entity: 1, related_id: 1 })
```

## Why `tenant_id` leads every index, not `brand_id`

`tenant_id` has the smallest cardinality-per-query fan-out that must never leak across it (a security boundary), so it should always be the first key a Mongo query can use to prune — consistent with every other collection's existing indexing pattern in this codebase (not shown here since those already exist; see `tools/check_tenant_backfill.py` for how the rest of the app verifies `tenant_id` coverage).

## What to check after creating these

Run `db.crm_leads.find({tenant_id: "madio", brand_id: "madio_doors_windows"}).explain("executionStats")` (and the equivalent for `crm_opportunities`) and confirm `stage` shows an `IXSCAN`, not a `COLLSCAN`, before this goes to real data volume.
