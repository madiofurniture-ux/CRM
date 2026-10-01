# Flows

Admin → **Flows** (`/admin/flows`). A flow watches one type of record and,
when its trigger fires and its conditions hold, runs its steps in order.
Workflows (`/admin/workflows`) still own each record type's stages and stage
gates; flows are the automation layer on top.

## Building a flow
1. **When** (trigger)
   - A record is created · A record is saved · A record enters a stage ·
     A field changes
   - Scheduled: **N days before/after a date field** (e.g. 2 days before a
     quotation's *valid until*, on a lead's *follow-up date*), or **stuck in
     a stage for N days** (counted from `stage_entered_at`).
2. **Only if** (optional): field comparisons (is, is not, contains, >, ≥,
   <, ≤, is empty, is not empty) on any field or the stage; all or any.
3. **Then, in order** (up to 10 steps): create a task · alert a teammate
   (a high-priority task due today) · set a field · assign the owner ·
   WhatsApp the customer (the same templates as everywhere else) · wait N
   days. Titles and messages take `{name}`, `{record}`, `{stage}` or any
   field such as `{customer}`.

The empty page offers three starting points (quote expiring, stalled
negotiation, big new lead). They fill in the builder and nothing is saved
until you save. **Test on a record** dry-runs a saved flow: it shows whether
each condition holds and what would run, without writing anything.

## How it runs
- Event flows run after every successful save, through the same hook as
  stage history and workflow rules (`run_stage_automation`). That covers
  screens, imports through the API, Convert buttons and quote approval.
- Steps write directly, so a flow's own changes never trigger flows again
  (no loops).
- Scheduled flows and waits are checked every 10 minutes on the server's
  background loop; **Run scheduled now** checks this company's at once.
  Each record fires once per occasion. After downtime, a date flow catches
  up for up to 3 days.
- A wait parks the run until its date. Switching the flow off, deleting it,
  or deleting the record cancels the wait.
- Every run is logged (Run log tab) with each step's result. A failing step
  is logged and the rest still run.
- Scheduled runs act as "Flow automation" inside the flow's own company. The
  company comes from the stored flow, never from a request.

Limits: 50 flows per company, 10 conditions, 10 steps, waits up to 90 days.

API (admin only): `GET /api/flows/meta`, `GET/POST /api/flows`,
`PUT/DELETE /api/flows/{id}`, `POST /api/flows/{id}/toggle`,
`POST /api/flows/{id}/test`, `POST /api/flows/run-scheduled`,
`GET /api/flow-runs`. Logic: `backend/flows.py` (pure) and the "Flows"
section of `server.py`. Collections: `flows`, `flow_runs`.
Tests: `backend/tests/test_flows.py`.
