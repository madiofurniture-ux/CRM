# Recommended Mongo Indexes — Canonical CRM v1

Every canonical collection is queried by `tenant_id` (`brand_id`) on
virtually every request (`tenancy.scope()` adds it to every query) — it
must be the first key in every compound index below, or a query on a large
tenant will still scan every other tenant's documents first.

None of this is applied automatically. Run these once against the target
Mongo deployment (`mongosh` or a small script using the same `pymongo`/
`motor` client server.py already uses) before real traffic hits `/api/v1`.

```js
// crm_leads
db.crm_leads.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_leads.createIndex({ tenant_id: 1, lead_status: 1, created_at: -1 });
db.crm_leads.createIndex({ tenant_id: 1, owner_id: 1 });
db.crm_leads.createIndex({ tenant_id: 1, name: "text", company: "text" }); // search_leads' q filter

// crm_opportunities
db.crm_opportunities.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_opportunities.createIndex({ tenant_id: 1, stage_id: 1, created_at: -1 });
db.crm_opportunities.createIndex({ tenant_id: 1, account_id: 1 });
db.crm_opportunities.createIndex({ tenant_id: 1, lead_id: 1 });
db.crm_opportunities.createIndex({ tenant_id: 1, owner_id: 1, is_won: 1 }); // "my open deals" / pipeline reports

// crm_accounts (v1.1, once the API ships)
db.crm_accounts.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_accounts.createIndex({ tenant_id: 1, name: 1 });

// crm_contacts (v1.1)
db.crm_contacts.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_contacts.createIndex({ tenant_id: 1, account_id: 1 });
db.crm_contacts.createIndex({ tenant_id: 1, email: 1 });

// crm_products (v1.1)
db.crm_products.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_products.createIndex({ tenant_id: 1, sku: 1 });

// crm_quotations (v1.1)
db.crm_quotations.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_quotations.createIndex({ tenant_id: 1, opportunity_id: 1 });

// crm_activities (v1.1)
db.crm_activities.createIndex({ tenant_id: 1, id: 1 }, { unique: true });
db.crm_activities.createIndex({ tenant_id: 1, related_type: 1, related_id: 1, created_at: -1 });
db.crm_activities.createIndex({ tenant_id: 1, owner_id: 1, due_date: 1 }); // "my open tasks"
```

## Notes

- The `{ tenant_id, id }` unique index is the important one for correctness:
  `id` alone is a UUID (already effectively unique globally), but scoping
  the uniqueness constraint by tenant matches how every lookup in
  `api_canonical.py` already queries (`tenancy.scope({"id": ...}, ...)`),
  so the index actually gets used.
- `$regex` search on `name` (used by `search_leads`/`search_opportunities`'s
  `q` param) does not use a text index unless the query switches to `$text`
  — the indexes above are listed for when that search gets real usage; a
  regex prefix search (`^term`) can use the existing `{tenant_id, ...}`
  index without a text index at all, and needs no infra beyond what's here.
- Apply the equivalent indexes to `leads`/`quotes`/`sales`/etc. only if
  they're missing — that's outside this doc's scope (canonical-only), and
  those collections already have `tenant_id` in `tenancy.TENANT_COLLECTIONS`
  from before this feature.
