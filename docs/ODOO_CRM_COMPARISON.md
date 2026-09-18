# Madio Canonical CRM vs Odoo CRM

Internal strategy comparison, not marketing copy. Scope: Madio's `/api/v1`
canonical layer (`backend/models_canonical.py`, `backend/api_canonical.py`,
`backend/modules_loader.py`) against Odoo's `crm` + `sale` modules as of
Odoo 17 community. Written for the "low-cost, multi-tenant CRM for SMBs"
brief, not a general CRM bake-off.

## 1. Data model comparison

| Concept | Madio (`models_canonical.py`) | Odoo | Notes |
|---|---|---|---|
| Company/org | `Account` — name, type, phone, email, address, owner_id | `res.partner` (`is_company=True`) | Odoo's `res.partner` is one polymorphic model for companies, individuals, and addresses (with `parent_id` hierarchy, multiple addresses, bank accounts). Madio splits Account/Contact cleanly — simpler, less flexible (no multi-address, no company hierarchy). |
| Person | `Contact` — account_id, name, phone, email, title, is_primary | `res.partner` (`is_company=False`, `parent_id` -> company) | Same model in Odoo, not a separate one. Madio's explicit `is_primary` flag on Contact has no direct Odoo equivalent (Odoo uses partner roles/tags instead). |
| Unqualified lead | `Lead` — name, phone, email, source, matched_account_id, lead_status, owner_id, estimated_value, converted_opportunity_id | `crm.lead` (`type='lead'`) | Odoo's `crm.lead` is a single model that IS both the lead and the opportunity (a `type` field and `stage_id` distinguish them). Madio uses two separate models/collections. Odoo has built-in duplicate detection (email-based) and a dedicated lead-to-opportunity conversion wizard with merge; Madio's `/leads/{id}/convert` is a straight-line create, no merge/dedup UI. |
| Sales deal | `Opportunity` — account_id, contact_id, lead_id, stage_id (string label), probability, amount, close_date, owner_id, status (open/won/lost) | `crm.lead` (`type='opportunity'`) | Odoo computes `probability` automatically per stage (and, in Enterprise, via predictive lead scoring); Madio's `probability` is a plain float the caller sets. Odoo's `stage_id` is a foreign key to a `crm.stage` record (ordered, team-scoped); Madio's `stage_id` is a string matched against the brand's manifest pipeline — no dedicated stage collection, so stage metadata (color, rotting-deal thresholds) doesn't exist yet. |
| Product | `Product` — name, sku, category, unit_price, uom, active | `product.product` / `product.template` | Odoo's product model is far deeper: variants (template + variant split), multiple price lists, UoM conversion tables, accounting categories, vendor pricelists, stock integration. Madio's `Product` is a flat catalog row — enough for a fixed-catalog SMB, not for variant-heavy retail. |
| Quote/order | `Quotation` — opportunity_id, account_id, quote_no, status, line_items (raw list of dicts), subtotal/tax_total/grand_total, valid_until | `sale.order` + `sale.order.line` | Odoo's `sale.order.line` is a real relational model (discounts, taxes as m2m to `account.tax`, analytic accounts, delivery/invoicing status per line). Madio's `line_items` is an untyped `List[dict]` — fast to ship, no schema/validation on line items, and reporting on line-item data means parsing JSON blobs rather than querying rows. |
| Activity/task | `Activity` — related_entity, related_id, type, subject, notes, due_date, completed, owner_id | `mail.activity` (+ `mail.message` for the chatter log) | Odoo's activity system is tied into `mail.thread` — every record gets a chatter (log, notes, email thread, followers) for free by inheriting a mixin. Madio's `Activity` is a plain polymorphic join table; no chatter/thread, no follower/subscription model, no inbound-email-to-record parsing. |
| Multi-tenancy | `tenant_id` (hard, SaaS-level) + `brand_id` (soft, intra-tenant) on every canonical record | Odoo multi-company (`res.company`) + optional Odoo.sh/SaaS tenancy at the infra level | Odoo's multi-company is a first-class ORM feature (record rules, company-dependent fields) but heavier to reason about; most self-hosted Odoo deployments are single-tenant per database. Madio's `tenant_id`/`brand_id` split is purpose-built for "one deployment, many small businesses," which Odoo doesn't optimize for out of the box. |
| Custom fields | `custom_data: dict` (freeform) on every entity + manifest-declared `custom_fields` per entity | Studio (Enterprise, no-code builder) or a custom module with real ORM fields + migrations | Odoo's custom fields (via a module) are real typed, indexed, migratable columns. Madio's `custom_data` is an unindexed JSON blob — trivial to add a field, but no type safety, no DB-level constraints, and querying/filtering by a custom field means a Mongo query into a nested dict rather than an indexed column. |

**Net read:** Madio's models cover the CRM core (Account/Contact/Lead/Opportunity/Product/Quotation/Activity) at roughly Odoo's *shape*, but at a fraction of the depth in every entity — no stage metadata, no line-item schema, no chatter/thread, no product variants. That's the correct trade for v1 low-cost SMB use; it is not close to Odoo CRM+Sales feature-for-feature.

