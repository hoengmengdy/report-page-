# Pagepulse · Facebook Page Analytics

A responsive React dashboard with a Flask REST API, official Facebook Login, encrypted server-side Meta tokens, PostgreSQL support, and a ready-to-run SQLite demo.

**The demo works without Meta credentials. Real Facebook analytics have not been verified with a live Meta app or authorized Page.** Live requests require your own app configuration, appropriate permissions and Page tasks, and any applicable Meta review. Entering a public Page URL does not grant Insights access.

## Run on Windows PowerShell

Prerequisites: Python 3.12+ and Node.js 22.12+ (Node 24 recommended), including npm. No PostgreSQL installation is needed for the local demo. These commands do not require activating a virtual environment or changing PowerShell execution policy.

First-time setup:

```powershell
Set-Location "C:\Word\Facebook Page Analytics Dashboard"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Terminal 1 — backend:

```powershell
Set-Location "C:\Word\Facebook Page Analytics Dashboard"
.\.venv\Scripts\python.exe index.py
```

Terminal 2 — frontend:

```powershell
Set-Location "C:\Word\Facebook Page Analytics Dashboard"
npm.cmd run dev
```

Open **http://localhost:5173**. Use this exact hostname consistently: the configured redirect URL and session cookies must use the same host. Vite forwards `/api` to Flask at port 5000. Flask binds to the local machine only. SQLite migrations run automatically on startup; the database and locally generated demo keys live in the ignored `instance/` directory.

Keep both terminals running; press Ctrl+C in each to stop. `npm.cmd` avoids the PowerShell `npm.ps1` execution-policy error.

## What you can use

- Overview, Content, Audience, and Reports views; responsive sidebar and mobile navigation.
- Facebook URL validation, Connect Page, Fetch Data, and refresh with rate-limit cooldown.
- In live mode, the dashboard automatically starts Facebook Login once per browser tab, without requiring a Page URL. Facebook may require sign-in and approval. After approval, it connects the first returned Page with an access token, preferring one with the `ANALYZE` task, and loads its analytics. **Authorized Facebook Pages** automatically loads every available Page batch for that browser session. Choose another Page by name and ID to fill the link field, then click Connect Page. Failed or cancelled login stays visible without repeated redirects; **Connect Facebook** retries manually. Reconnect Facebook refreshes the login without requiring a URL. Saved URLs do not imply authorization. Permission failures do not start a rate-limit cooldown.
- `data/requested_page_names.json` contains the 37 requested Page names. Authorized Pages with matching names appear first; duplicate and unmatched names are listed for review. Names never substitute for authorized Page IDs or establish a match with a saved URL.
- If Meta denies optional reaction/comment counters, posts are retried once without those fields. Accessible posts, shares and views still load; unavailable counters remain empty and the report explains the limitation.
- Last 7/28/90 days and custom inclusive ranges of 1–90 days. Defaults end yesterday. The application's default calendar timezone is Asia/Bangkok, configurable with `APP_TIMEZONE`.
- Daily interactive Recharts performance charts; aligned previous-period comparisons.
- Views, interactions, follower snapshots and follower changes. Unavailable values remain `null` and display as `—`; missing days are never filled with zero.
- Recent posts with loaded-post search, media filters, sorting, cursor pagination, and optional lifetime media views.
- Analytics CSV with daily values, period summaries, comparison values, and metric availability. The frontend's post export includes **all loaded posts**, with lifetime counters. Backend `dataset=posts` exports **one bounded page**, documented in each CSV row.
- Explicit synthetic-data labels on the dashboard and exports. Demo connects always retain the fictional Verdant Studio dataset; they do not fetch analytics for the entered URL.
- A persistent list of the 36 supplied Facebook URLs in `data/tracked_pages.json`, with a searchable **Page connections** view. Missing schemes and the supplied HTTP URL were normalized to HTTPS during import. ID labels and usernames identify saved URLs; they are not verified Page names.
- Facebook connection, permission and metric availability dialogs; loading, empty, partial-data, error, and public-only states.

The engagement donut summarizes available lifetime reactions/comments/shares from loaded posts. It is not the Page's date-limited interaction total. Followers are a stock metric: the dashboard uses the last reporting-day snapshot, never the sum of daily follower counts. Missing comparison data and zero previous totals produce no growth percentage.

## Configure official Meta access

1. Create/configure a Meta developer app supporting Facebook Login and the Pages API. Follow the use-case and login-product setup available for your app in Meta's current App Dashboard.
2. Register the **exact** local Valid OAuth Redirect URI: `http://localhost:5173/api/facebook/callback`. Set the appropriate app domain and website URL. Use HTTPS URLs for production. Use `localhost` everywhere, rather than mixing it with `127.0.0.1` in the browser.
3. Generate persistent backend keys:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. Edit `.env`, placing the first output in `SECRET_KEY`, the second in `TOKEN_ENCRYPTION_KEY`, and your credentials in `META_APP_ID` and `META_APP_SECRET`. Set `DEMO_MODE=false` (or keep `auto`, which selects live mode when both app credentials exist). Leave `META_GRAPH_VERSION=v26.0` unless you have reviewed a newer version. Restart Flask.
5. Enter your Page URL and choose **Connect Page**. The backend redirects to the official Facebook Login dialog requesting exactly `pages_show_list`, `pages_read_engagement`, and `read_insights`. Facebook's baseline public-profile access is part of Login; this app only fetches the user's numeric ID.
6. Grant your app access to the intended Page. The backend exchanges the authorization code, obtains a user token, lists `/me/accounts`, matches the submitted Page identity against authorized Pages, and stores the Page token encrypted. Page Insights require a token obtained by a person who can perform the Page's `ANALYZE` task. Actual permission/field failures are reported clearly.
7. Development-mode access is restricted by Meta to eligible app roles/test users and their authorized resources. To serve other users, complete applicable App Review, Advanced Access, business verification, app-mode, privacy-policy, and data-use requirements in Meta's dashboard. Requested scopes alone are not evidence of approval or access.

