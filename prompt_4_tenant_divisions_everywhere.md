# Prompt 4: Every company's own divisions work end to end (P0)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

Industry packs (`backend/industry_packs.py`) give each company its own
divisions — "Solar", "Electrical", "Consultation", "uPVC"… — and the lead form
now offers them (`frontend/src/pages/Leads.jsx` reads `TenantConfigContext`).
But several server paths still accept only MADIO's three divisions, so a
non-MADIO company **cannot save a lead with its own division**:

```
POST /api/leads {division: "Solar"}  (tenant with the solar pack)
→ 400 "Division must be one of Furniture, D&W, MAP"
```

This breaks the core rule "Divisions and tenants are configuration, not forks".

## Evidence (file:line at commit 36f0cca)

- `backend/server.py:2190` — lead normalizer calls `ops.validate_division`,
  which only knows MADIO's aliases.
- `backend/operations.py:24` `DIVISIONS = ["Furniture", "D&W", "MAP"]`,
  `_DIVISION_ALIASES`, `validate_division`, `normalize_division` (defaults
  unknown values to "Furniture"), `DIVISION_WORKFLOWS` (project checklists
  for the three divisions only), `SURVEY_DIVISIONS = {"Furniture", "MAP"}`.
- `backend/server.py:6435` — projects already fall back to the tenant's
  business-profile slugs, but then run the Furniture checklist.
- `backend/server.py:6809` `_survey_division` — refuses site surveys for any
  division other than Furniture/MAP.
- `backend/lifecycle.py:26` `DIVISIONS` — now only a default; rollups use
  `lc.use_divisions()` / `lc.divisions()` (see `server._tenant_divisions`).
- `backend/go_live_import.py:42`, `backend/seed.py:102` — MADIO-only, leave
  them alone (they load MADIO's own data).

## Goal

A company's divisions come from its business profile
(`/settings/business-profile`, `_get_business_profile`) everywhere a division
is validated, normalised or used to pick behaviour. MADIO's behaviour and
data stay byte-for-byte the same.

## Scope

1. One helper (e.g. `async def _division_for(user, raw) -> str`) that accepts
   a division when it matches one of the tenant's profile slugs (case- and
   space-insensitive), still maps MADIO's aliases ("dw", "mdw", "paints"…)
   for the MADIO tenant, and raises `ValueError` naming **the tenant's own**
   divisions otherwise. Use it in the lead normalizer and projects.
2. Project checklists per division as configuration: store an optional
   `milestones` list on each `Division` in the business profile
   (`models.Division`), fall back to `ops.DIVISION_WORKFLOWS` for MADIO's three,
   and to a generic list (Survey → Quotation → Order → Execution → Completion)
   for any other division. `COMPLETION_STAGE` / `INSTALLATION_EQUIVALENTS`
   semantics must still hold (journey, delivered stamping).
3. Industry packs (`industry_packs.py`) set sensible `milestones` per
   division (solar: Site Survey, Proposal, Subsidy Docs, Installation, Net
   Metering, Commissioning, Completion…), editable in Business Settings
   (`frontend/src/components/DivisionsManager.jsx`).
4. Site surveys: allow any division except one whose company uses the
   openings survey (`dwsurvey` module / D&W-style division). Replace the
   hardcoded `SURVEY_DIVISIONS` check with that rule.
5. Leave reports/analytics alone — they already use `lc.use_divisions`.

## Tests (`backend/tests/`)

- Solar-pack tenant: create a lead with division "Solar" → 201; with "MAP" →
  400 whose message lists Solar/Electrical.
- MADIO tenant: "dw" still normalises to "D&W"; existing tests unchanged.
- A project created for "Solar" gets the solar checklist; ticking its
  completion stage marks it delivered as Furniture projects do today.
- Site survey on a "Solar" project works; on a D&W project still points to
  the D&W survey.
- Tenant isolation: tenant A's divisions are never accepted for tenant B.

Run `python -m pytest tests -q` from `backend/` (all green) and
`CI=true npm run build` from `frontend/`.

## Out of scope

Renaming MADIO's divisions, changing `go_live_import.py` or `seed.py`.
