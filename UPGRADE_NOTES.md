# MADIO CRM — Emergent → Web-parity upgrade

This brings the Emergent-scaffolded React/FastAPI app up to the feature set of the live
single-file web CRM (`crm.madiofurniture.com`). The web app is the source of truth for the
business rules; this port re-implements them as testable server-side logic instead of the
inline JavaScript they live in there.

## Backend

- **`lifecycle.py` (new)** — pure, side-effect-free domain logic ported from `index.html`.
  Forgiving date parsing (handles the real typos in the data: `24/o1/2026`, `17/01.2026`,
  trailing-slash dates), number→string coercion for sheet round-trips, timestamp-corruption
  guards (`value > 1e10` → 0), the derived quote **sales-status axis**
  (Draft/Sent/Negotiation/Won/Lost/Expired from the ops stage), document-id generators
  (`AF-YYMM-NNN`, `MF NNN`, `LD-/PY-/PM-/DW-`), division report rollups + WhatsApp summary,
  outstanding aging buckets, `sale_phone` fallback-to-quote, and the customer-journey join.
  Covered by **`tests/test_lifecycle.py` (22 tests, all passing)**.

- **`models.py`** — Lead reworked to the unified intake schema (`lead_id`, `source`,
  `intake_date`, `division`, `owner`, `next_action_date`); Quote gained `status`, `version`,
  `discount`, `approval`, `lost_reason`, `next_action_date`; Sale gained `phone`. New models:
  `QuoteLine`, `Payment`, `Activity`, `Project`, `DWSurvey`, `DWOpening`.

- **`server.py`** — new/updated endpoints:
  - `GET/POST/PUT/DELETE /api/leads` — auto `LD-` id, phone-dedup warning on create.
  - `GET/POST/PUT/DELETE /api/quotes` — enriches each read with `derived_status`,
    `age_days`, `due_flag`, `is_open`; closes the matching lead on create.
  - `/api/payments` — rolls the amount into the linked sale's paid/balance, auto-flips
    stage to “Payment Received” at zero balance.
  - `/api/projects` (MAP), `/api/dw-surveys` + `/api/dw-openings`, `/api/quote-lines`,
    `/api/activities`.
  - `GET /api/reports?period=…` — division rollup + `whatsapp` summary string.
  - `GET /api/alerts` — grouped follow-up / money / dead-stock alerts.
  - `GET /api/journey/{phone}` — customer-360 timeline.
  - `POST /api/convert/{lead-to-quote,quote-to-sale,survey-to-quote}/{id}`.
  - `dashboard/stats` now uses the derived status axis and excludes Dealer-Catalog stock.

- **`seed.py`** — leads/quotes reseeded on the real vocabularies; sales-role users granted
  the new pages.

## Frontend

- **`lib/nav.js` (new)** — single source of truth for pages, routes, and the role-aware
  **app-switcher** groups (Sell / Deliver / Stock / Money / Relations / Command). Sidebar,
  RoleManager, and route gating all read from it.
- **New pages** — `Reports`, `Alerts`, `Projects` (8-stage MAP), `DWSurvey` (openings +
  auto sqft + convert-to-quote). Previously-orphaned `Outstanding`, `Invoices`, `PettyCash`,
  `Meets`, `Attendance` are now routed and in the nav.
- **`Leads`** — unified schema, saved-view chips (Due/Overdue/Untouched/…), inline
  stage + next-action edits, convert-to-quote, journey.
- **`Quotes`** — derived status pill + due/stale flags, saved-view chips
  (My Open/Awaiting/Hot/Overdue/Won-MTD), convert-to-sale, journey.
- **`Sales`** — unpaid/mine/delivered views, in-row **payment recording**, WhatsApp
  payment reminders (with quote-phone fallback), journey.
- **`Pipeline`** — Kanban columns switched to the sales-status axis.
- **New shared components** — `JourneyDrawer` (customer-360 slide-over), `FilterChips`.

## Run

Backend: `cd backend && pip install -r requirements.txt && uvicorn server:app --reload`
(needs `MONGO_URL` + `DB_NAME` in `backend/.env`).
Frontend: `cd frontend && yarn install && yarn start` (needs `REACT_APP_BACKEND_URL`).
Tests: `cd backend && python -m pytest tests/test_lifecycle.py -q`.

> Not yet ported from the web app (deliberate, larger follow-ups): Quote Workspace
> line-item builder UI, Data Centre / Google-Sheets sync, Tally import, media library,
> stock ledger & executions, `_safety` snapshot/rollback layer, offline queue.
