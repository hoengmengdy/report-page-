"""Official Graph transport. Never follow paging.next URLs containing tokens."""
import hashlib
import hmac
import logging
import re
import requests
from .validation import APIError

logger = logging.getLogger(__name__)
RATE_CODES = {4, 17, 32, 613, 80001, 80004}


class MetaClient:
    def __init__(self, app):
        self.version = app.config["META_GRAPH_VERSION"]
        self.secret = app.config["META_APP_SECRET"]
        self.app_id = app.config["META_APP_ID"]
        self.http = requests.Session()

    def get(self, path, token=None, **params):
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path) or any(s in (".", "..") for s in path.split("/")):
            raise APIError("Invalid Graph resource.")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            params["appsecret_proof"] = hmac.new(self.secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        try:
            response = self.http.get(f"https://graph.facebook.com/{self.version}/{path}",
                                     headers=headers, params=params, timeout=(5, 30), allow_redirects=False)
        except requests.RequestException:
            logger.warning("Meta network request failed for resource %s", path.split("/")[-1])
            raise APIError("Meta could not be reached. Please try again shortly.", 503, "meta_unavailable")
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError()
        except ValueError:
            raise APIError("Meta returned an unreadable response. Try again shortly.", 502, "meta_response")
        error = body.get("error")
        if error or response.status_code >= 400:
            error = error or {}
            code = error.get("code")
            logger.warning("Meta API error: code=%s status=%s", code, response.status_code)
            if code in RATE_CODES or response.status_code == 429:
                retry = response.headers.get("Retry-After", "60")
                retry = min(max(int(retry), 1), 3600) if retry.isdigit() else 60
                raise APIError("Meta's rate limit was reached. Wait before refreshing.", 429, "rate_limited", retry)
            if code == 190 or response.status_code == 401:
                raise APIError("Your Facebook authorization expired or was revoked. Reconnect your Page.", 401, "reauthorize")
            if code in (10, 200, 294) or response.status_code == 403:
                raise APIError("Meta did not grant access. Check Page tasks, granted permissions, and App Review.", 403, "permission_denied")
            if code in (100, 3001):
                raise APIError("This field or metric is unavailable for this Page and API version.", 422, "metric_unavailable")
            raise APIError("Meta could not complete this request. Please try again later.", 502, "meta_error")
        if not 200 <= response.status_code < 300:
            raise APIError("Unexpected response from Meta.", 502, "meta_response")
        return body

    def exchange_code(self, code, redirect_uri):
        short = self.get("oauth/access_token", client_id=self.app_id,
                         client_secret=self.secret, redirect_uri=redirect_uri, code=code)
        token = short.get("access_token")
        if not token:
            raise APIError("Facebook Login returned no access token.", 502, "oauth_failed")
        result = self.get("oauth/access_token", grant_type="fb_exchange_token",
                          client_id=self.app_id, client_secret=self.secret, fb_exchange_token=token)
        if not result.get("access_token"):
            raise APIError("Facebook token exchange failed.", 502, "oauth_failed")
        return result["access_token"]

    @staticmethod
    def next_cursor(body):
        paging = body.get("paging", {})
        return paging.get("cursors", {}).get("after") if paging.get("next") else None

    def accounts(self, token):
        pages, after, seen = [], None, set()
        for _ in range(20):
            params = {"fields": "id,name,link,picture,access_token,tasks", "limit": 100}
            if after:
                params["after"] = after
            body = self.get("me/accounts", token, **params)
            pages.extend(body.get("data", []))
            after = self.next_cursor(body)
            if not after:
                return pages
            if after in seen:
                break
            seen.add(after)
        raise APIError("Too many Pages to match safely. Reduce Page access in Facebook Login and reconnect.", 422, "pagination_limit")
