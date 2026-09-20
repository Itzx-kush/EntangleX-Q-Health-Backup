# Vercel deployment

This deployment keeps the existing React/Vite frontend and the existing FastAPI
application. Vercel serves the compiled SPA and routes `/api/*` to
`api/index.py`, which imports `backend.app.main:app`.

## What Vercel can and cannot persist

Vercel function filesystems are ephemeral. A Vercel deployment therefore needs:

- a hosted PostgreSQL-compatible database for the SQLAlchemy registry;
- an S3-compatible object store for CSV datasets, trusted model bundles, and
  optional experiment snapshots.

Local development still uses SQLite and local files when
`QHEALTH_STORAGE_BACKEND=local` and `DATABASE_URL` is unset.

## 1. Push the repository to GitHub

From Windows PowerShell, after reviewing the changes:

```powershell
git status
git add .
git commit -m "Prepare EntangleX Q-Health for Vercel"
git push origin main
```

If you are working from a feature branch, push that branch and select it in the
Vercel project instead.

## 2. Import into Vercel

1. Open the Vercel dashboard and choose **Add New > Project**.
2. Select the GitHub repository `Itzx-kush/EntangleX-Q-Health-Backup`.
3. Set **Root Directory** to `./` (the repository root).
4. The committed `vercel.json` supplies the install command, build command,
   output directory, Python function runtime, and routing. Do not configure a
   separate backend project.
5. Choose **Deploy** only after adding the environment variables below, or add
   them in **Project Settings > Environment Variables** before the first
   production redeploy.

The effective build settings are:

| Setting | Value |
| --- | --- |
| Install command | `npm --prefix frontend ci` |
| Build command | `npm --prefix frontend run build` |
| Output directory | `frontend/dist` |
| Python function | `api/index.py` with runtime `python3.12` |

## 3. Create the persistent services

Create a PostgreSQL-compatible database and copy its connection URL from that
provider. Create a private S3-compatible bucket and an access key limited to
that bucket. Do not commit either value or place them in a `VITE_*` variable.

The application does not create a database or bucket for you. It creates the
SQLAlchemy tables on a cold start and writes objects using the configured
storage credentials.

## 4. Add Vercel environment variables

In **Project Settings > Environment Variables**, add the required values for
**Production** (and Preview if you want preview deployments to use the same
services). See the table in the next section. Redeploy after changing them.

For a Vercel deployment, use:

```text
QHEALTH_STORAGE_BACKEND=s3
QHEALTH_SERVERLESS=true
QHEALTH_TRUSTED_HOSTS=*.vercel.app
```

Add your custom domain to `QHEALTH_TRUSTED_HOSTS` as its hostname if you use
one. Same-origin browser requests do not need a separate API base URL.

## 5. Deploy

1. Return to **Deployments** and choose **Redeploy** (or push a new commit).
2. Open the deployment URL.
3. Check the build logs for both the Vite build and Python Function packaging.
4. The first request may be a cold start while database tables are created.

## 6. Health check and application test

Replace `YOUR-DOMAIN` with the Vercel deployment hostname:

```powershell
$base = "https://YOUR-DOMAIN.vercel.app"
Invoke-RestMethod "$base/api/health"
Invoke-WebRequest "$base/" -UseBasicParsing
Invoke-WebRequest "$base/datasets" -UseBasicParsing
```

The health response must be HTTP 200 and include `status: "ok"`. Then use the
frontend's **Datasets > Load Wisconsin benchmark** flow. The demo dataset is
created by the real backend from scikit-learn's public packaged benchmark; it
is not a static frontend response. Run a bounded classical training job and
confirm that a later request still lists the dataset, experiment, job, and
model.

For a protected deployment, supply the configured bearer token in the
frontend's **Connection settings**. The token is held in memory only.

## 7. Common troubleshooting

- **404 on `/api/health`:** confirm Root Directory is the repository root and
  that the deployment contains `api/index.py` and `vercel.json`. API rewrites
  must precede the SPA fallback.
- **Frontend route refresh returns 404:** confirm the latest `vercel.json` was
  deployed. Its second rewrite sends non-API paths to `index.html`.
- **Database errors:** verify `DATABASE_URL` is present in the deployment
  environment, is reachable from Vercel, and uses a supported PostgreSQL URL.
  Do not use the local SQLite path in production.
- **Upload or model disappears:** verify `QHEALTH_STORAGE_BACKEND=s3` and all
  object-storage variables. Vercel's local filesystem is not durable.
- **Host not trusted:** add the exact custom-domain hostname to
  `QHEALTH_TRUSTED_HOSTS`; keep `*.vercel.app` for Vercel hostnames.
- **401 or 403:** set `QHEALTH_API_TOKEN` only when you intend to require a
  bearer token. For cross-origin callers, add the exact caller origin to
  `QHEALTH_CORS_ORIGINS`.
- **Training times out:** use a small sample budget, at most three CV folds,
  and classical models for the hosted demo. The serverless path executes a
  bounded job inside the request and does not pretend to be an immortal worker.
- **Quantum reports unavailable:** the default Vercel dependency set is
  classical-first. The Qiskit/Aer packages remain optional because their native
  footprint is not a reliable fit for serverless packaging. The capabilities
  endpoint reports the actual installed availability; install and run the
  quantum requirements locally or use a separately sized worker for quantum
  training.

## 8. Local verification before deployment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend
npm ci
npm run typecheck
npm run build
npm test
cd ..
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m pytest backend\tests -m "not quantum"
```

For local development with the full quantum and SHAP features, install
`backend\requirements.txt` instead of the root Vercel requirements. Start the
backend with Uvicorn and the frontend with `npm run dev` as described in the
root README.
