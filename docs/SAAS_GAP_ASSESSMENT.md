# SaaS gap assessment — what's left to sell the CRM to Indian businesses

Assessed at commit `36f0cca` (branch `claude/design-system-extraction-5rcdhw`),
after Business Setup, industry packs, the platform console and plans landed
(see `docs/BUSINESS_SETUP.md`). Each gap below has a ready-to-run Claude Code
prompt at the repository root. Run one prompt per session (CLAUDE.md: "One
task per session"), in the order given; each prompt names its own evidence,
scope, tests and what's out of scope.

## Already in place

Multi-tenancy with fail-closed scoping (`tenancy.py`); configurable workflows
and Flows; industry starter packs for ten trades; the Indian company/GST
profile with GSTIN checksum, amounts in words and IGST detection
(`india.py`); per-company divisions in reports, analytics and P&L; quote
terms from the company profile; platform console with plans, trials, seats
and suspension enforced server-side (`plans.py`); login that works for many
companies.

## Gaps, in order

| # | Priority | Prompt | Gap |
|---|---|---|---|
| 4 | **P0** | `prompt_4_tenant_divisions_everywhere.md` | A non-MADIO company **can't save a lead with its own division** (`POST /api/leads` → 400 "Division must be one of Furniture, D&W, MAP"; `server.py:2190` → `operations.validate_division`). Projects run the Furniture checklist and site surveys refuse other divisions. Verified on a solar-pack tenant. |
| 5 | P1 | `prompt_5_self_signup_and_billing.md` | No public sign-up and no payment: only the owner creates companies; plans carry no prices; an ended trial stays read-only until the owner acts. Razorpay subscriptions + GST invoices for the subscription. |
| 6 | P1 | `prompt_6_whatsapp_per_tenant.md` | WhatsApp Cloud API is single-tenant (`WHATSAPP_TENANT_ID`, `server.py` ~9077). Each company needs its own number, routing and templates. |
| 7 | P1 | `prompt_7_secure_login_otp.md` | PIN-only login; users can't change their own PIN; no forced change of an issued PIN; 7-day tokens aren't revoked on PIN reset; no mobile OTP. |
| 8 | P1 | `prompt_8_gst_einvoice_returns.md` | No e-invoice IRN/QR, no e-way bill, no GSTR-1/HSN-summary export. |
| 9 | P2 | `prompt_9_white_label_cleanup.md` | MADIO's name, colours and divisions still show to other companies in fallbacks, receipts, the topbar and PDFs. |
| 10 | P2 | `prompt_10_indian_languages.md` | English-only UI and customer messages; no i18n. |
| 11 | P2 | `prompt_11_dpdp_data_rights.md` | No whole-company export, no offboarding/deletion, no consent or opt-out (DPDP Act 2023). |
| 12 | P2 | `prompt_12_saas_operations.md` | No `tenants.id` index although every request now reads it; no per-tenant rate limits or usage metering; `render.yaml` lacks the new env vars; no error monitoring. |

## Dependencies

- 4 before 5 and 9 (sign-up and white-labelling assume every division works).
- 7's OTP sender can use 6's WhatsApp connection; without 6 it uses SMS.
- 5's mobile verification uses 7's OTP if present, else ships behind
  `PUBLIC_SIGNUP=false`.
- 12's plan-state cache should land before heavy multi-tenant traffic.

## How to use a prompt

Open a new Claude Code session on this repository, paste the prompt file's
contents (or say "Do prompt_4_tenant_divisions_everywhere.md"), and let it
plan → implement → test → commit. Each prompt ends with tests that must pass
together with `python -m pytest tests -q` (backend) and `CI=true npm run
build` (frontend).
