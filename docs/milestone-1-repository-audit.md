# Milestone 1 — Repository Audit

## Scope

This milestone intentionally does **not** rewrite or replace the existing CRM. It documents the current single-file architecture and identifies safe extension points for the Doors & Windows ERP quotation-engine roadmap. Existing CRM functionality must remain the source of truth until later milestones migrate modules behind reusable services and masters.

## Current Architecture

The repository currently contains a browser-first CRM implemented in one standalone HTML document, `MADIO_CRM_v16.html`. The file includes the complete UI shell, styling, seed data, state, render functions, modal forms, print templates, offline browser persistence, and backend connector snippets in a single asset.

### Application Layers

| Layer | Current implementation | Notes for ERP extension |
|---|---|---|
| Shell/UI | Static HTML sections using `.page` containers and sidebar navigation | Keep route IDs stable; add ERP pages incrementally. |
| Styling | Embedded CSS variables and utility classes | Reuse panels, KPI cards, tables, modals, badges, and dark theme tokens. |
| Data seed | Embedded `_D` object for quotes, sales, visitors, Navaki leads, inventory, petty cash, architects, charts, teams, and references | Extract only when adding a data service/migration layer. |
| State | Global arrays/objects plus localStorage-backed modules | Preserve keys; introduce new keys for D&W masters. |
| Rendering | Direct DOM rendering functions by page | Add reusable table/form helpers before adding large master screens. |
| Persistence | localStorage plus Google Apps Script / Excel-style sync helpers | D&W masters should use the same sync abstraction until a server DB exists. |
| Output | Browser `print()`-based estimates, invoices, POs, catalogues, audit reports | Extend print templates first; defer binary PDF dependencies. |

## Pages

The CRM already exposes these page containers:

| Page ID | Functional area |
|---|---|
| `dash` | Dashboard and active quote summary |
| `alerts` | Follow-up alerts |
| `pipeline` | Quotation pipeline kanban |
| `quotes` | Quotation list |
| `sales` | Sales register |
| `visitors` | Walk-in visitor tracking |
| `navaki` | Navaki lead capture |
| `revenue` | Revenue analytics |
| `leaderboard` | Team leaderboard |
| `sources` | Lead-source analytics |
| `architects` | Architect CRM |
| `meetplan` | Meeting planner |
| `inventory` | Stock inventory |
| `inv-analytics` | Inventory analytics |
| `petty` | Petty cash |
| `outstanding` | Outstanding and receivables |
| `data-centre` | Import/export/sync operations |
| `est` | Quotation/estimate builder |
| `media` | Image library |
| `admin-roles` | Role manager |
| `attendance` | Attendance capture |
| `pl` | P&L by project |
| `invoice-gen` | Tax invoice generator |
| `tally-import` | Tally import/export |
| `audit` | Stock audit |
| `tasks` | Tasks and activity feed |
| `catalogue` | Product catalogue |
| `daily-book` | Daily book |
| `party-ledger` | Party ledger |
| `voucher-entry` | Voucher entry/checker queue |

## Routes

There is no framework router. Routing is implemented by `showPage(id)`, which toggles matching `p-{id}` page containers, updates the title, checks role permissions, and delegates to `renderPage(id)`. Navigation elements call `showPage(...)` directly from inline `onclick` handlers.

## Components

Current reusable UI patterns are CSS/HTML conventions rather than framework components:

- Sidebar navigation (`.sb`, `.ni`, `.ns`).
- Sticky topbar, search, add, and sync controls.
- Cards and KPIs (`.kc`, `.kgrid`).
- Panels (`.panel`, `.ph`, `.pt`, `.ps`).
- Tables (`.tw`, `table`, badge helpers).
- Filter bars (`.fbar`, `.fc`, `.fi`).
- Kanban cards/columns (`.kb-*`).
- Modal shell (`#modal-ovl`, `.modal`, `.mh`, `.mb`, `.mf`).
- Print-preview overlays for estimates, invoices, purchase orders, catalogues, ledgers, and audit reports.

## Database Schema

There is no committed database schema or server migration yet. The effective schema is the shape of browser-resident arrays and spreadsheet sheet headers.

### Embedded domain collections

