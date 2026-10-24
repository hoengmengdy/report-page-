"""Metric normalization and deterministic, explicitly synthetic demo data."""
import math
from datetime import datetime, timedelta, timezone

from .validation import APIError

METRICS = {"views": "page_media_view", "interactions": "page_post_engagements", "followers": "page_follows"}
UNAVAILABLE = {
    "earnings": "Earnings require separately authorized monetization access and are not provided by this integration.",
    "reach": "Legacy reach metrics are deprecated. Unique media viewers are a different metric and are not relabeled as reach.",
    "impressions": "Legacy impressions metrics are deprecated. Media views are shown separately.",
}
DEMO_PAGE = {"id": "demo-verdant", "name": "Verdant Studio", "url": "https://www.facebook.com/verdantstudio",
             "picture": "/assets/verdant.svg", "category": "Home & garden · Sample Page"}


def days_between(since, until):
    return [since + timedelta(days=i) for i in range((until-since).days+1)]


def demo_daily(day):
    n = day.toordinal()
    wave = 1 + .31 * math.sin(n * .72) + .17 * math.cos(n * 1.43)
    trend = 1 + .0015 * (n - 739900)
    views = round((7100 + (n % 7)*385) * wave * trend)
    return {"views": max(0, views), "interactions": max(0, round(views * (.048 + .009*math.sin(n)))),
            "followers": max(0, 12486 + (n-739911)*23 + round(11*math.sin(n)))}


def metric_summary(current, previous, key, reason=None):
    vals = [d.get(key) for d in current]
    prev = [d.get(key) for d in previous]
    available = [v for v in vals if v is not None]
    complete = len(available) == len(vals)
    previous_complete = all(v is not None for v in prev)
    if key == "followers":
        # Stock metric: use the end-of-period value, never the sum of snapshots.
        value = vals[-1] if vals else None
        old = prev[-1] if prev else None
        complete = value is not None
        previous_complete = old is not None
    else:
        value = sum(available) if available else None
        old = sum(prev) if previous_complete else None
    growth = round((value-old)/old*100, 1) if complete and previous_complete and old and value is not None else None
    delta = value-old if complete and previous_complete and value is not None and old is not None else None
    return {"value": value, "previous": old, "growth": growth, "delta": delta,
            "status": "available" if complete else "partial" if available else "unavailable",
            "reason": reason or (None if complete else "Meta did not return every reporting day. Missing days are not treated as zero."),
            "source_metric": METRICS[key]}


def make_report(since, until, current, previous, reasons=None, demo=False):
    reasons = reasons or {}
    series = [{"date": row["date"], **{k: row.get(k) for k in METRICS},
               **{f"previous_{k}": previous[i].get(k) for k in METRICS},
               "previous_date": previous[i]["date"]} for i, row in enumerate(current)]
    summaries = {k: metric_summary(current, previous, k, reasons.get(k)) for k in METRICS}
    summaries.update({k: {"value": None, "previous": None, "growth": None, "delta": None,
                          "status": "unavailable", "reason": v, "source_metric": None} for k,v in UNAVAILABLE.items()})
    return {"demo": demo, "since": str(since), "until": str(until),
            "previous_since": previous[0]["date"], "previous_until": previous[-1]["date"],
            "metrics": summaries, "series": series,
            "reporting_note": "Synthetic sample data." if demo else "Daily buckets follow Meta's reporting boundaries. end_time labels the end of each bucket. Recent data may be delayed by 24–48 hours.",
            "fetched_at": datetime.now(timezone.utc).isoformat()}


def demo_insights(since, until):
    count = (until-since).days+1
    current = [{"date": str(d), **demo_daily(d)} for d in days_between(since, until)]
    previous = [{"date": str(d), **demo_daily(d)} for d in days_between(since-timedelta(days=count), since-timedelta(days=1))]
    return make_report(since, until, current, previous, demo=True)