## 2. Architecture comparison

| Axis | Madio | Odoo |
|---|---|---|
| Backend | FastAPI (Python), thin request handlers, Pydantic models for validation | Python ORM (`models.Model` classes) with declarative fields, auto-generated CRUD, business logic in model methods/`@api.depends` |
| Database | MongoDB, one DB, `tenant_id`/`brand_id` as scoping fields | PostgreSQL, relational, one DB per tenant/company in typical deployments |
| Schema enforcement | Pydantic at the API boundary only; Mongo itself is schemaless (a bad write can still land) | PostgreSQL column types + Odoo ORM constraints (`@api.constrains`, SQL constraints) enforced at the DB layer |
| Views/UI | Separate React frontend (`frontend/`), fully decoupled from the API | XML view definitions (`views/*.xml`) inside each module generate the UI directly — backend and UI are far more coupled, but a new field can appear in a form with zero frontend code |
| Extensibility mechanism | `modules/*/manifest.json` — data-only, loaded at runtime by `modules_loader.py` | `__manifest__.py` + Python `models/`, XML `views/`, `security/*.csv` — code-level modules, loaded at server boot, can override/inherit any existing model or view |
| Migrations | None yet — Mongo's schemaless nature means new fields just start appearing; no formal migration story for canonical models | Odoo has a mature migration framework (`openupgrade`, versioned upgrade scripts) because Postgres schema changes need one |
| Deployment footprint | One Python process + MongoDB + a static frontend build — deployable on a single small VM or free-tier services | Full Odoo stack (Python + PostgreSQL + often a separate worker/cron process), meaningfully heavier to self-host; Odoo.sh/Odoo Online abstract this away for a subscription fee |
| Multi-tenancy cost | Single shared DB, `tenant_id` filter on every query — near-zero marginal cost per tenant | Typically one Postgres DB per company/tenant in serious deployments — marginal cost per tenant is a full database |

**Net read:** Madio's architecture is deliberately minimal — one language, one DB engine, no XML view compiler, no migration framework — which is exactly what keeps it cheap to run and easy for one operator to reason about. Odoo's architecture is a mature, batteries-included framework built to be *extended by third parties*, which is also why it's heavier to run and slower to onboard a new brand into (a manifest.json edit vs. writing an Odoo module).

## 3. Feature comparison

**Pipeline management**
- Madio: per-brand pipeline stages declared in `manifest.json` (`pipelines.opportunity` — ordered `{key,label,terminal,won}` stages), loaded via `modules_loader.py`. No kanban drag-and-drop persistence logic beyond `stage_id` on the record; no per-stage rotting-deal alerts.
- Odoo: `crm.stage` records (team-scoped, ordered, with `is_won`), a native kanban board, automatic probability-per-stage, "lost reason" tracking, and (Enterprise) AI-suggested next actions.
- **Gap:** stage automation (auto-move, rotting alerts, forecasting by stage) — Madio has none of this yet.

**Teams**
- Madio: no team/territory concept at all in the canonical layer. `owner_id` is a single user per record; no team-level pipeline view, no round-robin lead assignment.
- Odoo: `crm.team` with team-level pipelines, targets, and assignment rules (including load-balanced auto-assignment in Enterprise).
- **Gap:** real gap — a multi-rep SMB outgrows "one owner_id" quickly once they want team pipelines or lead-routing rules.

**Activities**
- Madio: flat `Activity` model (call/email/meeting/note/task) attached to any entity. No reminders, no calendar sync, no chatter/thread, no @mentions.
- Odoo: `mail.activity` + full chatter (`mail.thread` mixin) on every business record — logged emails, internal notes, followers, activity reminders/overdue flags, calendar integration.
- **Gap:** Madio's activity log is closer to a to-do list; Odoo's is closer to a shared inbox/audit trail per record.

**Reporting**
- Madio: none in the canonical layer yet — no built-in pipeline/forecast dashboards for `/api/v1` data (the legacy `backend/server.py` app has its own separate Reports/Executive Analytics pages, unrelated to the canonical models).
- Odoo: built-in pivot/graph views on every model, a dedicated CRM reporting dashboard (win/loss, forecast, team performance), all queryable via the ORM's `read_group`.
- **Gap:** significant — any canonical-CRM reporting today would need to be built from scratch against MongoDB aggregation pipelines.

**Integrations**
- Madio: none built into the canonical layer (no email-to-lead capture, no calendar sync, no marketing automation hooks). The wider MADIO app has WhatsApp-style discussions and Tally accounting sync, but those are separate from `/api/v1`.
- Odoo: email gateway (incoming mail creates/updates leads), calendar (Google/Outlook), marketing automation, accounting (native, since `sale.order` -> `account.move` is in the same suite), VoIP connectors, and a large third-party app marketplace.
- **Gap:** Odoo's biggest practical advantage for a business already living in email is automatic lead capture from an inbox; Madio has no equivalent today.

