# Phase 3 — Industry Operations: Plan + Result

## Scope decision (before implementation)

`docs/FEATURE_ROADMAP.md`'s Phase 3 has three parts: D&W (extend, don't
rebuild), Paints (shade/formula/batch), Furniture (design brief/concept
approval), plus one explicit exit test — a D&W survey should block a linked
project's release-to-production until client sign-off is recorded, and the
roadmap itself says to verify that gate doesn't exist yet before building it.

**Verified this pass:** it did not exist. `backend/models.py`'s `DWSurvey`
had no sign-off field at all, and `server.py`'s `create_project_daily_log`
(the endpoint that advances a project's `current_milestone`, including to
`"Production"` — see `lifecycle.DEFAULT_PROJECT_MILESTONES`) applied any
milestone value unconditionally.

**In this pass:** the D&W gate only — it is the one concretely-specified,
testable deliverable, and `dw_surveys`/`dw_openings` genuinely just needed
extending, not rebuilding.

**Explicitly deferred, not implemented this pass:**
- **Paints (shade/formula/batch) and Furniture (design brief/concept
  approval) models** — per the roadmap's own framing, these are "genuinely
  new entities with design decisions" (what does a formula record look like?
  what states does a concept approval move through?) that deserve their own
  scoping conversation, same reasoning Phase 2 used to defer Team/assignment
  and the Quotation rebuild. Today these stay manifest `custom_fields`
  declarations only.
- Any change to `modules/*/manifest.json` — not touched.

## What was implemented

### `backend/models.py` — `DWSurveyBase`
Added three optional fields (default `False`/`""`, so every existing survey
document loads unchanged): `client_sign_off`, `client_sign_off_at`,
`client_sign_off_by`. No new endpoint needed to set them — `PUT
/dw-surveys/{id}` already accepts an arbitrary `dict` patch (see
`update_dw_survey`), so a client can already `PUT
{"client_sign_off": true}`.

### `backend/server.py` — `create_project_daily_log`
Before inserting a daily log, if `payload.current_milestone == "Production"`,
the handler now looks up every `dw_surveys` row linked to that
`project_id` (tenant-scoped) and rejects the write with `400` naming any
survey still missing `client_sign_off`. Any project with zero linked D&W
surveys (Furniture/MAP jobs, or a D&W job whose survey isn't linked via
`project_id`) is unaffected — the gate only fires when there is something to
gate.

### Tests
`backend/tests/test_project_tracking.py` — two new cases alongside the
existing daily-log tests: milestone `"Production"` is rejected (`400`,
survey id named in the message) while the linked survey is unsigned, and
succeeds once `client_sign_off` is set.

## Verification run this pass

```
cd backend
python -m py_compile server.py models.py
python -m pytest tests/test_project_tracking.py -q   # 9 passed
python -m pytest tests/ -q --deselect tests/test_tenant_isolation_api.py   # 566 passed
```
