import re
import os
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo


class APIError(Exception):
    def __init__(self, message, status=400, code="invalid_request", retry_after=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code
        self.retry_after = retry_after


def parse_page_url(value):
    """Parse identities only. Never fetch user-supplied URLs or follow redirects."""
    if not isinstance(value, str) or len(value) > 2048:
        raise APIError("Enter a valid Facebook Page URL.")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname not in
                {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment):
            raise ValueError()
    except ValueError:
        raise APIError("Use an HTTPS URL on facebook.com, such as https://www.facebook.com/YourPageName.")
    path = unquote(parsed.path).strip("/")
    parts = path.split("/")
    query = parse_qs(parsed.query)
    if path == "profile.php":
        ids = query.get("id", [])
        if len(ids) != 1 or not re.fullmatch(r"\d{5,30}", ids[0]):
            raise APIError("The profile.php URL must contain one valid numeric Page id.")
        identity = ids[0]
    elif len(parts) == 3 and parts[0].lower() == "pages" and re.fullmatch(r"\d{5,30}", parts[2]):
        identity = parts[2]
    elif len(parts) == 1 and re.fullmatch(r"[A-Za-z0-9.\-]{2,100}", path):
        identity = path
        if identity in (".", ".."):
            raise APIError("Enter a valid Page username.")
        if identity.lower() in {"login", "login.php", "sharer.php", "share", "watch", "reel", "reels", "groups", "events", "marketplace", "help", "settings", "gaming", "messages", "photo.php", "story.php", "home.php", "pages", "people"}:
            raise APIError("Enter the Page's own URL, rather than a post, group, or Facebook utility URL.")
    else:
        raise APIError("Enter a Page username URL or a profile.php?id=PAGE_ID URL.")
    return {"identity": identity.lower(), "url": (
        f"https://www.facebook.com/profile.php?id={identity}" if identity.isdigit()
        else f"https://www.facebook.com/{identity}")}


def date_range(args):
    try:
        today = datetime.now(ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Bangkok"))).date()
        days = int(args.get("days", "28"))
        if days not in (7, 28, 90):
            raise ValueError()
        if bool(args.get("since")) != bool(args.get("until")):
            raise ValueError()
        until = date.fromisoformat(args["until"]) if args.get("until") else today - timedelta(days=1)
        since = date.fromisoformat(args["since"]) if args.get("since") else until - timedelta(days=days-1)
        if since > until or (until-since).days >= 90 or until > today or since < today-timedelta(days=640):
            raise ValueError()
    except (ValueError, TypeError):
        raise APIError("Choose a valid range of 1–90 days within the last 640 days, ending no later than today.")
    return since, until


def cursor_arg(args):
    after = args.get("after")
    if after and (len(after) > 2048 or not re.fullmatch(r"[A-Za-z0-9_\-=+/]+", after)):
        raise APIError("Invalid pagination cursor.")
    return after


def page_size(args):
    try:
        limit = int(args.get("limit", 6))
        if not 1 <= limit <= 100:
            raise ValueError()
        return limit
    except (ValueError, TypeError):
        raise APIError("Page size must be between 1 and 100.")
