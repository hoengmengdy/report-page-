"""Operator-configured Page URLs, without fetching or inferring Page analytics."""
import json
from pathlib import Path

from .validation import APIError, parse_page_url


def load_requested_names(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        names = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(names, list) or len(names) > 500 or any(
                not isinstance(name, str) or not name.strip() or len(name) > 200 for name in names):
            raise ValueError()
        return list(dict.fromkeys(name.strip() for name in names))
    except (OSError, ValueError) as exc:
        raise RuntimeError("The requested Page names must be a JSON list of non-empty names.") from exc


def load_watchlist(path):
    try:
        urls = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(urls, list) or len(urls) > 500:
            raise ValueError("Expected at most 500 Page URLs.")
        pages, seen = [], set()
        for url in urls:
            target = parse_page_url(url)
            if target["identity"] in seen:
                continue
            seen.add(target["identity"])
            pages.append({**target, "label": (
                f"Page {target['identity']}" if target["identity"].isdigit() else f"@{target['identity']}")})
        return pages
    except (OSError, ValueError, APIError) as exc:
        raise RuntimeError("The tracked Pages configuration must be a JSON list of valid HTTPS Facebook Page URLs.") from exc


def watchlist_rows(pages, selected_page=None, public_only=False):
    identities = set()
    if selected_page:
        identities.add(str(selected_page["id"]).lower())
        for key in ("link", "url"):
            if selected_page.get(key):
                try:
                    identities.add(parse_page_url(selected_page[key])["identity"])
                except APIError:
                    pass
    return [{**page, "status": (
        "public_only" if public_only else "active") if page["identity"] in identities else "not_connected"}
        for page in pages]