| Collection | Representative fields | Current owner |
|---|---|---|
| `Q26` / `_D.quotes` | `id`, `vdate`, `name`, `ref`, `phone`, `div`, `by`, `qdate`, `mode`, `remarks`, `stage`, `value`, `cash`, `bank` | Quotation and pipeline modules |
| `SALES` / `_D.sales` | sale/customer/order financial fields used by sales, revenue, outstanding, P&L, invoices | Sales and finance modules |
| `VISITORS` | visitor lead fields | Walk-in module |
| `NAVAKI` | lead/follow-up fields | Navaki module |
| `INV_DATA` | `sl`, `model`, `name`, `cat`, `vendor`, `size`, `material`, `sku`, `cost`, `mrp`, `margin`, `status`, `has_img`, `locs` | Inventory/catalogue/audit modules |
| `PETTY` | petty cash expense/payment fields | Petty cash module |
| `ARCHS` | `sno`, `name`, `firm`, `type`, `loc`, `gift`, `visited`, `assigned`, `last_contact`, `remarks` | Architect CRM |
| `ESTIMATES` | saved estimate objects in localStorage | Estimate builder |
| `MEDIA_LIB` | uploaded image metadata/data URLs in localStorage | Image library |
| `ATT_RECORDS` | attendance records with selfie/location fields | Attendance |
| `TASKS` / activity feed | browser task/activity records | Task module |
| `PO_DATA` | purchase orders | Purchase-order module |
| Voucher/checker queues | accounting voucher records | Voucher module |

### Spreadsheet sync schema

An embedded Google Apps Script snippet defines `SHEET_MAP`, `readSheet`, `getDelta`, `pushAll`, `upsertRow`, `appendRow`, `deleteRow`, `batchUpsert`, and `initHeaders`. This is the current API/database bridge and should be extended for D&W masters before adding a separate backend.

## API Endpoints

There are no repository-hosted HTTP endpoints. Existing integration points are:

- Google Apps Script `doGet(e)` with actions such as read and delta reads.
- Google Apps Script `doPost(e)` with actions for push, upsert, append, delete, batch upsert, and header initialization.
- Browser-side sync functions under the Data Centre module for Apps Script connection, polling, conflict badges, manual import/export, and push-all operations.
- External WhatsApp links generated with `wa.me` for customer follow-up.
- Browser File APIs for imports and image uploads.

## State Management

State is managed through globals plus localStorage. Important patterns:

- Core data globals: `Q26`, `SALES`, `VISITORS`, `NAVAKI`, `INV_DATA`, `PETTY`, `ARCHS`.
- Configuration: `CFG` from `madio_cfg3`.
- Estimate/media state: `madio_estimates`, `madio_media`.
- Role management state: role definitions and admin log in browser storage.
- Inventory image map: `madio_inv_imgs_v1`.
- Offline/sync queue functions enqueue and reconcile changes for spreadsheet-backed sync.

## Authentication

Authentication is local PIN-based role selection, not server authentication. Users select a role on the login screen and enter a PIN. `_launchApp()` initializes the app after successful PIN verification. This is suitable for showroom/offline use but not sufficient for multi-user ERP security without a server-backed identity provider.

## Current Role Based Security

Role defaults are configured in `ROLE_DEFAULTS`, loaded into `ROLES`, and applied by `_applyAccess()`. Access currently controls page visibility and feature access in the browser. The Admin Role Manager can edit users, PINs, page permissions, groups, visual identity, and logs changes locally.

## Current Product Module

The product module is currently furniture/MAP inventory-oriented:

- Stock inventory with cards and table views.
- Inventory analytics by category/status/value.
- Product catalogue and CSV export/print.
- Inventory-image enrichment through central image JSON/CDN import.
- Purchase-order importer can generate inventory SKUs.

The Doors & Windows data currently exists mainly as estimate line inputs and `DW_RATES`, not as normalized product-master records.

## Current Quote Module

There are two quotation experiences:

1. CRM quotations (`Q26`) for pipeline and customer follow-up.
2. Estimate/quotation builder (`est`) for Furniture, MAP, and D&W with line items, totals, discounts, terms, images, print preview, save/load, and convert-to-quote support.

The current D&W quote flow is manual rate-entry/area-based and should be replaced incrementally with a master-driven configurator.

## Current Inventory Module

Inventory uses `INV_DATA` and supports list/card display, search, category/status filtering, analytics, images, quick stock selection from quotes, catalogue printing/export, stock audit sessions, and purchase-order import synchronization.

## Current Project Module

