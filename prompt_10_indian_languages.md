# Prompt 10: Indian languages for staff and customer messages (P2)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

The whole UI is English-only — there is no i18n library or message catalogue
in `frontend/` (no i18next/react-intl). Showroom staff, site supervisors and
field teams across India often work better in Hindi, Telugu, Tamil, Kannada
or Marathi, and customers expect WhatsApp messages in their language.

## Goal

A user picks their language; the app's chrome and the most-used screens
render in it; customer-facing messages (WhatsApp templates, quote cover
text) can be sent in the customer's preferred language.

## Scope (phase 1)

1. Add `react-i18next` with lazy-loaded JSON catalogues under
   `frontend/src/locales/<lang>/`. Languages: en (source), hi, te, ta, kn, mr.
2. Translate the shell (sidebar, topbar, `SubscriptionBanner`), Login,
   Business Setup, Leads, Follow-ups, Tasks, Attendance and the shared
   components (`EmptyState`, `ErrorState`, buttons). Leave admin/finance
   screens in English for phase 1 and say so in the docs.
3. User preference `language` on the user record (default from the company's
   `default_language`, then `en`), editable from the user menu; the server
   never translates data, only UI strings.
4. Numbers and dates stay Indian format (`en-IN` / `hi-IN` locale for
   `Intl`), ₹ grouping unchanged (`lib/format.js`).
5. Customer `preferred_language` on leads/customers; notification and Flows
   templates (`backend/notifications.py`, `backend/flows.py`) gain per-language
   bodies with English fallback.
6. Fonts: Noto Sans for Devanagari, Telugu, Tamil, Kannada loaded only when that
   language is active.
7. A CI check that every key in `en` exists in each catalogue (missing keys
   fall back to English at runtime, but the check lists them).

## Tests

Frontend build passes; a unit test that switching to `hi` renders the
translated sidebar labels; backend test that a notification for a customer
with `preferred_language: "te"` uses the Telugu body and falls back to English
when absent.

## Out of scope

Translating user-entered data, right-to-left scripts, Urdu.
