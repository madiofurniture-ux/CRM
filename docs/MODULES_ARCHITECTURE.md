# Modules Architecture

## How it works

A **brand** (`brand_id`, stored as `tenant_id` — see
[MODEL_MAPPING.md](MODEL_MAPPING.md)) owns exactly one **module folder**
under `backend/modules/<brand_id>/`, containing a `manifest.json`. That
manifest is the entire definition of the brand's:

- **custom_fields** — extra fields per entity (Opportunity, Lead, Product,
  ...), each `{key, label, type}`.
- **pipelines** — ordered stage lists per entity (e.g. Opportunity's
  `qualification → site_survey → quotation → negotiation → won/lost`).
- **quotations** — which quotation templates (from `quotation_templates.py`)
  the brand can use.
- **permissions** — the default role for new users of that brand (kept
  minimal for v1; the existing `permissions.py` Role matrix still governs
  actual access).

`backend/modules_loader.py` resolves a `brand_id` to its **effective
config**: `core_crm`'s manifest (the shared baseline) with the brand's own
manifest layered on top — a brand's `custom_fields` add to core's (same
`key` overrides), and a brand's `pipelines`/`quotations`/`permissions`
override core's per-entity. An unknown or blank `brand_id` falls back to
`core_crm` alone rather than a 500 — fail open to sane defaults.

`backend/api_canonical.py` calls `modules_loader.pipeline_for(brand_id,
"opportunity", OPPORTUNITY_STAGES)` (etc.) instead of hardcoding stage
lists, so `move_stage`/`set_won`/`set_lost`/`convert_lead` all respect the
caller's brand automatically.

## Comparison

| | Odoo | Salesforce | This system |
|---|---|---|---|
| Unit of extension | a Python module with `__manifest__.py` | an org's Setup config (custom fields/page layouts/flows) | a `manifest.json` — data, not code |
| Adding a "brand"/org | install a new addon | provision a new Salesforce org | drop a new folder + manifest.json |
| Custom fields | Python model inheritance (`_inherit`) | Setup UI or Metadata API | JSON list per entity in the manifest |
| Pipeline/stage config | `crm.stage` records, editable in UI | `OpportunityStage` records | ordered string list in the manifest |
| Cost per new brand | new deploy (addon install) | new org (real infra cost) | zero — one shared backend, one shared DB |

The tradeoff: Odoo/Salesforce give an admin UI for all of this; v1 here is
file-based on purpose — it's the cheapest possible way to make brand
extension config-driven, and a manifest-editing UI is a natural v1.1 (read
the same files, write through `modules_loader`) once there's a second or
third external customer to justify it.

## Operator Guide

### Add a new brand

1. Pick a `brand_id` (lowercase, `snake_case` — it becomes both the
   tenant's `tenant_id` and the folder name, e.g. `navaki`).
2. Create `backend/modules/<brand_id>/manifest.json`. Copy
   `backend/modules/map_paints/manifest.json` as a starting template — it's
   the smallest of the two examples.
3. Fill in `custom_fields`/`pipelines`/`quotations` for the fields and
   stages this brand actually needs; leave anything unset to inherit from
   `core_crm`.
4. Create the tenant/users for that brand with `tenant_id` set to the same
   `brand_id` (existing user-management flow — unchanged by this feature).
5. No restart is strictly required to *add* the file (manifests are read
   lazily and cached), but `modules_loader`'s `lru_cache` means a running
   process won't pick up an *edit* to an existing manifest until it
   restarts — redeploy/restart after editing a live brand's manifest.

### Change pipeline stages or custom fields without code changes

Edit the brand's `manifest.json` directly (or `core_crm/manifest.json` to
change the shared baseline every brand inherits). Restart the backend
process so the cached config is dropped. No migration is needed — existing
records simply keep whatever `stage_id`/`lead_status` value they already
had; only new stage-list *validation* changes immediately.

### Verify a brand's effective config

```bash
cd backend
python -c "import modules_loader as ml; import json; print(json.dumps(ml.load_brand_config('madio_doors_windows'), indent=2))"
```
