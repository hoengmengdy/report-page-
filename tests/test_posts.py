from datetime import date
from unittest.mock import Mock

import pytest

from backend.analytics import live_posts
from backend.validation import APIError


PAGE = {"id": "12345", "access_token": "PAGE_TOKEN"}


def test_posts_survive_denied_optional_counters_without_inventing_counts():
    client = Mock()
    client.get.side_effect = [APIError("User-content counters denied", 403, "permission_denied"),
        {"data": [{"id": "12345_1", "message": "A real Page post", "shares": {"count": 20}}]},
        {"data": [{"name": "post_media_view", "values": [{"value": 6008}]}]}]
    client.next_cursor.return_value = "next-posts"
    result = live_posts(client, PAGE, date(2026, 10, 16), date(2026, 10, 22), after="previous-posts", limit=1)
    assert result["posts"][0]["text"] == "A real Page post"
    assert result["posts"][0]["reactions"] is None
    assert result["posts"][0]["comments"] is None
    assert result["posts"][0]["shares"] == 20
    assert result["posts"][0]["views"] == 6008
    assert result["next_cursor"] == "next-posts"
    assert "not authorized" in result["counts_note"]
    first, fallback = client.get.call_args_list[:2]
    assert "reactions" in first.kwargs["fields"] and "comments" in first.kwargs["fields"]
    assert "reactions" not in fallback.kwargs["fields"] and "comments" not in fallback.kwargs["fields"]
    assert fallback.kwargs["after"] == "previous-posts" and fallback.kwargs["limit"] == 1
    assert first.args == fallback.args == ("12345/posts", "PAGE_TOKEN")


@pytest.mark.parametrize("code,status", [("reauthorize", 401), ("rate_limited", 429), ("meta_unavailable", 503)])
def test_posts_do_not_retry_authorization_expiry_rate_limits_or_network_failures(code, status):
    client = Mock()
    client.get.side_effect = APIError("Request failed", status, code)
    with pytest.raises(APIError) as caught:
        live_posts(client, PAGE, date(2026, 10, 16), date(2026, 10, 22))
    assert caught.value.code == code
    assert client.get.call_count == 1


def test_posts_do_not_hide_a_denied_basic_posts_request():
    client = Mock()
    client.get.side_effect = APIError("Posts denied", 403, "permission_denied")
    with pytest.raises(APIError) as caught:
        live_posts(client, PAGE, date(2026, 10, 16), date(2026, 10, 22))
    assert caught.value.code == "permission_denied"
    assert client.get.call_count == 2