def graph_metrics(client, page, metrics, since, until):
    values, after, seen = {metric: {} for metric in metrics}, None, set()
    for _ in range(20):
        params = {"metric": ",".join(metrics), "period": "day", "since": str(since),
                  "until": str(until+timedelta(days=1)), "limit": 100}
        if after:
            params["after"] = after
        body = client.get(f"{page['id']}/insights", page["access_token"], **params)
        for result in body.get("data", []):
            if result.get("name") not in values:
                continue
            for entry in result.get("values", []):
                value = entry.get("value")
                if isinstance(value, (int, float)) and not isinstance(value, bool) and entry.get("end_time"):
                    try:
                        # Keep Meta's offset, rather than shifting reporting days into browser time.
                        bucket = (datetime.fromisoformat(entry["end_time"].replace("Z", "+00:00"))-timedelta(days=1)).date()
                    except ValueError:
                        continue
                    if since <= bucket <= until:
                        values[result["name"]][str(bucket)] = value
        after = client.next_cursor(body)
        if not after:
            return values
        if after in seen:
            break
        seen.add(after)
    raise APIError("Insights pagination exceeded the safe limit. Try a shorter date range.", 422, "pagination_limit")


def graph_daily(client, page, metric, since, until):
    return graph_metrics(client, page, [metric], since, until)[metric]


def live_insights(client, page, since, until):
    count = (until-since).days+1
    current = [{"date": str(d)} for d in days_between(since, until)]
    previous = [{"date": str(d)} for d in days_between(since-timedelta(days=count), since-timedelta(days=1))]
    reasons = {}
    for key, metric in METRICS.items():
        # Separate ranges keep every Insights request inside Meta's 90-day limit.
        for rows in (current, previous):
            start = datetime.fromisoformat(rows[0]["date"]).date()
            end = datetime.fromisoformat(rows[-1]["date"]).date()
            try:
                data = graph_daily(client, page, metric, start, end)
                for row in rows:
                    row[key] = data.get(row["date"])
            except APIError as exc:
                if exc.code not in ("metric_unavailable", "permission_denied"):
                    raise
                reasons[key] = exc.message
                for row in rows:
                    row[key] = None
    return make_report(since, until, current, previous, reasons)


def live_insights_combined(client, page, since, until):
    """Two multi-metric requests for bulk PDFs; fall back to per-metric availability."""
    count = (until-since).days+1
    current = [{"date": str(day)} for day in days_between(since, until)]
    previous = [{"date": str(day)} for day in days_between(since-timedelta(days=count), since-timedelta(days=1))]
    try:
        for rows in (current, previous):
            data = graph_metrics(client, page, list(METRICS.values()), date_from_row(rows[0]), date_from_row(rows[-1]))
            for row in rows:
                row.update({key: data[metric].get(row["date"]) for key, metric in METRICS.items()})
    except APIError as exc:
        if exc.code not in ("metric_unavailable", "permission_denied"):
            raise
        return live_insights(client, page, since, until)
    return make_report(since, until, current, previous)


def date_from_row(row):
    return datetime.fromisoformat(row["date"]).date()


POST_TEMPLATES = [
    ("A little green goes a long way. Meet your new favorite corner. 🌿", "Photo", "plant-room", 1248, 86, 124),
    ("Your 60-second guide to happier houseplants. Save this for watering day.", "Video", "plant-care", 986, 72, 208),
    ("Slow mornings, soft light, and a space that feels like you.", "Photo", "interior", 864, 54, 92),
    ("The studio edit: five pieces that bring the outside in.", "Photo", "shelf", 728, 43, 76),
    ("What's growing in your space? Show us your favorite plant in the comments. 💚", "Text", "leaves", 642, 138, 48),
    ("Behind the scenes at Verdant: a little care in every detail.", "Video", "plant-room", 592, 38, 64),
    ("A new leaf, a fresh start. Our weekend mood.", "Photo", "leaves", 527, 29, 42),
    ("Three simple ways to style your shelves with greenery.", "Video", "shelf", 488, 36, 89),
    ("Made for the spaces in between. Discover our studio favorites.", "Photo", "interior", 426, 21, 34),
    ("Good things take a little growing. Here's your midweek reminder.", "Text", "plant-care", 362, 18, 27),
    ("Morning light in the studio. There's no place we'd rather be.", "Photo", "plant-room", 318, 24, 31),
    ("Let's make room for something green this week.", "Video", "leaves", 287, 17, 23),
]


