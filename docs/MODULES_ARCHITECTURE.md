# Modules Architecture

## How it works

A **module** is a directory `backend/modules/<name>/` containing one `manifest.json`. `core_crm` is the base module every brand depends on; a **brand module** (`madio_doors_windows`, `map_paints`, `navaki`) is what a `brand_id` value actually resolves to.

```json
{
  "name": "madio_doors_windows",
  "version": "1.0.0",
  "depends": ["core_crm"],
  "custom_fields": { "opportunity": [ { "key": "survey_id", "label": "Survey ID", "type": "text" } ] },
  "pipelines": { "opportunity": [ { "key": "new", "label": "New", "terminal": false, "won": false } ] },
  "quotations": { "templates": ["doors_windows"] },
  "permissions": {}
}
```

`backend/modules_loader.py` reads and merges these at request time:

- `load_for_brand(brand_id)` — merges `core_crm` + the brand's own manifest. `custom_fields` are additive per entity (brand fields append to core's, deduped by `key`); `pipelines`/`quotations`/`permissions` are a shallow merge where the brand's own key wins if it defines one, otherwise `core_crm`'s default is used.
- `pipeline_for(brand_id, entity)`, `stage_keys(...)`, `won_stage(...)`, `lost_stage(...)` — helpers `api_canonical.py` uses to validate a `move_stage`/`set_won`/`set_lost` call against that brand's actual pipeline instead of a hardcoded list.
- `list_brands()` — every manifest directory except `core_crm` itself (which is a dependency, not a selectable brand).

No caching layer beyond an in-process `lru_cache` on the raw file read — manifests are tiny JSON files, re-reading them is not a bottleneck at this scale. If a manifest is edited, restart the backend process to pick it up (the `lru_cache` is per-process, not per-request).

## Comparison to Odoo / Salesforce

- **Odoo**: modules are Python packages with `__manifest__.py` declaring `depends`, and they can add models/views/code, not just config. This system is deliberately a config-only subset of that idea — a brand module here cannot add new Python behavior, only data-shaped extensions (fields, pipeline stages, template names). That is the trade-off for "no deploy per brand."
- **Salesforce**: comparable to a combination of Record Types (per-object picklist/field variation) and a Sales Process (per-record-type stage list) — both are admin-configured, no code. This system's manifest is the same idea expressed as a file instead of clicks in a setup UI, because there is no setup UI yet.

## Operator Guide — Adding a New Brand

1. Pick a `brand_id` (lowercase, underscore-separated — e.g. `navaki_interiors`).
2. Create `backend/modules/<brand_id>/manifest.json`. Minimum viable manifest:
   ```json
   { "name": "<brand_id>", "version": "1.0.0", "depends": ["core_crm"],
     "custom_fields": {}, "pipelines": {}, "quotations": {"templates": ["standard"]}, "permissions": {} }
   ```
   This alone makes the brand usable — it inherits `core_crm`'s default Lead/Opportunity pipeline and no custom fields.
3. Restart the backend (`modules_loader`'s manifest cache is per-process).
4. Confirm it's live: `GET /api/v1/brands` should list the new `brand_id`; `GET /api/v1/brands/<brand_id>/config` should return the merged config.
5. Start creating Leads/Opportunities with `brand_id=<brand_id>` — no other setup required. All records are automatically scoped to the signed-in user's `tenant_id` (unchanged tenancy behavior) plus this `brand_id`.

## Operator Guide — Changing Pipeline Stages or Custom Fields Without Code Changes

Edit the brand's `manifest.json` directly:

- **Add/reorder pipeline stages**: edit the `pipelines.opportunity` (or `.lead`) array. Exactly one stage should have `"won": true`; exactly one (typically the last) should have `"terminal": true, "won": false` for `lost`. `opportunities/{id}/set_won` and `/set_lost` read these flags to decide which stage to move a record to.
- **Add a custom field**: append an object to `custom_fields.<entity>` — `{"key": ..., "label": ..., "type": ...}`. The field itself isn't enforced by Pydantic (v1's `custom_data` is an open dict); this manifest entry is metadata for the frontend to render a field, not a schema constraint. Restart the backend to pick up the change.
- **No brand's manifest edit ever requires touching `models_canonical.py`, `api_canonical.py`, or `tenancy.py`.** If a change seems to need one of those, it's no longer a config change — treat it as a new feature request, not a brand onboarding step.
