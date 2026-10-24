import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import click
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate, upgrade
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from .analytics import DEMO_PAGE, METRICS, demo_insights, demo_posts, live_insights, live_posts
from .meta import MetaClient
from .models import BrowserSession, db
from .pdf_jobs import PDFExports
from .validation import APIError, cursor_arg, date_range, page_size, parse_page_url
from .watchlist import load_requested_names, load_watchlist, watchlist_rows

ROOT = Path(__file__).resolve().parent.parent


def public_page(page):
    return {"id": page["id"], "name": page.get("name", "Facebook Page"),
            "url": page.get("link") or page.get("url") or f"https://www.facebook.com/profile.php?id={page['id']}",
            "picture": page.get("picture", {}).get("data", {}).get("url") if isinstance(page.get("picture"), dict) else page.get("picture"),
            "category": page.get("category", "Facebook Page")}


def match_page(identity, pages):
    for page in pages:
        if identity == str(page["id"]).lower():
            return page
        try:
            if page.get("link") and identity == parse_page_url(page["link"])["identity"]:
                return page
        except APIError:
            continue
    return None


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def create_app(test_config=None):
    load_dotenv(ROOT / ".env")
    app = Flask(__name__, instance_path=str(ROOT / "instance"), static_folder=None)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        TOKEN_ENCRYPTION_KEY=os.getenv("TOKEN_ENCRYPTION_KEY"),
        META_APP_ID=os.getenv("META_APP_ID", ""),
        META_APP_SECRET=os.getenv("META_APP_SECRET", ""),
        META_GRAPH_VERSION=os.getenv("META_GRAPH_VERSION", "v26.0"),
        META_REDIRECT_URI=os.getenv("META_REDIRECT_URI", "http://localhost:5173/api/facebook/callback"),
        META_PERMISSIONS=os.getenv("META_PERMISSIONS", "pages_show_list,pages_read_engagement,read_insights"),
        FRONTEND_URL=os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/"),
        DEMO_MODE=os.getenv("DEMO_MODE", "auto"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///pagepulse.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=16384,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_HEADERS_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)
    mode = str(app.config["DEMO_MODE"]).lower()
    if mode not in ("auto", "true", "false"):
        raise RuntimeError("DEMO_MODE must be auto, true, or false.")
    configured = bool(app.config["META_APP_ID"] and app.config["META_APP_SECRET"])
    app.config["IS_DEMO"] = mode == "true" or (mode == "auto" and not configured)
    if mode == "auto" and bool(app.config["META_APP_ID"]) != bool(app.config["META_APP_SECRET"]):
        raise RuntimeError("Provide both META_APP_ID and META_APP_SECRET, or clear both for demo mode.")
    if not re.fullmatch(r"v\d+\.\d+", app.config["META_GRAPH_VERSION"]):
        raise RuntimeError("META_GRAPH_VERSION must be an explicit version, such as v26.0.")
    permissions = set(app.config["META_PERMISSIONS"].split(","))
    if permissions != {"pages_show_list", "pages_read_engagement", "read_insights"}:
        raise RuntimeError("META_PERMISSIONS must contain exactly pages_show_list,pages_read_engagement,read_insights.")
    Path(app.instance_path).mkdir(exist_ok=True)
    if app.config["IS_DEMO"]:
        keys_path = Path(app.instance_path) / "demo-keys.json"
        if not keys_path.exists():
            keys_path.write_text(json.dumps({"secret": secrets.token_hex(32), "cipher": Fernet.generate_key().decode()}))
        keys = json.loads(keys_path.read_text())
        app.config["SECRET_KEY"] = app.config["SECRET_KEY"] or keys["secret"]
        app.config["TOKEN_ENCRYPTION_KEY"] = app.config["TOKEN_ENCRYPTION_KEY"] or keys["cipher"]
    elif not configured or not app.config["SECRET_KEY"] or not app.config["TOKEN_ENCRYPTION_KEY"]:
        raise RuntimeError("Live mode requires META_APP_ID, META_APP_SECRET, SECRET_KEY, and TOKEN_ENCRYPTION_KEY in .env.")
    if len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters.")
    app.extensions["token_cipher"] = Fernet(app.config["TOKEN_ENCRYPTION_KEY"].encode())
    db.init_app(app)
    Migrate(app, db, directory=str(ROOT / "migrations"))
    limiter = Limiter(get_remote_address, app=app, default_limits=["120 per minute"],
                      enabled=not app.config.get("TESTING", False))
    # Retain the extension even when disabled in tests (route decorators use weak references).
    app.extensions["pagepulse_limiter"] = limiter
    app.extensions["meta"] = MetaClient(app)
    app.extensions["tracked_pages"] = load_watchlist(ROOT / "data" / "tracked_pages.json")
    app.extensions["requested_page_names"] = load_requested_names(ROOT / "data" / "requested_page_names.json")
    app.extensions["pdf_exports"] = PDFExports(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        with app.app_context():
            if app.config.get("TESTING"):
                db.create_all()
            else:
                upgrade(directory=str(ROOT / "migrations"))

    def browser(create=False):
        sid = session.get("sid")
        record = db.session.get(BrowserSession, sid) if sid else None
        if record and record.expired:
            app.extensions["pdf_exports"].forget(record.id)
            db.session.delete(record)
            db.session.commit()
            session.clear()
            record = None
        if record is None and create:
            session["sid"] = secrets.token_urlsafe(32)
            session.permanent = True
            record = BrowserSession(id=session["sid"], expires_at=datetime.now(timezone.utc)+timedelta(hours=8))
            record.write({})
            db.session.add(record)
            db.session.commit()
        return record

    def authorized():
        record = browser()
        if record is None or not record.read().get("user_token"):
            raise APIError("Connect your Facebook account to access authorized Page data.", 401, "login_required")
        return record, record.read()

    def selected():
        record, payload = authorized()
        page = payload.get("selected_page")
        if not page:
            raise APIError("Connect a Page before fetching analytics.", 409, "page_required")
        if payload.get("public_only"):
            raise APIError("Only public Page metadata is available. Private Insights require Page access and read_insights permission.", 403, "public_only")
        return record, payload, page

    def save(record, payload):
        record.write(payload)
        db.session.commit()

    def activate_page(record, payload, page):
        if not page.get("access_token"):
            raise APIError("Meta returned no Page access token. Reconnect and grant access to the Page.", 403, "permission_denied")
        payload.update(selected_page=page, public_only=False, cache={})
        save(record, payload)
        return {"page": public_page(page), "public_only": False, "message": "Page connected. Metrics remain subject to Meta permissions and availability."}

    def auto_connect_page(record, payload):
        page = payload.get("selected_page")
        if page and page.get("access_token") and not payload.get("public_only"):
            return {"page": public_page(page), "public_only": False,
                    "message": "Your existing Facebook Page connection is ready."}
        pages = app.extensions["meta"].accounts(payload["user_token"])
        candidates = [page for page in pages if page.get("access_token")]
        if not candidates:
            raise APIError("Facebook returned no Pages with access tokens. Reconnect Facebook and grant access to the Pages you manage.", 403, "page_not_accessible")
        page = next((page for page in candidates if "ANALYZE" in page.get("tasks", [])), candidates[0])
        return activate_page(record, payload, page)

    def connect_live(record, payload, target):
        client = app.extensions["meta"]
        pages = client.accounts(payload["user_token"])
        page = match_page(target["identity"], pages)
        metadata = None
        if not page:
            # A lookup is permitted only if Meta itself authorizes it. No scraping.
            try:
                metadata = client.get(target["identity"], payload["user_token"], fields="id,name,link,picture,category")
                page = match_page(str(metadata.get("id", "")), pages)
            except APIError as exc:
                if exc.code not in ("metric_unavailable", "permission_denied"):
                    raise
        if not page:
            if metadata and metadata.get("id"):
                payload.update(selected_page=metadata, public_only=True, cache={})
                save(record, payload)
                return {"page": public_page(metadata), "public_only": True,
                        "message": "Meta permitted public metadata only. This account cannot access this Page's private Insights."}
            raise APIError(f"Facebook returned {len(pages)} authorized Pages, but this URL is not among them. Choose from Authorized Facebook Pages, or use Reconnect Facebook to grant access to this Page. Your Facebook account must also have access to the Page.", 403, "page_not_accessible")
        return activate_page(record, payload, page)

    @app.before_request
    def csrf_guard():
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path not in (
                "/api/facebook/deauthorize", "/api/facebook/data-deletion"):
            expected = session.get("csrf")
            actual = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected, actual):
                raise APIError("Your session needs refreshing. Reload this page and try again.", 403, "csrf_failed")
            origin = request.headers.get("Origin")
            if origin and origin != app.config["FRONTEND_URL"]:
                raise APIError("Request origin is not allowed.", 403, "origin_denied")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(APIError)
    def api_error(exc):
        if exc.code == "reauthorize":
            record = browser()
            if record:
                app.extensions["pdf_exports"].forget(record.id)
                db.session.delete(record)
                db.session.commit()
        response = jsonify(error={"message": exc.message, "code": exc.code})
        response.status_code = exc.status
        if exc.retry_after:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.errorhandler(HTTPException)
    def http_error(exc):
        response = jsonify(error={"message": "Too many requests. Wait before trying again." if exc.code == 429 else exc.description,
                                  "code": "rate_limited" if exc.code == 429 else "http_error"})
        response.status_code = exc.code
        if exc.code == 429:
            response.headers["Retry-After"] = "60"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        db.session.rollback()
        # Type only: SQL and network exception messages may contain sensitive values.
        app.logger.error("Unhandled backend error: %s", type(exc).__name__)
        return jsonify(error={"message": "The server could not complete this request.", "code": "server_error"}), 500

    @app.get("/api/health")
    @limiter.exempt
    def health():
        db.session.execute(db.select(db.literal(1)))
        return jsonify(status="ok", demo=app.config["IS_DEMO"], graph_version=app.config["META_GRAPH_VERSION"])

    @app.get("/api/session")
    def get_session():
        record = browser()
        payload = record.read() if record else {}
        session.setdefault("csrf", secrets.token_urlsafe(32))
        page = DEMO_PAGE if app.config["IS_DEMO"] else (public_page(payload["selected_page"]) if payload.get("selected_page") else None)
        error = payload.pop("login_error", None)
        if error and record:
            save(record, payload)
        return jsonify(demo=app.config["IS_DEMO"], authenticated=bool(payload.get("user_token")),
                       page=page, public_only=payload.get("public_only", False), csrf_token=session["csrf"],
                       permissions=payload.get("permissions", []), graph_version=app.config["META_GRAPH_VERSION"], login_error=error)

    @app.delete("/api/session")
    def disconnect():
        record = browser()
        if record:
            app.extensions["pdf_exports"].forget(record.id)
            db.session.delete(record)
            db.session.commit()
        session.clear()
        return jsonify(message="This browser's stored connection and cached analytics have been deleted.")

    @app.get("/api/facebook/watchlist")
    def watchlist():
        record = browser()
        payload = record.read() if record and not app.config["IS_DEMO"] else {}
        selected_page = payload.get("selected_page") if payload.get("user_token") else None
        rows = watchlist_rows(app.extensions["tracked_pages"], selected_page, payload.get("public_only", False))
        return jsonify(pages=rows, count=len(rows), demo=app.config["IS_DEMO"],
                       note="Saved URLs for manual Page tracking. No background monitoring or automatic analytics collection is running.")

    @app.get("/api/facebook/pages")
    @limiter.limit("20 per minute")
    def pages():
        if app.config["IS_DEMO"]:
            return jsonify(demo=True, pages=[DEMO_PAGE], next_cursor=None)
        _, payload = authorized()
        params = {"fields": "id,name,link,picture,tasks", "limit": page_size(request.args)}
        if cursor_arg(request.args):
            params["after"] = cursor_arg(request.args)
        result = app.extensions["meta"].get("me/accounts", payload["user_token"], **params)
        return jsonify(demo=False, pages=[public_page(p) for p in result.get("data", [])], requested_names=app.extensions["requested_page_names"],
                       next_cursor=MetaClient.next_cursor(result))

    @app.post("/api/facebook/connect")
    @limiter.limit("10 per minute")
    def connect():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise APIError("Send a JSON object containing page_url.")
        account_only = data.get("account_only") is True
        target = None if account_only else parse_page_url(data.get("page_url"))
        if app.config["IS_DEMO"]:
            return jsonify(demo=True, page=DEMO_PAGE, public_only=False,
                           message="Demo mode uses the fictional Verdant Studio Page. No data was fetched from the submitted URL.")
        record = browser(create=True)
        payload = record.read()
        if payload.get("user_token") and not data.get("reauthorize"):
            if not account_only:
                return jsonify(demo=False, **connect_live(record, payload, target))
            if data.get("auto_connect") is True:
                return jsonify(demo=False, authenticated=True, **auto_connect_page(record, payload))
            return jsonify(demo=False, authenticated=True, message="Your Facebook account is already connected.")
        state = secrets.token_urlsafe(32)
        payload.update(oauth_state=hashlib.sha256(state.encode()).hexdigest(), oauth_started=time.time(),
                       pending_url=target["url"] if target else None, oauth_account_only=account_only,
                       oauth_auto_connect=account_only and data.get("auto_connect") is True)
        save(record, payload)
        params = {"client_id": app.config["META_APP_ID"], "redirect_uri": app.config["META_REDIRECT_URI"],
                  "state": state, "response_type": "code", "scope": app.config["META_PERMISSIONS"]}
        if data.get("reauthorize"):
            params["auth_type"] = "rerequest"
        return jsonify(authorization_url=f"https://www.facebook.com/{app.config['META_GRAPH_VERSION']}/dialog/oauth?{urlencode(params)}")

    @app.get("/api/facebook/callback")
    @limiter.limit("15 per minute")
    def callback():
        record = browser()
        if not record:
            raise APIError("Facebook Login session expired. Start again from Connect Page.", 400, "oauth_state")
        payload = record.read()
        state = hashlib.sha256(request.args.get("state", "").encode()).hexdigest()
        expected = payload.pop("oauth_state", "")
        started = payload.pop("oauth_started", 0)
        target = payload.pop("pending_url", None)
        account_only = payload.pop("oauth_account_only", False)
        auto_connect = payload.pop("oauth_auto_connect", False)
        # Consume the state before any network call to prevent replay.
        save(record, payload)
        if not expected or not hmac.compare_digest(expected, state) or time.time()-started > 600 or (not target and not account_only):
            raise APIError("Facebook Login security check failed or expired. Start Connect Page again.", 400, "oauth_state")
        try:
            if request.args.get("error") or not request.args.get("code"):
                raise APIError("Facebook Login was cancelled or permission was declined.", 403, "oauth_declined")
            client = app.extensions["meta"]
            token = client.exchange_code(request.args["code"], app.config["META_REDIRECT_URI"])
            user = client.get("me", token, fields="id")
            grants = client.get("me/permissions", token)
            payload = {"user_token": token, "permissions": [p["permission"] for p in grants.get("data", []) if p.get("status") == "granted"]}
            record.meta_user_id = str(user["id"])
            # Rotate the opaque session ID after successful authentication.
            record.id = secrets.token_urlsafe(32)
            session["sid"] = record.id
            session["csrf"] = secrets.token_urlsafe(32)
            save(record, payload)
            if account_only and auto_connect:
                auto_connect_page(record, payload)
            elif not account_only:
                connect_live(record, payload, parse_page_url(target))
        except APIError as exc:
            payload["login_error"] = exc.message
            save(record, payload)
            return redirect(app.config["FRONTEND_URL"] + "/?auth=error")
        return redirect(app.config["FRONTEND_URL"] + ("/?auth=authorized" if account_only and not auto_connect else "/?auth=connected"))

    def report(since, until):
        if app.config["IS_DEMO"]:
            return demo_insights(since, until)
        record, payload, page = selected()
        key = f"{page['id']}:{since}:{until}"
        cache = payload.get("cache", {})
        cached = cache.get(key)
        if request.args.get("refresh") != "1" and cached and time.time()-cached["time"] < 300:
            return cached["data"]
        result = live_insights(app.extensions["meta"], page, since, until)
        cache = {k: v for k,v in cache.items() if time.time()-v["time"] < 300}
        cache[key] = {"time": time.time(), "data": result}
        payload["cache"] = dict(list(cache.items())[-5:])
        save(record, payload)
        return result

    def post_data(since, until, after=None, limit=6):
        if app.config["IS_DEMO"]:
            return demo_posts(since, until, after, limit)
        _, _, page = selected()
        return live_posts(app.extensions["meta"], page, since, until, after, limit)

    @app.get("/api/facebook/insights")
    @limiter.limit("20 per minute")
    def insights():
        return jsonify(report(*date_range(request.args)))

    @app.get("/api/facebook/posts")
    @limiter.limit("30 per minute")
    def posts():
        return jsonify(post_data(*date_range(request.args), cursor_arg(request.args), page_size(request.args)))

    @app.get("/api/facebook/export")
    @limiter.limit("5 per minute")
    def export():
        since, until = date_range(request.args)
        kind = request.args.get("dataset", "insights")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        demo = app.config["IS_DEMO"]
        if kind == "insights":
            result = report(since, until)
            writer.writerow(["source", "record_type", "date", "metric", "value", "status", "previous_value", "growth_percent", "note"])
            for metric, item in result["metrics"].items():
                writer.writerow(["SAMPLE DATA" if demo else "Meta Graph API", "summary", f"{since} to {until}", item["source_metric"] or metric,
                                 item["value"], item["status"], item["previous"], item["growth"], item["reason"]])
            for row in result["series"]:
                for metric in METRICS:
                    writer.writerow(["SAMPLE DATA" if demo else "Meta Graph API", "daily", row["date"], METRICS[metric], row[metric],
                                     "unavailable" if row[metric] is None else "available", row[f"previous_{metric}"], "", result["reporting_note"]])
            truncated = False
        elif kind == "posts":
            writer.writerow(["source", "post_id", "published_at", "text", "reactions_lifetime", "comments_lifetime", "shares_lifetime", "views_lifetime", "url", "note"])
            # Deliberately export one bounded page per request, with explicit scope.
            data = post_data(since, until, cursor_arg(request.args), min(page_size(request.args), 100))
            for post in data["posts"]:
                writer.writerow([csv_cell(v) for v in ["SAMPLE DATA" if demo else "Meta Graph API", post["id"], post["published_at"], post["text"],
                                 post["reactions"], post["comments"], post["shares"], post["views"], post["url"], "This export contains the current post page. " + data["counts_note"]]])
            truncated = bool(data["next_cursor"])
        else:
            raise APIError("dataset must be insights or posts.")
        response = Response("\ufeff"+output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="pagepulse-{kind}-{since}-{until}{"-sample" if demo else ""}.csv"'
        response.headers["X-Export-More-Posts"] = str(truncated).lower()
        return response

    def pdf_owner(create=False):
        if not app.config["IS_DEMO"]:
            return authorized()
        record = browser(create=create)
        if record is None:
            raise APIError("Start a PDF export from this browser first.", 401, "login_required")
        return record, record.read()

    @app.post("/api/facebook/export/jobs")
    @limiter.limit("3 per minute")
    def start_pdf_export():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise APIError("Send the reporting date range as a JSON object.")
        since, until = date_range(data)
        record, payload = pdf_owner(create=True)
        job = app.extensions["pdf_exports"].start(record.id, payload.get("user_token"), since, until,
            demo=app.config["IS_DEMO"], cache=payload.get("cache", {}))
        return jsonify(job), 202

    @app.get("/api/facebook/export/jobs/<job_id>")
    @limiter.limit("90 per minute")
    def pdf_export_status(job_id):
        record, _ = pdf_owner()
        return jsonify(app.extensions["pdf_exports"].get(job_id, record.id))

    @app.delete("/api/facebook/export/jobs/<job_id>")
    def cancel_pdf_export(job_id):
        record, _ = pdf_owner()
        return jsonify(app.extensions["pdf_exports"].cancel(job_id, record.id))

    @app.get("/api/facebook/export/jobs/<job_id>/file")
    def download_pdf_export(job_id):
        record, _ = pdf_owner()
        data, filename = app.extensions["pdf_exports"].get(job_id, record.id, download=True)
        response = Response(data, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def signed_user():
        if app.config["IS_DEMO"]:
            raise APIError("Meta callbacks are disabled in demo mode.", 400)
        try:
            signature, encoded = request.form["signed_request"].split(".", 1)
            decode = lambda s: base64.urlsafe_b64decode(s + "="*((4-len(s)%4)%4))
            expected = hmac.new(app.config["META_APP_SECRET"].encode(), encoded.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(decode(signature), expected):
                raise ValueError()
            body = json.loads(decode(encoded))
            if body.get("algorithm", "").upper() != "HMAC-SHA256" or not re.fullmatch(r"\d{1,64}", str(body.get("user_id", ""))):
                raise ValueError()
            return str(body["user_id"])
        except (ValueError, KeyError, TypeError):
            raise APIError("Invalid signed Meta request.", 403, "invalid_signature")

    @app.post("/api/facebook/deauthorize")
    @app.post("/api/facebook/data-deletion")
    def data_deletion():
        user_id = signed_user()
        for record in db.session.execute(db.select(BrowserSession).where(BrowserSession.meta_user_id == user_id)).scalars():
            app.extensions["pdf_exports"].forget(record.id)
        db.session.execute(db.delete(BrowserSession).where(BrowserSession.meta_user_id == user_id))
        db.session.commit()
        confirmation = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="deletion").dumps({"deleted": True, "nonce": secrets.token_hex(8)})
        return jsonify(url=app.config["FRONTEND_URL"]+"/?deletion="+confirmation, confirmation_code=confirmation)

    @app.get("/api/deletion-status/<confirmation>")
    def deletion_status(confirmation):
        try:
            body = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="deletion").loads(confirmation)
            if not body.get("deleted"):
                raise BadSignature("Invalid status")
        except BadSignature:
            raise APIError("Unknown deletion confirmation.", 404)
        return jsonify(status="complete", message="Stored connections and cached analytics associated with this Meta user were deleted.")

    @app.cli.command("prune-sessions")
    def prune_sessions():
        """Delete expired sessions and their tokens. Schedule this at least hourly."""
        result = db.session.execute(db.delete(BrowserSession).where(BrowserSession.expires_at < datetime.now(timezone.utc)))
        db.session.commit()
        click.echo(f"Deleted {result.rowcount} expired sessions.")

    @app.get("/")
    @app.get("/<path:path>")
    @limiter.exempt
    def frontend(path=""):
        if path.startswith("api/"):
            raise APIError("API endpoint not found.", 404)
        dist = ROOT / "dist"
        candidate = (dist / path).resolve()
        if candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return send_from_directory(dist, path)
        if (dist / "index.html").exists():
            return send_from_directory(dist, "index.html")
        return jsonify(message="API is running. Start the frontend with npm run dev, or build it with npm run build.")

    return app
