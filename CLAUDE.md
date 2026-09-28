# MADIO CRM — Project Context

## Business
MADIO Group, Hyderabad (showroom: Kondapur). Three divisions:
- Furniture
- MAP (Madio Architectural Cluster, texture/acrylic paints)
- Doors & Windows (D&W)

All three follow the same workflow. MADIO sells and manages; manufacturing/
delivery partners (vendors) fulfil orders on MADIO's behalf.

## Roadmap
1. Go live for MADIO Group (tenant 1)
2. Onboard partner's interior design firm (tenant 2)
3. Commercialise as a multi-tenant SaaS product

## Stack and repo state (read before starting any task)
- **System of record:** Python (FastAPI) backend + MongoDB, React frontend.
  Multi-tenancy is built in `backend/tenancy.py`.
- **Heads-up:** commit `bc0af67` ("initialize Android project structure")
  removed `backend/`, `frontend/`, `db/`, `deploy/`, `netlify/` and
  `.github/workflows/` from `main`. The last full web-stack tree is
  `c04a55a`. Inspect it with `git show c04a55a:<path>` or
  `git ls-tree -r c04a55a --name-only`.
- **Current HEAD:** a Kotlin / Jetpack Compose Android scaffold in `app/`
  (package `com.example.madiocrm`). `CrmRepository.kt` is an in-memory
  singleton. It has no backend, no persistence and no tenancy yet.
- If a task needs backend or frontend code, confirm with the user whether to
  restore it from `c04a55a` before editing. Don't restore it silently.
- `docs/` (PRD, module architecture, Mongo indexes, go-live checklist) survived
  and describes the web stack.

## Core rules (never break)
- Every document carries `tenant_id` (the company/tenant) and `division`.
  The codebase uses `tenant_id`, not `company_id`. Don't introduce a second name.
- Every query is tenant-scoped. In the backend, go through the single
  chokepoint `tenancy.scope(query, collection, user)` for reads and
  `tenancy.stamp(doc, collection, user)` for writes. New tenant data
  collections must be added to `TENANT_COLLECTIONS`.
- The tenant comes from the authenticated user record, never from a header or
  client-editable claim. Fail closed: no tenant means match nothing.
- No cross-tenant reads, ever.
- One codebase. Divisions and tenants are configuration, not forks.
- Quotation is ONE engine with per-division templates (`quotation_templates.py`);
  only the formats differ.
- Don't rename or restructure modules outside the task's scope.

## End-to-end flow (the spine)
Visitor → Lead → Quotation → Sales Order → Vendor PO → Vendor Delivery
→ Project Execution/Installation → Customer Payment Closed

## Supporting modules
Finance (customer receipts, vendor payments, ledger), Attendance.

## Vendor module (critical)
- Vendor partners master (per division), collection `vendors`
- Vendor PO linked to a Sales Order (one SO can have multiple POs), collection
  `purchase_orders`
- PO status: Raised → Confirmed → In Production → Dispatched → Delivered → Installed
- Vendor payments against a PO: amount, date, mode, reference
- Per PO: value, paid, balance, promised vs actual delivery date
- Per SO: sale value − total PO cost = gross margin

## Working rules for Claude Code
- One task per session. Plan first, then implement, then test, then commit.
- Small commits with clear messages.
- If a change touches more than one module, stop and list the impact before editing.
- Backend tests: `pytest` from `backend/` (pre-approved in `.claude/settings.json`).