**What Madio does that Odoo doesn't (for this use case)**
- A `brand_id` concept purpose-built for "one company, several distinct retail/product lines, one shared backend" — Odoo would model this as either multiple companies (heavier) or a plain category field (no manifest-driven custom fields/pipelines per brand).
- Manifest-driven custom fields/pipelines with **zero code deploys** per brand (`modules_loader.list_brands()` just globs a directory) — adding an Odoo custom field, even a simple one, means writing and deploying a Python module.
- A much smaller total system to operate, patch, and reason about — relevant when the "IT department" is one person.

## 4. Extensibility comparison

| | Madio | Odoo |
|---|---|---|
| Unit of extension | A `manifest.json` (data, not code) | A Python module: `__manifest__.py` + `models/*.py` + `views/*.xml` + `security/*.csv` |
| Adding a custom field | Add an entry to `custom_fields` in a brand's manifest; consumers merge it via `modules_loader.load_for_brand()`. No migration, no restart required. Not a real typed column — see model comparison. | Add a field to a model in a custom module, write a view to expose it, run `-u` to upgrade the module (applies the schema migration). Real typed column, but requires a deploy. |
| Adding a whole new entity | Not really supported by the manifest system — it only extends `custom_fields`/`pipelines`/`quotations`/`permissions` on the *existing* canonical entities; a genuinely new entity means writing a new Pydantic model + router either way. | Fully supported — a module can define brand-new models with their own tables, views, and menus. |
| Overriding existing behavior | Not supported — there's no hook system for a brand to override how, say, lead conversion works; every brand runs the same `api_canonical.py` code. | Core Odoo feature — modules can inherit (`_inherit`) and override any existing model's fields or methods, or extend/override any view via XML inheritance. |
| Permissions | `permissions: {}` in the manifest — present in the schema but not yet enforced anywhere in `api_canonical.py` (role gating there is the same `get_current_user`/`tenancy` pattern as the rest of the app, not manifest-driven). | Full row-level security (`ir.rule`) and field-level access (`ir.model.access.csv`) per group, enforced by the ORM on every query. |
| Onboarding a new brand/tenant | Drop a new directory with `manifest.json` under `backend/modules/` — no code change, no deploy (confirmed in this repo: `list_brands()` autodiscovers it). | Create a new company (or a new database, for full isolation) and configure/install modules against it — heavier, but gets full data isolation and its own security groups for free. |

**Net read:** Madio's extension model is optimized for the *one specific case* it needs to solve well — a new brand with its own fields and pipeline, shipped by editing a JSON file — and is dramatically lower-friction than Odoo for exactly that case. It is not a general extensibility framework: it can't add new entities, override behavior, or enforce field-level permissions without a code change, all of which Odoo's module system genuinely supports.

## 5. When to use Madio CRM vs Odoo CRM

**Use Madio CRM when:**
- The business is Madio's own brands (or a similar SMB) that needs Leads/Opportunities/Quotations covered adequately, not comprehensively.
- Cost matters more than depth: one small VM, one MongoDB instance, one Python process — no PostgreSQL tuning, no Odoo worker/cron sizing, no per-tenant database.
- The operator is a single person (or small team) who needs to onboard a new brand/tenant by editing a JSON file, not by writing and deploying a module.
- The business doesn't yet need team-based pipelines, email-to-lead capture, built-in reporting dashboards, or product variants — and can tolerate building those later, in-house, as the product matures.
- Reselling this CRM to other SMBs at a low price point is a goal — Odoo's per-tenant cost (a full company/database) and licensing model (Enterprise features gated) work against a low-cost multi-tenant resale motion.

**Use Odoo CRM when:**
- The business already needs (or will soon need) team pipelines, lead scoring, marketing automation, or tight integration with accounting/inventory/HR — Odoo's suite covers all of that in one system, which Madio would have to build piece by piece.
- Reporting is a hard requirement from day one — Odoo's pivot/graph views and forecast reporting exist out of the box; Madio's canonical layer has none yet.
- The team can either self-host Postgres+Odoo competently or pay for Odoo Online/Odoo.sh, and per-tenant infrastructure cost is acceptable.
- Deep customization (new entities, overriding core behavior, field-level permissions) is expected — Odoo's module system is built for exactly that; Madio's manifest system explicitly is not.
- The complexity budget includes learning Odoo's ORM/XML-view conventions, which is a real ramp-up cost against FastAPI+Pydantic+React, a stack the team already knows in this repo.

**Bottom line:** Madio CRM is the right choice for a lean, low-cost, multi-brand internal tool with a clear, narrow v1 scope and a single operator. Odoo CRM is the right choice once the business needs suite-level depth (reporting, team pipelines, accounting integration, real extensibility) and is willing to pay the infrastructure/complexity cost that comes with it. They are not currently comparable in capability — only in the narrow slice of "can it record a lead and turn it into a quote."
