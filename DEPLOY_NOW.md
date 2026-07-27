# MADIO CRM — 10 Minute Deployment

Everything is prepared. Follow these four steps in order.

**What you are deploying:** FastAPI backend on Render (free) + React frontend on
Netlify (free) + your existing MongoDB Atlas. Total cost: ₹0.

**Before you start, have these two open:**
- MongoDB Atlas connection string (in `backend\.env`, line `MONGO_URL=`)
- Your GitHub login (repo `madiofurniture-ux/CRM`)

---

## Step 0 — Rotate the database password (2 min) ⚠️ DO THIS FIRST

The current Atlas password was shared in chat, so treat it as public.

1. Atlas → **Database Access** → your user → **Edit** → **Edit Password** → Autogenerate → **Update User**
2. Atlas → **Network Access** → confirm it is **not** `0.0.0.0/0`.
   For Render's free tier you *do* need broad access, so if it must stay open,
   that makes Step 0's strong password the only thing protecting your data.
3. Copy the new connection string. You will paste it in Step 2.

---

## Step 1 — Push the code to GitHub (2 min)

From `Documents\CRM`:

```bash
git init
git add backend frontend render.yaml DEPLOY_NOW.md deploy
git commit -m "MADIO CRM production build"
git branch -M production
git remote add origin https://github.com/madiofurniture-ux/CRM.git
git push -u origin production
```

`.gitignore` already excludes `.env`, so your secrets do **not** get pushed.

---

## Step 2 — Deploy the backend on Render (4 min)

1. Go to <https://dashboard.render.com> → **New** → **Blueprint**
2. Connect the `madiofurniture-ux/CRM` repo, branch **production**
3. Render reads `render.yaml` and proposes a service named **madio-crm-api**
4. Fill the two secrets it asks for:

   | Variable | Value |
   |---|---|
   | `MONGO_URL` | your **new** Atlas string from Step 0 |
   | `CORS_ORIGINS` | `*` for now — tighten in Step 4 |

   (`DB_NAME=madio_crm` and a strong random `JWT_SECRET` are set automatically.)
5. **Apply** and wait for the first build (~3 min).
6. Copy the service URL, e.g. `https://madio-crm-api.onrender.com`
7. Check it works — open `<your-url>/api/` in a browser. You should see
   `{"app":"MADIO CRM Backend API","status":"online"}`

> **Free tier note:** the service sleeps after ~15 min idle, so the first
> request each morning takes ~30 s to wake. Everything after that is instant.
> Upgrade to the $7/mo plan if that annoys the team.

---

## Step 3 — Build & deploy the frontend (3 min)

In PowerShell, from `Documents\CRM`, paste your Render URL:

```powershell
.\deploy\build-frontend.ps1 -BackendUrl "https://madio-crm-api.onrender.com"
```

That bakes in the API URL, builds, and refuses to continue if any tracking
script sneaks back in. It prints `BUILD OK` when done.

Then:

1. Go to <https://app.netlify.com/drop>
2. Drag the **`frontend\build`** folder onto the page
3. Netlify gives you a URL, e.g. `https://madio-crm.netlify.app`

`_redirects` is already inside the build, so deep links like `/inventory`
work on refresh.

---

## Step 4 — Lock it down (1 min)

1. **Restrict CORS:** Render → your service → **Environment** → set
   `CORS_ORIGINS` to your exact Netlify URL (e.g. `https://madio-crm.netlify.app`)
   → **Save** (it redeploys itself).
2. **Change every PIN.** The seeded ones are public knowledge:

   | User | Seeded PIN |
   |---|---|
   | admin | 1234 |
   | raghu | 2222 |
   | nenmu | 3333 |
   | gowtham | 4444 |

   Log in as `admin` → **Admin → Role Manager** → change all four.

---

## Done — verify in 60 seconds

- [ ] Log in as admin
- [ ] **Inventory** shows 643 items with product photos
- [ ] **Sales Register** shows 345 records
- [ ] **Projects** opens without error
- [ ] **Admin → Financial Year** lists FY 2026-27 down to 2023-24
- [ ] Open the site on a phone — the D&W survey camera button opens the camera

---

## Custom domain (optional, later)

Netlify → **Domain settings** → **Add custom domain** → `crm.madiofurniture.com`.
In GoDaddy DNS add a **CNAME**: `crm` → `<your-site>.netlify.app`.
SSL is issued automatically once DNS propagates.

---

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Login spins forever | Backend asleep (free tier) | Wait 30 s, retry |
| "Network Error" everywhere | `CORS_ORIGINS` doesn't match the Netlify URL exactly | Fix it in Render env (include `https://`, no trailing slash) |
| Blank page on refresh at `/inventory` | `_redirects` missing | Rebuild with the script — it includes it |
| Data missing after deploy | Backend pointing at the wrong DB | Check `DB_NAME=madio_crm` in Render |
| Frontend calls `undefined/api` | Built without the URL | Re-run Step 3 with `-BackendUrl` |

---

## To redeploy later

- **Backend change:** `git push` → Render rebuilds automatically.
- **Frontend change:** re-run the Step 3 script, drag `build` to Netlify again.