There is no standalone project master yet. Project-like behavior is inferred from quote/customer names, sale references, P&L grouping, and pipeline stages. Milestone 2 should introduce a normalized `projects` master while preserving current quote/sales records.

## Current Customer Module

There is no dedicated customer master yet. Customer details are embedded in quotations, sales, visitors, ledgers, vouchers, invoices, and estimates. Milestone 2 should introduce a customer master with deduplication and backward-compatible lookup from existing records.

## Current Image Upload

Image handling exists in three areas:

- Estimate images through `attachImages`, `renderImageGallery`, and `removeEstImage`.
- Media library uploads through `libUpload`, `renderMedia`, filters, and localStorage.
- Inventory image imports through `importInvImages`, `EMBEDDED_INV_IMGS`, and optional CDN JSON settings.

D&W typology previews, technical drawings, sections, elevations, and plans should reuse the media-library storage/display model.

## Current PDF Generator

The application currently generates printable HTML documents and calls browser print. There is no dedicated PDF library committed. Professional quotations should first extend the print templates with print CSS, page numbering, and branded sections; optional PDF export can be added later if dependencies are introduced.

## Current Printing

Printing is implemented via generated HTML documents and browser `print()` for estimates, invoices, purchase orders, catalogues, ledgers, and stock-audit reports. This is reusable for branded D&W quotation PDFs/printouts.

## Current Reports

Existing reports include dashboard KPIs, revenue charts, division chart, team leaderboard, lead-source charts, inventory analytics, outstanding receivables, P&L by project, daily book, party ledger, Tally exports, stock-audit review/report/coverage/prices/condition/floors/history, catalogue export, and Data Centre exports.

## Reusable Modules for Doors & Windows ERP

| Reusable module | How to reuse |
|---|---|
| Page shell and navigation | Add D&W master/configurator pages without changing existing routes. |
| Modal shell | Reuse for CRUD dialogs across master tables. |
| Table/filter styles | Build a generic master table renderer. |
| Data Centre import/export | Add master dataset import/export and spreadsheet sync. |
| Media library | Store typology images/drawings centrally. |
| Estimate builder | Replace only D&W internals with configurator-driven openings. |
| Print templates | Extend quote print output with specifications, images, terms, warranty, and acceptance. |
| Role manager | Add permissions for D&W masters, pricing, BOM, production, and installation. |
| Audit/activity log patterns | Use for master audit history and ERP lifecycle events. |
| Inventory/catalogue | Link BOM output and hardware/accessory picking to existing inventory patterns. |

## Target Milestone Plan

| Milestone | Deliverable | Compatibility rule |
|---|---|---|
| 2 — Master Tables | LocalStorage/spreadsheet-backed D&W master registry, CRUD UI foundation, import/export, seed data, migration scripts | Do not alter existing `Q26`, `SALES`, or `INV_DATA` shapes. |
| 3 — Product Configurator | Master-driven dependent selections for D&W product families through installation type | No hardcoded option lists in the configurator UI. |
| 4 — Quote Builder | Opening schedule integrated into D&W estimates | Existing Furniture/MAP quote flows remain unchanged. |
| 5 — Pricing Engine | Configurable rate cards and margin/discount/GST calculations | Remove manual D&W selling price entry only after pricing parity tests. |
| 6 — BOM | Generated profile/glass/mesh/hardware/accessory lists | Link to inventory without mutating stock automatically. |
| 7 — PDF | Professional branded quote print/PDF template | Continue supporting browser print. |
| 8 — Dashboard | Sales/project/production/installation pipeline dashboards | Existing dashboard KPIs remain visible. |
| 9 — Production | Cutting list, glass order, picking, fabrication, packing, dispatch, installation sheets | Driven from approved quotations only. |
| 10 — Testing | Regression fixtures for existing CRM plus D&W engine calculations | Compile/lint every milestone. |

## Risks and Recommendations

1. **Single-file complexity:** new ERP functionality should be introduced with clearly marked sections and reusable helpers before any file split.
2. **No real database migrations yet:** add migration/seed scripts as documented browser/spreadsheet data contracts until a backend is selected.
3. **Local authentication only:** server-backed auth is required before exposing sensitive pricing, margin, and customer data online.
4. **No normalized customers/projects:** create masters in Milestone 2 and backfill references non-destructively.
5. **Manual D&W rates:** master-driven dependencies, validations, SKU generation, and pricing must be added before replacing the current D&W estimator.
