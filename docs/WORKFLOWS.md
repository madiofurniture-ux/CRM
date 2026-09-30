# Configurable workflows (Salesforce-style)

Every record type moves through stages that each tenant configures under
**Admin → Workflows** (`/admin/workflows`, admin only). This is the CRM's
equivalent of Salesforce's Path, validation rules and record-triggered flows.

## Record types

| Record type | Collection | Stage field | Stage list |
|---|---|---|---|
| Visitors | `visitors` | `stage` | Tenant-defined |
| Leads | `leads` | `stage` | Tenant-defined |
| Quotations | `quotes` | `stage` | Tenant-defined |
| Sales Orders | `sales` | `stage` | Tenant-defined |
| Customers | `customers` | `stage` | Tenant-defined |
| Products | `inventory` | `stage` | Tenant-defined |
| Projects | `projects` | `stage` | **System** (Survey → … → Completed) |
| Vendor Orders | `manufacturer_orders` | `status` | **System** (Quoted → … → Delivered) |
| Purchase Orders | `purchase_orders` | `status` | **System** (Draft / Issued / Received / Cancelled) |
| Invoices | `invoices` | `status` | **System** (Draft / Sent / Paid / Cancelled) |
| Tasks | `tasks` | `status` | **System** (Pending / In Progress / Completed / Rolled Over) |

"System" stage lists are fixed (`tenancy.LOCKED_STAGES`): project P&L,
committed spend, notifications and model validators depend on the exact
strings. A tenant can configure everything *about* each of those stages, but
cannot add, remove, rename or reorder them.

## What a stage carries

- **Probability %**: drives the weighted value on the Pipeline board. A deal's
  own `probability` still overrides it.
- **Closes the record / Counts as won**: terminal and won flags, used by reports
  and by the Path's final "Closed" chevron.
- **Guidance for success**: shown on the record's Path.
- **Required before entering**: fields that must be filled before a record can
  move into the stage. Also shown as the stage's key fields on the Path.
- **Can move next to**: allowed next stages. Leave empty to allow any stage.

Required fields and allowed next stages only bind when **Enforce** is on (the
same opt-in switch as before). A blocked move returns `400` with
`{message, code: "required_fields" | "transition_not_allowed", missing_fields | allowed}`,
and the UI shows the message as a toast. Saving a record without changing its
stage never trips a gate.

## Stage history

Every stage change appends `{from, to, at, by, by_id}` to the record's own
`stage_history` (last 100 entries) and sets `stage_entered_at`. Both are
server-owned: a client can't write them. Because history lives on the record,
it has the same visibility rules as the record itself.

## Automations

A rule fires **when a record is created** or **when it enters a stage** (not
when it's re-saved at the same stage). Each rule has up to 5 actions:

- **Create a task**: the title can use `{record}`, `{stage}` or any text/number
  field such as `{customer}`. It's assigned to the record owner, the user who
  moved the record, or a named person, and is due N days out. Tasks are tagged
  `category: "Workflow"` and linked back through `ref` / `ref_type`.
- **Update a field**: text or yes/no fields only. Document numbers, totals and
  owner fields (which control who can see a record) can't be set by a rule.
- **Message the customer**: uses the existing `notifications.EVENTS`
  templates, sent to the record's phone number and logged in
  `notification_logs` (the transport is still a stub, see `notifications.py`).

Automations are best-effort. The business write has already happened, so a
failing action is logged as a warning and never turns the save into an error.
Each run is recorded in `activities` (`action: "automation"`).

## Where it's used in the UI

- `components/StagePath.jsx`: the Lightning-style Path (chevrons, "Mark as
  current stage", "Mark stage as complete", key fields, guidance, time in
  stage). Shown in the Lead and Project detail drawers.
- `hooks/useWorkflow.js`: loads a tenant's workflow. Leads, Pipeline,
  Quotations, Visitors and Projects take their stage lists and probabilities
  from it instead of hardcoded arrays.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/workflows` | Every record type: stages, rules, `locked`, `stage_field`, `fields` (catalog for pickers) |
| GET | `/api/workflows/{entity}` | One record type |
| PUT | `/api/workflows/{entity}` | Admin. `{stages, rules?, enforce, force?}`. Omitting `rules` keeps the existing rules. `409` if records would be stranded on a removed stage |
| POST | `/api/workflows/{entity}/adopt` | Admin. Builds the stage list from stages already used in the data (not for system stage lists) |
| POST | `/api/workflows/{entity}/reset` | Admin. Back to the defaults, removing rules |

Code: `backend/tenancy.py` (schema, defaults, locked lists),
`backend/workflow_rules.py` (field catalog, gates, rule validation),
`backend/server.py` (`validate_stage`, `run_stage_automation`, routes).
Tests: `backend/tests/test_workflow_engine.py`.
