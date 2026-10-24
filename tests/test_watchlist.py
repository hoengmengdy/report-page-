import json
from unittest.mock import Mock

import pytest

from backend.models import BrowserSession, db
from backend.watchlist import load_requested_names, load_watchlist, watchlist_rows


def test_all_submitted_urls_are_saved_and_no_meta_requests_are_made(app, client):
    app.extensions["meta"].get = Mock()
    response = client.get("/api/facebook/watchlist")
    assert response.status_code == 200
    body = response.json
    assert body["count"] == 36
    assert len({page["identity"] for page in body["pages"]}) == 36
    assert body["pages"][0]["identity"] == "61580719959744"
    assert body["pages"][-1]["url"] == "https://www.facebook.com/profile.php?id=61588859777323"
    assert {p["identity"] for p in body["pages"] if not p["identity"].isdigit()} == {"komsantv1629", "acejusmin4luv"}
    assert all(page["url"].startswith("https://www.facebook.com/") for page in body["pages"])
    assert all(page["status"] == "not_connected" for page in body["pages"])
    assert all("metrics" not in page and "access_token" not in page for page in body["pages"])
    app.extensions["meta"].get.assert_not_called()


def test_selected_page_status_is_private_to_the_authenticated_session(live_app, auth_client):
    with live_app.app_context():
        record = db.session.execute(db.select(BrowserSession)).scalar_one()
        payload = record.read()
        payload["selected_page"]["id"] = "61580719959744"
        record.write(payload)
        db.session.commit()
    response = auth_client.get("/api/facebook/watchlist")
    assert response.json["pages"][0]["status"] == "active"
    assert "SECRET" not in response.text
    anonymous = live_app.test_client().get("/api/facebook/watchlist")
    assert all(row["status"] == "not_connected" for row in anonymous.json["pages"])


def test_public_metadata_does_not_mark_an_insights_connection_active():
    rows = watchlist_rows([{"identity":"123456", "url":"https://facebook.com/profile.php?id=123456", "label":"Page 123456"}],
                          {"id":"123456"}, public_only=True)
    assert rows[0]["status"] == "public_only"


def test_config_rejects_untrusted_hosts_and_deduplicates_canonical_identity(tmp_path):
    config = tmp_path / "pages.json"
    config.write_text(json.dumps(["https://facebook.com/MyPage", "https://www.facebook.com/mypage/"]))
    assert len(load_watchlist(config)) == 1
    config.write_text(json.dumps(["https://facebook.com.evil.test/AnyPage"]))
    with pytest.raises(RuntimeError): load_watchlist(config)


def test_watchlist_usernames_match_an_authorized_page_link():
    rows = watchlist_rows([{"identity":"komsantv1629", "url":"https://facebook.com/komsantv1629", "label":"@komsantv1629"}],
                          {"id":"123456", "link":"https://www.facebook.com/KomsanTV1629/"})
    assert rows[0]["status"] == "active"


def test_requested_names_remain_names_without_assuming_url_or_page_identity(tmp_path):
    config = tmp_path / "names.json"
    assert load_requested_names(config) == []
    config.write_text(json.dumps([" Komsan Today ", "Komsan Today", "កម្សាន្ត អារម្មណ៍"], ensure_ascii=False), encoding="utf-8")
    assert load_requested_names(config) == ["Komsan Today", "កម្សាន្ត អារម្មណ៍"]
    config.write_text(json.dumps([{"name": "Komsan Today"}]))
    with pytest.raises(RuntimeError):
        load_requested_names(config)
