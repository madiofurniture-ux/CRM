# MADIO CRM (React + FastAPI + MongoDB) — near-zero-cost production deploy

Three layers, each on a free (or already-paid) host. Target cost: **≈₹0/month** for a small team.

```
Frontend (static React)  →  Hostinger (already paid)   e.g. crm.madiofurniture.com
Backend  (FastAPI)       →  Render free  OR  Cloud Run  e.g. api.madiofurniture.com
Database (MongoDB)       →  MongoDB Atlas M0 (free forever)
```

Deploy order: **Database → Backend → Frontend** (each needs the previous one's URL).

---

## 1. Database — MongoDB Atlas M0 (free)

1. mongodb.com/atlas → create a free **M0** cluster.
2. **Database Access** → add a user + password.
3. **Network Access** → allow the backend host. For Render/Cloud Run (dynamic IPs) use `0.0.0.0/0`
   — access is still gated by the user/password in the connection string.
4. **Connect → Drivers** → copy the string:
   `mongodb+srv://USER:PASS@cluster.xxxx.mongodb.net/`
   Keep it secret; it is a backend env var, never in the frontend.

The backend **auto-seeds** sample data (4 users, inventory, sales, etc.) the first time each
collection is empty, so the app is usable immediately after the first boot.

---

## 2. Backend — pick ONE

Both read these env vars: `MONGO_URL`, `DB_NAME` (=`madio_crm`), `JWT_SECRET` (any long random
string), `CORS_ORIGINS` (the frontend origin, e.g. `https://crm.madiofurniture.com`).

### Option A — Render (simplest, no credit card)
1. Push this repo to GitHub (already on `conflict_220726_0734`).
2. Render → **New → Blueprint** → pick the repo. It reads [`render.yaml`](render.yaml) and creates
   the `madio-crm-api` free web service (`JWT_SECRET` is auto-generated).
3. In the service's **Environment**, set `MONGO_URL` and `CORS_ORIGINS`.
4. Deploy → note the URL, e.g. `https://madio-crm-api.onrender.com`. Verify `…/api/` returns
   `{"status":"ok"}`.
   *Trade-off:* the free plan sleeps after 15 min idle → first request ~50s. Fine for internal use.

### Option B — Google Cloud Run (scales to zero, faster cold start)
Uses [`backend/Dockerfile`](backend/Dockerfile). Needs a GCP project with billing enabled (the free
tier — 2M req/mo — still costs ₹0 for this workload). With the `gcloud` CLI, from `backend/`:
```bash
gcloud run deploy madio-crm-api --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars DB_NAME=madio_crm,JWT_SECRET=<long-random>,CORS_ORIGINS=https://crm.madiofurniture.com \
  --set-env-vars MONGO_URL='mongodb+srv://USER:PASS@cluster.xxxx.mongodb.net/'
```
Note the `https://…run.app` URL it prints.

---

## 3. Frontend — Hostinger (already paid)

Build against the backend URL, then upload the static files.

1. On your machine, in `frontend/`, create `.env.production`:
   ```
   REACT_APP_BACKEND_URL=https://madio-crm-api.onrender.com
   ```
   (or your Cloud Run URL). Then `npm install && npm run build`.
2. In Hostinger **hPanel → File Manager**, upload the **contents** of `frontend/build/` into
   `public_html/` (or a subdomain's folder). Include the `.htaccess` (it's in the build output and
   makes deep links like `/quotes/ws/<id>` work on refresh).
3. Point your domain/subdomain at that folder in hPanel.
4. Back in the backend, make sure `CORS_ORIGINS` exactly matches this origin (scheme + host, no
   trailing slash), then redeploy the backend.

*(Netlify/Cloudflare Pages free tier also work — a `_redirects` file for the same SPA fallback is
included. Cloudflare Pages is a good pick if you'd rather not touch Hostinger.)*

---

## Security before you share the URL

The backend is a real auth server now (bcrypt-hashed PINs + 7-day JWT), a genuine upgrade over the
single-file app's public hardcoded key. Still, before go-live:
- **Change every seeded PIN** (admin/1234, raghu/2222, …) via **Role Manager**.
- Set a strong, unique `JWT_SECRET` (Render's `generateValue` does this; set one yourself on Cloud Run).
- Keep `MONGO_URL` and `JWT_SECRET` only in the backend host's env — never in the repo or frontend.
- Scope `CORS_ORIGINS` to your real frontend origin, not `*`.

## Cost summary

| Layer | Host | Ongoing cost |
|---|---|---|
| Database | Atlas M0 | ₹0 forever (512 MB) |
| Backend | Render free / Cloud Run free tier | ₹0 (cold-start trade-off on Render) |
| Frontend | Hostinger (already owned) | ₹0 marginal |

If the Render cold start ever annoys the team, the cheapest always-on upgrades are Render Starter
(~$7/mo) or a Hostinger VPS (~$5/mo) running the Docker image — but start free.
