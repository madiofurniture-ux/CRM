# TASK: Wire Live Backend Aggregation for Command Centre Dashboard
SYSTEM: Everything Claude Code (ECC) Autonomous Execution Harness
TARGET: Local workspace (madiofurniture-ux/CRM)
CONSTRAINTS:
- Local execution only. Do NOT run `git push`.
- Maintain all 545/545 backend tests (`pytest backend/tests/`).
- Zero spec hallucination: Aggregate strictly from active MongoDB collections (`leads`, `quotes`, `sales`, `projects`, `tasks`).

---

## 1. RECONNAISSANCE & SCHEMA MAPPING (Zero Writes)
1. Inspect `backend/server.py`:
   - Identify existing collection handles (`db.leads`, `db.quotes`, `db.sales`, `db.projects`, `db.tasks`).
   - Note tenant scoping conventions (e.g., `user["tenant_id"]` or `tenant_filter(user)`).
   - Check existing approval logic in `backend/lifecycle.py` for discount thresholds.
2. Inspect `frontend/src/pages/CommandCentre.jsx`:
   - Identify state hooks and where static mock numbers are currently assigned for the 5 KPI cards, the pipeline bar chart, and the today action stream.
3. Verify test baseline:
   - Run `pytest backend/tests/` to confirm all 545 tests pass before making any changes.

---

## 2. BACKEND AGGREGATION ENDPOINT
In `backend/server.py`, add a tenant-scoped endpoint:
`GET /api/overview/command-centre`

Compute and return the following payload:
1. **KPI Rollups**:
   - `open_pipeline`: Sum of `estimated_value` or quote totals for active, un-won leads/quotes.
   - `won_this_month`: Sum of `total_amount` for sales created within the current calendar month, along with order count.
   - `receivables`: Sum of outstanding balances (`balance_due` or `unpaid_amount`) across sales.
   - `projects_live`: Count of projects in non-terminal stages (e.g., not "Completed" or "Handed Over"), and count of projects flagged "at risk" or with overdue tasks.
   - `sla_breaches`: Count of open tasks past their `due_date`.
2. **Pipeline by Unit**:
   - Breakdown of active pipeline grouped by unit/division (`Design Studio`, `Factory`, `Site Teams`, etc.).
3. **Pending Actions (Unit Scope)**:
   - Recent quotes requiring discount threshold approval (`lifecycle.needs_approval == True`).

---

## 3. FRONTEND DATA HYDRATION
In `frontend/src/pages/CommandCentre.jsx`:
1. Add an `useEffect` hook fetching `GET /api/overview/command-centre` using the existing authenticated API client.
2. Provide loading skeletons or clean fallback state while data resolves.
3. Replace hardcoded KPI cards, unit bar chart heights, and today's action item with the live response data.
4. Format currency figures cleanly in Lakhs/Crores using `font-mono` tabular numerals.

---

## 4. VERIFICATION & AUTO-HEALING
1. Run backend tests: `pytest backend/tests/` (Ensure 545/545 pass; add a unit test for `GET /api/overview/command-centre`).
2. Run frontend build: `npm run build` or `npx craco build` (Ensure 0 errors/warnings).
3. Lint: `npx eslint frontend/src --ext .js,.jsx --fix`.

---

## 5. LOCAL ATOMIC COMMIT
- Branch: `feat/command-centre-live-data`
- Commit: `git commit -am "feat(overview): wire live backend aggregation to command centre kpis and pipeline chart"`