If a URL is not among authorized Pages, the backend makes a basic metadata lookup using the official Graph API. It displays public metadata **only if Meta permits the request** (which can require approved public-access features). A public-only connection cannot read private Insights or posts through this integration. If metadata access is denied, a clear permissions error is shown. There is no scraping, cookie collection, password collection, or access-control bypass.

Reconnect through **Settings → Reconnect Facebook** if a token expires, permission is revoked, or the required Page was not selected. An inaccessible new Page never inherits analytics from a different Page.

### Your saved Pages

Open **Page connections** in the sidebar to search all 36 saved URLs. Choose **Use Page**, then **Connect Page**. The list is shared project configuration; connection/active statuses are private to the current browser session. Edit `data/tracked_pages.json` and restart Flask to change the configured list.

Saving or selecting a URL does not start background monitoring. This dashboard fetches one authorized Page at a time when connected/refreshed. In demo mode, selecting one of your real URLs clears sample analytics and disables Fetch Data/exports for that target. Connect Page then explains the required Meta setup. Enter the fictional sample Page URL (`https://www.facebook.com/verdantstudio`) to return to the demo dataset. No sample statistics are assigned to your real Pages, and no live calls were made to verify these Pages' names or Insights.

For an expired connection, use **Settings → Reconnect Facebook** after configuring your Meta app. Private Insights still require appropriate authorization for each selected Page. There is no scheduled polling or cross-Page aggregate report in this version.

Auto-connect reuses the current browser's existing account and selected Page without opening Facebook Login again. If that account has no selected Page, it selects an available authorized Page. Normal login does not force permission re-approval; explicit Reconnect Facebook requests permissions again. An unavailable Facebook app can still block new logins and requires inspection in the Meta App Dashboard. Existing connections are never copied between browser sessions.

## API and metric verification

Verified against Meta's official documentation on **October 23, 2026**:

| Purpose | Official Graph API request | Treatment |
| --- | --- | --- |
| Login | `https://www.facebook.com/v26.0/dialog/oauth` | Server-held, single-use OAuth state; 10-minute expiry |
| Code/token exchange | `/v26.0/oauth/access_token` | Backend only |
| Authorized Pages | `/v26.0/me/accounts` | Page tokens stripped from client responses; cursor pagination |
| Granted permissions | `/v26.0/me/permissions` | Actual granted scopes shown in settings |
| Views | `/{page-id}/insights?metric=page_media_view&period=day` | Sum of returned daily media views |
| Interactions | `/{page-id}/insights?metric=page_post_engagements&period=day` | Sum of daily engagement counts; subject to Meta's metric limitations |
| Followers | `/{page-id}/insights?metric=page_follows&period=day` | Last daily follower snapshot |
| Recent Page posts | `/{page-id}/posts` | Publication-range filtering, field selection, and cursor pagination |
| Post views | `/{post-id}/insights?metric=post_media_view&period=lifetime` | Optional; per-post availability handled independently |
| Earnings | No endpoint called | Unavailable: separate monetization authorization is outside this integration |
| Legacy reach/impressions | No deprecated endpoint/metric requested | Unavailable; media views are not relabeled as reach or impressions |

