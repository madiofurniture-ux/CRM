# MADIO CRM — PRD

## Problem Statement
"Help me build CRM app based on https://github.com/odoo/odoo and the app I built for my organization"

User uploaded MADIO_CRM_v17.html (their existing custom CRM) and seed data files
(visitors CSV + annual stock audit XLSX) for a furniture / paints / doors-and-windows business.

## User Choices
- **Scope (initial MVP)**: Core CRM + Inventory + Tasks
- **Visual design**: Fully redesigned — fresh distinctive look (not replicating the dark+gold of v17)
- **Authentication**: PIN-based login with Role Manager (username + 4-digit PIN, page-level permissions)
- **Data**: Seeded with real sample data from uploaded CSV/XLSX

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + JWT (PyJWT) + bcrypt
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn-ui + Recharts + Sonner toasts
- **Auth**: JWT in localStorage; Bearer in Authorization header; role + page array gating
- **Design**: Earthy palette (terracotta #C85A32 + moss #4A5D4E on bone #F8F7F4), Manrope + IBM Plex Sans + JetBrains Mono

## Personas
- **Admin** — manages users, has full access
- **Sales executive (Raghu / Nenmu / Gowtham)** — works visitors, leads, quotes, sales, inventory, tasks

## Done (v2 — 2026-07-26) — P1 feature batch
- **Tax Invoice** module with GST breakup (CGST/SGST/IGST auto-computed), line items, editable HSN, and print-to-PDF preview
- **Quotation Builder** — Quotes now supports optional line items with subtotal + GST + grand total, plus print/PDF export
- **Meet Planner** — weekly grid view (8am–8pm × 7 days) + list view, click-slot-to-schedule, Lead/Architect/Customer/Internal ref types
- **Petty Cash Ledger** — Cash In / Out entries with running balance, category & mode
- **Outstanding Report** — 3 KPIs (unpaid sales / invoices / hot pipeline ≥₹1L) + aging buckets (0-30/31-60/61-90/90+) + 3 detail tables
- **Attendance with geofencing** — browser geolocation + backend haversine distance vs office radius, check-in/check-out, duration_min, admin sees "team today" view, 30-day history
- **Office & Geofence settings** — admin editable Company/Address/GSTIN/InvoicePrefix + Office lat/lng/radius + "Use my location" button (in Role Manager page)
- **Mobile UI** — sidebar becomes hamburger drawer <lg breakpoint, Topbar shrinks, table `overflow-x-auto` on all data-dense pages, buttons compact on <sm
- **Print CSS** — @media print rules hide sidebar/topbar and dedicate full page to invoice/quote

## Done (v1 — 2026-06-22)
- PIN-based auth (login, JWT issuance, /me, admin-only user CRUD)
- Sidebar + Topbar layout with role-aware nav
- **Login**: split-screen with hero image + role cards + PIN pad
- **Dashboard**: 6 KPIs, monthly revenue bar chart, division pie chart, pipeline-by-stage bars, follow-up alerts, recent quotes
- **Pipeline**: drag-and-drop Kanban across 6 stages (auto-syncs to backend)
- **Quotations**: filterable table + create/edit/delete modal
- **Sales register**: filterable table with paid/balance
- **Visitors**: walk-in log with inline stage updates
- **Leads**: pipeline with follow-up date highlighting overdue
- **Architects**: contact directory card grid
- **Inventory**: grid + list view toggle, filters, add item
- **Inventory Analytics**: KPIs + breakdowns by category/vendor/location + top items
- **Tasks**: open/done/all filter, inline complete toggle, priority badges
- **Role Manager**: admin-only user management with per-page permission checkboxes
- **Seed data**: 4 users + 25 visitors + 120 inventory items + ~80 sales + 15 leads + 10 architects + 15 quotes + 10 tasks loaded on first startup

## Test Credentials
See `/app/memory/test_credentials.md` — admin / 1234, raghu / 2222, nenmu / 3333, gowtham / 4444

## Backlog (next iterations)
### P1 — high impact
- ~~Tax Invoice generator with GST + line items~~ ✅ done v2
- ~~Meet Planner~~ ✅ done v2
- ~~Quotation Builder with line items + print/PDF~~ ✅ done v2
- ~~Petty Cash ledger~~ ✅ done v2
- ~~Outstanding report~~ ✅ done v2
- ~~Attendance with geofencing~~ ✅ done v2
- ~~UI mobile responsiveness~~ ✅ done v2

### P2 — nice-to-have
- P&L by project
- Stock Audit with camera-selfie + location tracking
- Attendance with check-in/out
- Tally XML import/export
- Activity feed
- Data Centre (CSV import/export, Google Sheets / SharePoint live sync)
- Architect → Lead linking and visit history
- Quote → Sale conversion flow
- WhatsApp deep-link buttons on visitor/lead rows
- AI: auto-summarise lead remarks, smart follow-up suggestions
