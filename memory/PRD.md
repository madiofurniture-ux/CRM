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
- Tax Invoice generator with GST + line items
- Meet Planner (4-week grid)
- Quotation Builder with line items + print/PDF
- Petty Cash ledger
- Outstanding report (combined view of unpaid sales + high-value unconverted quotes)

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
