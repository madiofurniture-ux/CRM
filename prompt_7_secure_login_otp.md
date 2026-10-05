# Prompt 7: Login fit for many companies — OTP, own-PIN change, sessions (P1)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.

## Why

Sign-in is username + a 4–6 digit PIN (`backend/auth.py`,
`POST /api/auth/login` in `server.py`, `frontend/src/pages/Login.jsx`). For a
shared SaaS product that is weak and awkward:

- There is no way for a user to **change their own PIN** — only an admin can
  (`PUT /api/auth/users/{id}`), yet the onboarding handover tells customers to
  "change your PIN after the first login".
- New companies get a PIN typed by the platform owner; nothing forces a
  change on first login.
- A JWT stays valid for 7 days (`ACCESS_TOKEN_EXPIRE_DAYS`); removing a user or
  resetting a PIN does not end existing sessions.
- Indian users expect mobile OTP sign-in.

## Goal

Users can sign in with mobile + OTP (WhatsApp or SMS) or username + PIN,
change their own PIN, are made to replace an issued PIN on first login, and
an admin can sign a user out everywhere.

## Scope

1. `PUT /api/auth/me/pin` {current_pin, new_pin}: 4–6 digits, not all the
   same digit, not 1234-style sequences; rate-limited.
2. `must_change_pin` on users created by `tenant_create` and by admins; the
   app routes to a "Set your PIN" screen until it's changed.
3. Session versioning: `token_version` on the user, embedded in the JWT and
   checked in `get_current_user`; bump it on PIN change, PIN reset, user
   deactivation and from an admin "Sign out everywhere" action.
4. Mobile OTP: `POST /api/auth/otp/request` {mobile} and
   `/auth/otp/verify` {mobile, code}. 6-digit code, 5-minute expiry, hashed
   at rest, max 5 attempts, per-mobile and per-IP throttles. Delivery
   through a pluggable sender: WhatsApp (Prompt 6) or an SMS provider via
   env (e.g. MSG91 with a DLT-registered template); a `console` sender for
   development. Mobile must belong to exactly one user; usernames stay
   globally unique.
5. Login page: "Sign in with mobile OTP" alongside the PIN pad; keep the
   existing PIN-length memory and `LOGIN_PROFILE_TILES` behaviour.

## Tests

Own-PIN change succeeds with the right current PIN and invalidates the old
token; wrong current PIN → 400 and counts toward lockout; `must_change_pin`
blocks other writes until set; OTP expiry, attempt limit and replay are
enforced; OTP for an unknown mobile reveals nothing (same response).

## Out of scope

SSO / Google login, 2FA for the platform owner (separate prompt if wanted).
