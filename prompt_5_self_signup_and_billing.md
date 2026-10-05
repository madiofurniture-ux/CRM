# Prompt 5: Self-serve sign-up and subscription billing (Razorpay) (P1)

Work in this repository (`madiofurniture-ux/CRM`). Read `CLAUDE.md` first and
follow its core rules and working rules. Plan first, list the multi-module
impact before editing, then implement, test and commit in small steps.
Do Prompt 4 first.

## Why

Today only the platform owner can create a company (Platform → Customers,
`POST /api/tenants`, owner-only in `backend/server.py` `tenant_create`). Plans
exist (`backend/plans.py`: trial, starter, growth, business, enterprise with
seat limits) but **no prices are stored and nothing takes payment**; when a
trial ends the company is read-only until the owner changes its plan by hand.
To sell to Indian SMBs the product needs a public sign-up and online payment
in rupees with GST invoices for the subscription itself.

## Goal

A business owner can sign up on the web, get a 14-day trial set up for their
industry, and later pay for a plan with UPI / card / netbanking through
Razorpay. Paying moves the company to the paid plan automatically; failed or
lapsed payments follow a clear grace-period rule.

## Scope

1. **Public sign-up** — `POST /api/signup` (unauthenticated, rate-limited like
   `/auth/login`): business name, owner name, mobile (validated with
   `india.normalize_mobile`), email, industry pack, chosen username and PIN.
   Creates the tenant + first admin exactly as `tenant_create` does (reuse
   it — extract the shared part, don't duplicate), plan `trial`. Mobile
   verification by OTP if Prompt 7 has landed; otherwise behind an env flag
   `PUBLIC_SIGNUP=true` (default off). Frontend: `/signup` page in the
   login page's style (`frontend/src/pages/Login.jsx`), linked from login.
2. **Prices as configuration** — add `price_inr_month` / `price_inr_year` per
   plan, overridable by env/DB, shown on a plan picker (Business Setup →
   "Plan & billing"). Prices are **exclusive of 18% GST**; show both.
3. **Razorpay Subscriptions** — backend module `backend/billing.py`:
   create a Razorpay customer + subscription for the tenant, return the
   checkout parameters, verify the webhook signature
   (`X-Razorpay-Signature`, HMAC-SHA256 with the webhook secret) and on
   `subscription.charged` set `plan`, `paid_until`; on `payment.failed` /
   `subscription.halted` start a 7-day grace period, after which
   `plans.state` treats the company like an ended trial (read-only).
   Keys only from env (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
   `RAZORPAY_WEBHOOK_SECRET`); no live call in tests — mock the client.
4. **Subscription invoices** — each charge produces a GST tax invoice from
   the platform owner to the customer (owner's GSTIN from the owner's office
   settings; customer's GSTIN from their company profile; IGST vs CGST+SGST
   via `india.is_interstate`; amount in words via `india.amount_in_words`),
   downloadable from "Plan & billing".
5. **Platform console** (`frontend/src/pages/Platform.jsx`) shows paid-until,
   last payment and MRR per company.
6. New collections (`subscriptions`, `subscription_invoices`) are tenant data:
   add them to `tenancy.TENANT_COLLECTIONS`; webhook writes stamp the tenant
   resolved from the Razorpay subscription id, never from the payload's
   claims alone.

## Tests

Signup creates an isolated tenant with the pack applied; duplicate username
→ 400; webhook with a bad signature → 401 and no change; a charged event
moves trial → growth and extends `paid_until`; grace period expiry makes
writes return 402; invoice tax split correct for same-state and
other-state customers.

## Out of scope

Coupons, proration between plans mid-cycle, refunds UI.