Sources: [Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog/), [v26 release](https://developers.facebook.com/docs/graph-api/changelog/version26.0/), [Page Insights reference](https://developers.facebook.com/docs/graph-api/reference/page/insights/), [manual Facebook Login flow](https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow/), [Pages API getting started](https://developers.facebook.com/docs/pages-api/getting-started/), [Meta's official SDK version configuration](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/apiconfig.py).

Meta listed v26.0, released July 29, 2026, as the latest Graph API version at verification. API versions and metrics can change; review these references before upgrading. Documentation verification is separate from testing a live authorized request. App/metric availability can vary by Page, permission, eligibility, reporting retention, or API version. Some metrics require sufficient Page size and may update only once per day. Page engagement metrics may exclude certain formats such as Reels, per Meta's reference.

Current and previous periods are requested separately so each request stays within Meta's 90-day limit. The UI labels a daily bucket using its returned `end_time` minus one day, preserving Meta's offset. Meta's reporting boundaries may differ from the user's local day. Live analytics are cached for five minutes per session/Page/range; Refresh bypasses that cache. Posts are fetched fresh. Individual unavailable metrics do not fail the entire report. Expired tokens, network failures, and rate limits are surfaced instead of converted to missing or fake values.

## REST endpoints

| Method | Route | Notes |
| --- | --- | --- |
| GET | `/api/health` | Database connectivity, demo status, Graph version; no credentials |
| GET | `/api/session` | Session state, sanitized Page metadata, CSRF token |
| DELETE | `/api/session` | Delete this browser's stored connection/data; CSRF required |
| GET | `/api/facebook/pages` | Authorized Pages; `after` and `limit` parameters |
| GET | `/api/facebook/watchlist` | Configured URL list and this session's active/public-only status; no external fetches |
| POST | `/api/facebook/connect` | JSON `{ "page_url": "https://www.facebook.com/YourPageName" }`; CSRF required |
| GET | `/api/facebook/callback` | Facebook authorization callback; state validated/consumed |
| GET | `/api/facebook/insights` | `days=7|28|90` or `since=YYYY-MM-DD&until=YYYY-MM-DD`; optional `refresh=1` |
| GET | `/api/facebook/posts` | Same date parameters, optional `after`, `limit=1..100` |
| GET | `/api/facebook/export` | Same range; `dataset=insights` (default) or `posts`, with pagination for posts |
| POST | `/api/facebook/deauthorize` | Meta-signed callback; deletes all sessions for the Meta user |
| POST | `/api/facebook/data-deletion` | Meta-signed deletion callback; returns confirmation code/status URL |
| GET | `/api/deletion-status/{confirmation}` | Validated deletion confirmation; no personal data in URL |

In live mode, data endpoints require the authenticated backend session and its selected Page. Client-provided Page IDs cannot select someone else's data. JSON errors have the form `{ "error": { "code": "permission_denied", "message": "..." } }`. Rate limits return HTTP 429 plus `Retry-After`; the client displays a cooldown. Graph requests have bounded timeouts, cursor cycle detection, and no automatic retry loops. The backend follows returned cursors against fixed Graph endpoints, never token-bearing `paging.next` URLs.

## PostgreSQL and migrations

SQLite is the local default. To use PostgreSQL, create an empty database (example name `pagepulse`) and configure:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/pagepulse
```

URL-encode special characters in the database password. Apply the included Alembic migration before starting Flask against PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m flask --app index db upgrade
```

The same command is safe to repeat. SQLite applies the same migrations automatically. To create future migrations after deliberate model changes, use `flask --app index db migrate -m "description"`, review the generated migration, and run `db upgrade`. PostgreSQL runtime validation was not performed in this environment; SQLAlchemy models and the baseline migration use portable types.

## Build, test, and serve the built app

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

For a single-server local preview of the production build, stop Vite, keep Flask running, and open **http://localhost:5000**. For live Login on this origin, change both `.env` and Meta's registered redirect to match port 5000, and set `FRONTEND_URL=http://localhost:5000`.

For a production WSGI process on Windows, after building:

```powershell
.\.venv\Scripts\waitress-serve.exe --host=127.0.0.1 --port=5000 index:app
```

Serve it behind an HTTPS reverse proxy, configure `FRONTEND_URL` and `META_REDIRECT_URI` for the public origin, and set `COOKIE_SECURE=true`. Use one public origin for frontend and `/api`; broad CORS is intentionally not enabled. Configure the proxy to omit query strings from access logs, particularly OAuth callbacks. `index.py` already omits query strings in local development logs. Do not enable Flask debug mode with live credentials.

Keep `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY` stable and private. Changing the encryption key makes existing stored sessions unreadable; perform a deliberate token/session revocation and key-rotation procedure. Keep `.env`, `instance/`, logs, and database backups private. Only the backend reads credentials; there are no `VITE_` credentials or browser-stored Meta tokens.

For multiple workers/instances, use PostgreSQL and a shared rate-limit store:

```powershell
.\.venv\Scripts\python.exe -m pip install "Flask-Limiter[redis]>=4,<5"
```

Then set `RATELIMIT_STORAGE_URI` to your Redis URI. The default `memory://` limits are per process. Rate limiting uses the actual connected address; behind a proxy, configure trusted forwarding deliberately in your deployment rather than trusting arbitrary incoming forwarding headers.

Schedule this cleanup **at least hourly**, using Windows Task Scheduler with this project as the working directory:

```powershell
.\.venv\Scripts\python.exe -m flask --app index prune-sessions
```

Sessions and encrypted tokens expire after eight hours and are rejected/removed on access. Cleanup removes abandoned expired sessions. The Meta deauthorization and data-deletion callbacks remove all sessions tied to the signed Meta user ID. The in-app privacy notice describes implementation behavior; the deployment operator must publish an appropriate privacy policy, contact details, and any required retention disclosures, then register the HTTPS deauthorization and data-deletion URLs in Meta's App Dashboard. No legal policy is implied by the demo notice.

## Verification and limitations

- **86 backend tests pass**, covering URL/parameter validation, Graph authentication/permission/rate/network errors, safe transport, OAuth state/replay checks, demo labeling, encrypted tokens, public-only access, report math, pagination, cache refresh, CSV injection protection, session expiration, disconnection, signed data deletion, fresh/repeated SQLite migration startup, and watchlist integrity/session isolation.
- The React/TypeScript production build and HTTP smoke checks for the frontend, API proxy, local images, and CSV download have been run.
- **8 frontend component tests pass**, covering demo labeling, CSRF connect requests, navigation/filtering, stale-pagination races, revoked authorization with a concurrent successful request, unavailable engagement counters, saved-Page search/selection, and separation of real targets from demo statistics. Chart components are mocked in these tests; they do not substitute for visual browser QA.
- End-to-end HTTP smoke checks pass for demo connection, all three preset reporting ranges, post pagination, CSV downloads, built JavaScript/CSS assets, security headers, and actual HTTP rate-limit/Retry-After behavior. Dependency checks report no npm vulnerabilities or broken Python requirements.
- No browser automation surface was available in this session. Desktop/mobile visual rendering and browser interactions remain unverified. Responsive layout rules and accessible labels/focus management are included.
- No live Meta credentials were supplied; real Facebook Login, Page matching, and Insights/Post requests require integration testing with your approved app and Page.
- PostgreSQL requires a running PostgreSQL service and was not exercised here. SQLite was exercised locally.
- Monetization/earnings are deliberately unavailable. Legacy reach/impressions are not requested. Unsupported data is not estimated.

## Project layout

```text
index.py                  Flask entry point / WSGI app
backend/__init__.py        REST routes, OAuth, sessions, deletion and CSV
backend/meta.py            Official Graph API transport and error translation
backend/analytics.py       Metric normalization and explicitly synthetic demo data
backend/models.py          Encrypted database session model
backend/validation.py      URL, range, cursor and limit validation
backend/watchlist.py       Saved URL validation and per-session connection status
data/tracked_pages.json    The 36 supplied Page URLs, normalized to HTTPS
src/                      React + TypeScript dashboard and styles
public/assets/             Local demo imagery and profile illustration
migrations/               Alembic database migration
tests/                    Pytest unit and API tests
.env.example              Backend configuration template
```

Demo thumbnails are downloaded from [Unsplash](https://unsplash.com) and bundled locally; they are illustrative assets, not actual Facebook post media. Photo IDs: `photo-1416879595882-3373a0480b5b`, `photo-1459411621453-7b03977f4bfc`, `photo-1484154218962-a197022b5858`, `photo-1485955900006-10f4d324d411`, `photo-1501004318641-b39e6451bec6`. The Pagepulse mark and botanical avatar are project SVG assets. All demo post copy and analytics are fictional.
#   r e p o r t - p a g e -  
 