def demo_posts(since, until, after=None, limit=6):
    try:
        offset = int(after or "0")
        if offset < 0 or offset > len(POST_TEMPLATES):
            raise ValueError()
    except ValueError:
        raise APIError("Invalid demo pagination cursor.")
    days = (until-since).days+1
    posts = []
    for i, (text, kind, image, reactions, comments, shares) in enumerate(POST_TEMPLATES):
        day = until-timedelta(days=min(days-1, i*max(1, days//12)))
        posts.append({"id": f"demo-{i}", "text": text, "type": kind, "picture": f"/assets/{image}.jpg",
                      "published_at": f"{day}T09:30:00+00:00", "reactions": reactions,
                      "comments": comments, "shares": shares, "views": reactions*17+i*369,
                      "url": None, "views_reason": "Synthetic lifetime sample views."})
    return {"demo": True, "posts": posts[offset:offset+limit],
            "next_cursor": str(offset+limit) if offset+limit < len(posts) else None,
            "count": len(posts), "counts_note": "Sample lifetime post counts; publication dates are inside the selected range."}


def live_posts(client, page, since, until, after=None, limit=6):
    basic_fields = "id,message,created_time,permalink_url,full_picture,attachments{media_type},shares"
    params = {"fields": basic_fields + ",reactions.limit(0).summary(true),comments.limit(0).summary(true)",
              "since": str(since), "until": str(until+timedelta(days=1)), "limit": limit}
    if after:
        params["after"] = after
    counters_denied = False
    try:
        body = client.get(f"{page['id']}/posts", page["access_token"], **params)
    except APIError as exc:
        if exc.code != "permission_denied":
            raise
        # Optional user-content counters can require more access than Page posts.
        # Retry only the smaller, authorized field set; a second denial propagates.
        params["fields"] = basic_fields
        body = client.get(f"{page['id']}/posts", page["access_token"], **params)
        counters_denied = True
    posts = []
    for post in body.get("data", []):
        attachments = post.get("attachments", {}).get("data", [])
        media_type = attachments[0].get("media_type", "") if attachments else ""
        views, reason = None, "Meta did not return lifetime media views for this post."
        try:
            result = client.get(f"{post['id']}/insights", page["access_token"], metric="post_media_view", period="lifetime")
            for item in result.get("data", []):
                if item.get("name") == "post_media_view":
                    vals = item.get("values", [])
                    raw = vals[-1].get("value") if vals else item.get("total_value", {}).get("value")
                    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                        views, reason = raw, None
        except APIError as exc:
            if exc.code not in ("metric_unavailable", "permission_denied"):
                raise
            reason = exc.message
        posts.append({"id": post["id"], "text": post.get("message", "Untitled post"),
                      "published_at": post.get("created_time"), "url": post.get("permalink_url"),
                      "picture": post.get("full_picture"),
                      "type": "Video" if media_type == "video" else "Photo" if media_type == "photo" else "Text",
                      "reactions": post.get("reactions", {}).get("summary", {}).get("total_count"),
                      "comments": post.get("comments", {}).get("summary", {}).get("total_count"),
                      "shares": post.get("shares", {}).get("count"), "views": views, "views_reason": reason})
    note = "Post counts are lifetime totals for posts published in the selected range, not activity limited to that range."
    if counters_denied:
        note += " Reaction and comment counters were not authorized and remain unavailable."
    return {"demo": False, "posts": posts, "next_cursor": client.next_cursor(body), "count": None,
            "counts_note": note}
