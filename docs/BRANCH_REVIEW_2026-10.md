# Branch & PR review against main (2 Oct 2026)

Every branch and PR (#1–#12) was compared with `main` by content, not commit
id: main's history was rewritten when the web stack was restored, so git
reports nearly every old commit as "missing" even when its code is there.

## Ported into main

| From | What |
|---|---|
| PR #12 `feat/project-petty-cash-ledger` (b69c397) | Quotation form closes on Escape; Quote Follow-ups no longer sticks on "Loading…" when the fetch fails |
| PR #12 (ff55a51) | Revenue by division on the Command Centre (booked sales, cancelled excluded), beside Pipeline by division |
| PR #11 `claude/madio-crm-go-live-px66h5` (8cee9e3) | `backend/tools/reset_user_pin.py`, for unlocking an admin from the database (now with `--tenant`) |
| `worktree-hashed-enchanting-pinwheel` (78949e4) | Business Settings brand colours now restyle the app; colour pickers on the fields |

## Already in main (newer or stronger version)

- Cashbook privacy mask and customer phone index (`worktree-e2e-qa-fixes`): main masks every ledger amount and wallet balance.
- Meet planner IST date shift: main uses `isoDateIST`.
- Command Centre KPI overview (PR #12): main's Command Centre is a later rewrite with the same KPIs.
- Responsive sidebar drawer (`claude/crm-auth-cross-platform-1ic4uz`): `LightAppShell` has the mobile drawer.
- Canonical CRM v1 (`worktree-madio-canonical-crm-v1`): main's `/api/v1` has every route and more (accounts, contacts, activities, brands).
- Login lockout, tenant-scoped reports, workflow enforcement/editor, conversion fixes (PRs #5–#7, #10): present in refactored form.

## Not ported, on purpose

- Project petty-cash ledger UI (PR #12, 551ec55): Petty Cash is read-only history; money requests and Cashbook wallets replaced it (docs/FINANCE.md).
- `New`, `conflict_220726_0734`, `production`, `pr/production-merge`, `codex/…`: Emergent-era scaffolding, test reports, the single-file `MADIO_CRM_v16.html`, the Jekyll workflow. All superseded by the current React app.

PRs #11 and #12 are still open; everything useful in them is now in main, so
they can be closed.
