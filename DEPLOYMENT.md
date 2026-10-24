# Deploy Pagepulse

This project has a Vite frontend and a Flask backend. Deploying `dist` serves the
website; the API also needs an online Python host. The Vite development proxy
only runs locally.

## 1. Host the Flask backend

Use a Python host that keeps a single application process running. PDF export
jobs and generated PDFs currently live in process memory, so multiple workers,
multiple replicas, or serverless restarts can lose job state. The local SQLite
database also needs persistent storage; PostgreSQL avoids that local database
dependency. PostgreSQL does not make PDF jobs durable.

Install dependencies:

```sh
pip install -r requirements.txt
```

Set these environment variables on the **backend host**, using your real
production website origin and database connection:

```dotenv
DEMO_MODE=false
FRONTEND_URL=https://YOUR-WEBSITE.vercel.app
META_REDIRECT_URI=https://YOUR-WEBSITE.vercel.app/api/facebook/callback
COOKIE_SECURE=true
APP_TIMEZONE=Asia/Bangkok
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
META_GRAPH_VERSION=v26.0
META_PERMISSIONS=pages_show_list,pages_read_engagement,read_insights
```

Also set `META_APP_ID`, `META_APP_SECRET`, `SECRET_KEY`, and
`TOKEN_ENCRYPTION_KEY` as private backend environment variables. Generate
persistent production keys once, keep them stable across restarts, and do not
put them in frontend variables or source control:

```sh
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the public port supplied by your host in `PORT`, then use this start command:

```sh
python -m backend.serve
```

The production entry point applies PostgreSQL migrations before serving
traffic, then starts one Waitress process on `0.0.0.0` using `PORT` (8080 by
default). Standard provider database URLs beginning with `postgres://` or
`postgresql://` are mapped to the installed psycopg 3 driver automatically.

For a container host, the included Dockerfile builds the frontend and runs the
same backend entry point. Supply the production environment through your host,
including a persistent PostgreSQL database. Local `.env` files, tokens,
databases, and generated reports are excluded from the Docker build context.

```sh
docker build -t pagepulse .
```

The Flask development command `python index.py` listens only on the local
machine and is not the production start command.

The container can serve both the built website and API from one domain if you
choose a container host for the whole application. When keeping the frontend
on Vercel, use the container's public HTTPS origin as `BACKEND_URL` below.

Check `https://YOUR-BACKEND-HOST/api/health`. It must return JSON with
`"status": "ok"`.

## 2. Deploy the frontend on Vercel

Push `vercel.mjs` together with the application changes to the repository Vercel
deploys. This file sets Vite, `npm ci`, `npm run build`, and the `dist` output.

Set one environment variable on **Vercel** for each deployment environment:

```dotenv
BACKEND_URL=https://YOUR-BACKEND-HOST
```

Use the backend origin without `/api`, query parameters, or credentials. Use a
public HTTPS backend, not localhost and not the Vercel frontend URL.
`BACKEND_URL` is read when Vercel evaluates its project configuration; redeploy
after changing it. A missing or invalid value stops the deployment with an
explanation instead of publishing a frontend with a broken API route.

Requests such as `/api/session`, Facebook callbacks, CSV downloads, and PDF
exports are forwarded to the same path on the backend. Browser requests stay
on the frontend origin so session cookies and CSRF headers remain compatible.

For live Facebook Login, use one stable production domain. Preview domains
need their own matching backend origin configuration and Meta redirect
registration; the backend intentionally accepts a single `FRONTEND_URL`.

## 3. Configure Facebook and verify the deployed website

Register the exact production `META_REDIRECT_URI` in your Meta app's Facebook
Login settings. The app must permit login by the intended Facebook account.
Existing localhost sessions do not transfer to a new production domain.

Verify the production URL in this order:

1. `/api/health` returns JSON with `"status": "ok"`, not an HTML page.
2. `/api/session` returns JSON and sets a secure browser session cookie.
3. Facebook Login returns to the production website and loads authorized Pages.
4. Page analytics, CSV, and a complete PDF export work from the same browser.

If the frontend shows HTML instead of API data, check `BACKEND_URL`, confirm
`vercel.mjs` is in the deployed commit, and redeploy. If the backend health
check fails, inspect the Python host's startup logs, database connectivity,
keys, and migrations.

References:
- https://vercel.com/docs/project-configuration/vercel-ts
- https://vercel.com/docs/routing/rewrites
- https://vercel.com/kb/guide/is-sqlite-supported-in-vercel
