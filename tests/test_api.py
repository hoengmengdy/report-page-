import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from backend import csv_cell
from backend.analytics import graph_daily, metric_summary
from backend.models import BrowserSession, db
from backend.validation import APIError
from conftest import csrf


def test_demo_end_to_end(client):
    state = client.get("/api/session").json
    assert state["demo"] and not state["authenticated"]
    result = client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/SomeOtherPage"}, headers=csrf(client))
    assert result.status_code == 200
    assert result.json["page"]["name"] == "Verdant Studio"
    assert "No data was fetched" in result.json["message"]
    report = client.get("/api/facebook/insights?days=7").json
    assert report["demo"] and len(report["series"]) == 7
    assert report["metrics"]["views"]["value"] == sum(row["views"] for row in report["series"])
    assert report["metrics"]["followers"]["value"] == report["series"][-1]["followers"]
    for key in ("earnings","reach","impressions"):
        assert report["metrics"][key]["value"] is None
    first = client.get("/api/facebook/posts?days=7&limit=6").json
    second = client.get(f"/api/facebook/posts?days=7&limit=6&after={first['next_cursor']}").json
    assert len(first["posts"])+len(second["posts"]) == first["count"]
    assert not set(p["id"] for p in first["posts"]) & set(p["id"] for p in second["posts"])
    export = client.get("/api/facebook/export?days=7")
    assert export.status_code == 200 and export.mimetype == "text/csv"
    assert "SAMPLE DATA" in export.text and "sample" in export.headers["Content-Disposition"]
    assert export.headers["Cache-Control"] == "no-store"


def test_csrf_and_origin_validation(client):
    assert client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/Test"}).status_code == 403
    headers = {**csrf(client), "Origin":"https://evil.test"}
    assert client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/Test"}, headers=headers).status_code == 403
    assert client.post("/api/facebook/connect", json=[], headers=csrf(client)).status_code == 400


@pytest.mark.parametrize("route", ["/api/facebook/pages", "/api/facebook/insights", "/api/facebook/posts", "/api/facebook/export"])
def test_live_data_requires_authentication(live_app, route):
    assert live_app.test_client().get(route).status_code == 401


def test_tokens_never_exposed_and_encrypted(live_app, auth_client):
    result = auth_client.get("/api/session")
    assert "SECRET_" not in result.text
    assert "access_token" not in result.text
    with live_app.app_context():
        record = db.session.execute(db.select(BrowserSession)).scalar_one()
        assert "SECRET_" not in record.encrypted_payload
        assert record.read()["selected_page"]["access_token"] == "SECRET_PAGE_TOKEN"


def test_authorized_page_picker_response_strips_tokens_and_preserves_pagination(live_app, auth_client):
    meta = live_app.extensions["meta"]
    meta.get = Mock(return_value={"data": [{"id": "67890", "name": "Authorized Page",
        "access_token": "SECRET_PAGE_TOKEN", "tasks": ["ANALYZE"]}],
        "paging": {"next": "https://graph.facebook.com/next?access_token=SECRET_USER_TOKEN",
                   "cursors": {"after": "next-cursor"}}})
    result = auth_client.get("/api/facebook/pages?limit=100&after=previous-cursor")
    assert result.status_code == 200
    assert result.json["pages"][0]["url"] == "https://www.facebook.com/profile.php?id=67890"
    assert result.json["next_cursor"] == "next-cursor"
    assert "SECRET_" not in result.text and "access_token" not in result.text
    meta.get.assert_called_once_with("me/accounts", "SECRET_USER_TOKEN",
        fields="id,name,link,picture,tasks", limit=100, after="previous-cursor")


def test_permissions_do_not_turn_into_zero_values(live_app, auth_client):
    live_app.extensions["meta"].get = Mock(side_effect=APIError("Permission denied",403,"permission_denied"))
    result = auth_client.get("/api/facebook/insights?days=7")
    assert result.status_code == 200
    assert all(row["views"] is None for row in result.json["series"])
    assert result.json["metrics"]["views"]["value"] is None
    assert result.json["metrics"]["views"]["status"] == "unavailable"


def test_rate_error_propagates_with_retry_after(live_app, auth_client):
    live_app.extensions["meta"].get = Mock(side_effect=APIError("Wait before retrying",429,"rate_limited",25))
    result = auth_client.get("/api/facebook/insights")
    assert result.status_code == 429
    assert result.headers["Retry-After"] == "25"
    assert result.json["error"]["code"] == "rate_limited"


def test_revoked_token_removes_stored_credentials(live_app, auth_client):
    live_app.extensions["meta"].get = Mock(side_effect=APIError("Reconnect Facebook",401,"reauthorize"))
    result = auth_client.get("/api/facebook/posts")
    assert result.status_code == 401
    with live_app.app_context():
        assert db.session.execute(db.select(BrowserSession)).scalars().all() == []
    assert not auth_client.get('/api/session').json['authenticated']


def test_meta_end_time_bucket_is_labeled_correctly():
    client = Mock()
    client.get.return_value = {"data":[{"name":"page_media_view", "values":[{"end_time":"2026-10-02T07:00:00+0000", "value":42}]}]}
    client.next_cursor.return_value = None
    rows = graph_daily(client, {"id":"1234","access_token":"SECRET"}, "page_media_view", date(2026,10,1),date(2026,10,1))
    assert rows == {"2026-10-01":42}


def test_missing_days_disable_comparison_instead_of_inventing_growth():
    result = metric_summary([{"views":10},{"views":None}], [{"views":5},{"views":5}], "views")
    assert result["value"] == 10 and result["status"] == "partial" and result["growth"] is None
    result = metric_summary([{"followers":100},{"followers":110}], [{"followers":90},{"followers":100}], "followers")
    assert result["value"] == 110 and result["growth"] == 10 and result["delta"] == 10


def test_insights_caching_and_90_day_request_boundaries(live_app, auth_client):
    fake = Mock(return_value={"data":[]})
    live_app.extensions["meta"].get = fake
    assert auth_client.get("/api/facebook/insights?days=90").status_code == 200
    assert fake.call_count == 6
    for call in fake.call_args_list:
        assert (date.fromisoformat(call.kwargs["until"])-date.fromisoformat(call.kwargs["since"])).days == 90
    auth_client.get("/api/facebook/insights?days=90")
    assert fake.call_count == 6
    auth_client.get("/api/facebook/insights?days=90&refresh=1")
    assert fake.call_count == 12


def test_inaccessible_page_never_gets_insights(live_app, auth_client):
    meta = live_app.extensions["meta"]
    meta.accounts = Mock(return_value=[])
    meta.get = Mock(side_effect=APIError("Not permitted",403,"permission_denied"))
    result = auth_client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/OtherPage"}, headers=csrf(auth_client))
    assert result.status_code == 403 and result.json["error"]["code"] == "page_not_accessible"
    assert "0 authorized Pages" in result.json["error"]["message"]
    assert "Reconnect Facebook" in result.json["error"]["message"]


def test_public_metadata_cannot_access_private_insights(live_app, auth_client):
    meta = live_app.extensions["meta"]
    meta.accounts = Mock(return_value=[])
    meta.get = Mock(return_value={"id":"11111", "name":"Public Page", "category":"Community"})
    result = auth_client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/OtherPage"}, headers=csrf(auth_client))
    assert result.status_code == 200 and result.json["public_only"]
    assert auth_client.get("/api/facebook/insights").status_code == 403
    assert auth_client.get("/api/facebook/posts").status_code == 403


def test_oauth_state_validation_and_success(live_app):
    client = live_app.test_client()
    response = client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/TestPage"}, headers=csrf(client))
    url = urlsplit(response.json["authorization_url"])
    assert url.hostname == "www.facebook.com"
    params = parse_qs(url.query)
    assert params["scope"][0] == "pages_show_list,pages_read_engagement,read_insights"
    state = params["state"][0]
    meta = live_app.extensions["meta"]
    meta.exchange_code = Mock(return_value="SECRET_LOGIN_TOKEN")
    meta.get = Mock(side_effect=[{"id":"123456"}, {"data":[{"permission":"read_insights","status":"granted"}]}])
    meta.accounts = Mock(return_value=[{"id":"67890", "name":"Real Page", "link":"https://facebook.com/TestPage", "access_token":"SECRET_PAGE_TOKEN"}])
    result = client.get(f"/api/facebook/callback?state={state}&code=TEST_CODE")
    assert result.status_code == 302 and "auth=connected" in result.location
    assert client.get("/api/session").json["authenticated"]
    assert "SECRET" not in client.get("/api/session").text
    assert client.get(f"/api/facebook/callback?state={state}&code=TEST_CODE").status_code == 400


def test_account_login_loads_pages_without_requiring_a_page_url(live_app):
    client = live_app.test_client()
    response = client.post('/api/facebook/connect', json={'account_only': True}, headers=csrf(client))
    assert response.status_code == 200
    state = parse_qs(urlsplit(response.json['authorization_url']).query)['state'][0]
    meta = live_app.extensions['meta']
    meta.exchange_code = Mock(return_value='SECRET_USER_TOKEN')
    meta.get = Mock(side_effect=[{'id': '123456'}, {'data': [{'permission': 'pages_show_list', 'status': 'granted'}]}])
    meta.accounts = Mock()
    result = client.get(f'/api/facebook/callback?state={state}&code=TEST_CODE')
    assert result.status_code == 302 and 'auth=authorized' in result.location
    session = client.get('/api/session').json
    assert session['authenticated'] and session['page'] is None
    meta.accounts.assert_not_called()
    assert client.get(f'/api/facebook/callback?state={state}&code=TEST_CODE').status_code == 400


@pytest.mark.parametrize('pages,expected_id', [
    ([{'id': '1', 'access_token': 'SECRET_PAGE_1', 'tasks': ['CREATE_CONTENT']},
      {'id': '2', 'access_token': 'SECRET_PAGE_2', 'tasks': ['ANALYZE']}], '2'),
    ([{'id': '1', 'access_token': 'SECRET_PAGE_1'}], '1'),
    ([{'id': '1', 'tasks': ['ANALYZE']}, {'id': '2', 'access_token': 'SECRET_PAGE_2'}], '2'),
])
def test_auto_login_selects_an_available_page_and_keeps_tokens_private(live_app, pages, expected_id):
    client = live_app.test_client()
    response = client.post('/api/facebook/connect', json={'account_only': True, 'auto_connect': True}, headers=csrf(client))
    state = parse_qs(urlsplit(response.json['authorization_url']).query)['state'][0]
    meta = live_app.extensions['meta']
    meta.exchange_code = Mock(return_value='SECRET_USER_TOKEN')
    meta.get = Mock(side_effect=[{'id': '123456'}, {'data': []}])
    meta.accounts = Mock(return_value=pages)
    result = client.get(f'/api/facebook/callback?state={state}&code=TEST_CODE')
    assert result.status_code == 302 and 'auth=connected' in result.location
    session = client.get('/api/session')
    assert session.json['authenticated'] and session.json['page']['id'] == expected_id
    assert 'SECRET' not in session.text and 'access_token' not in session.text
    assert client.get(f'/api/facebook/callback?state={state}&code=TEST_CODE').status_code == 400
    meta.accounts.assert_called_once_with('SECRET_USER_TOKEN')


def test_auto_login_with_no_pages_preserves_login_and_shows_an_actionable_error(live_app):
    client = live_app.test_client()
    response = client.post('/api/facebook/connect', json={'account_only': True, 'auto_connect': True}, headers=csrf(client))
    state = parse_qs(urlsplit(response.json['authorization_url']).query)['state'][0]
    meta = live_app.extensions['meta']
    meta.exchange_code = Mock(return_value='SECRET_USER_TOKEN')
    meta.get = Mock(side_effect=[{'id': '123456'}, {'data': []}])
    meta.accounts = Mock(return_value=[])
    result = client.get(f'/api/facebook/callback?state={state}&code=TEST_CODE')
    assert 'auth=error' in result.location
    session = client.get('/api/session').json
    assert session['authenticated'] and session['page'] is None
    assert 'no Pages with access tokens' in session['login_error']


def test_auto_connect_reuses_this_browsers_selected_page_without_oauth(live_app, auth_client):
    meta = live_app.extensions['meta']
    meta.accounts = Mock()
    result = auth_client.post('/api/facebook/connect', json={'account_only': True, 'auto_connect': True}, headers=csrf(auth_client))
    assert result.status_code == 200
    assert result.json['authenticated'] and result.json['page']['id'] == '67890'
    assert 'authorization_url' not in result.json and 'SECRET' not in result.text
    meta.accounts.assert_not_called()
    with live_app.app_context():
        record = db.session.execute(db.select(BrowserSession)).scalar_one()
        assert 'oauth_state' not in record.read()


def test_auto_connect_selects_page_from_this_browsers_existing_account(live_app, auth_client):
    with live_app.app_context():
        record = db.session.execute(db.select(BrowserSession)).scalar_one()
        payload = record.read()
        payload.pop('selected_page')
        record.write(payload)
        db.session.commit()
    meta = live_app.extensions['meta']
    meta.accounts = Mock(return_value=[{'id': '24680', 'name': 'Available Page', 'access_token': 'SECRET_PAGE_TOKEN', 'tasks': ['ANALYZE']}])
    result = auth_client.post('/api/facebook/connect', json={'account_only': True, 'auto_connect': True}, headers=csrf(auth_client))
    assert result.status_code == 200 and result.json['page']['id'] == '24680'
    assert 'authorization_url' not in result.json and 'SECRET' not in result.text
    meta.accounts.assert_called_once_with('SECRET_USER_TOKEN')


def test_account_connect_reuses_login_without_auto_selecting_a_page(live_app, auth_client):
    result = auth_client.post('/api/facebook/connect', json={'account_only': True}, headers=csrf(auth_client))
    assert result.status_code == 200 and result.json['authenticated']
    assert 'authorization_url' not in result.json


@pytest.mark.parametrize('reauthorize', [False, True])
def test_only_explicit_reauthorization_rerequests_facebook_permissions(live_app, reauthorize):
    client = live_app.test_client()
    result = client.post('/api/facebook/connect', json={'account_only': True, 'reauthorize': reauthorize}, headers=csrf(client))
    params = parse_qs(urlsplit(result.json['authorization_url']).query)
    assert params.get('auth_type') == (['rerequest'] if reauthorize else None)


def test_explicit_reauthorization_still_opens_facebook_for_a_connected_account(live_app, auth_client):
    result = auth_client.post('/api/facebook/connect', json={'account_only': True, 'auto_connect': True, 'reauthorize': True}, headers=csrf(auth_client))
    assert result.status_code == 200 and 'authorization_url' in result.json
    assert parse_qs(urlsplit(result.json['authorization_url']).query)['auth_type'] == ['rerequest']


def test_oauth_bad_state_never_exchanges_code(live_app):
    client = live_app.test_client()
    client.post("/api/facebook/connect", json={"page_url":"https://facebook.com/TestPage"}, headers=csrf(client))
    meta = live_app.extensions["meta"]
    meta.exchange_code = Mock()
    assert client.get("/api/facebook/callback?state=wrong&code=code").status_code == 400
    meta.exchange_code.assert_not_called()


def test_disconnect_and_expiration_delete_credentials(live_app, auth_client):
    assert auth_client.delete("/api/session", headers=csrf(auth_client)).status_code == 200
    with live_app.app_context(): assert db.session.execute(db.select(BrowserSession)).scalars().all() == []
    assert auth_client.get("/api/facebook/posts").status_code == 401


def test_expired_session_is_rejected(live_app, auth_client):
    with live_app.app_context():
        record = db.session.execute(db.select(BrowserSession)).scalar_one()
        record.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        db.session.commit()
    assert auth_client.get("/api/facebook/insights").status_code == 401
    with live_app.app_context(): assert db.session.execute(db.select(BrowserSession)).scalars().all() == []


def test_signed_deletion_and_tampered_signatures(live_app, auth_client):
    encoded = base64.urlsafe_b64encode(json.dumps({"algorithm":"HMAC-SHA256", "user_id":"123456"}).encode()).rstrip(b"=")
    digest = hmac.new(live_app.config["META_APP_SECRET"].encode(), encoded, hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()+"."+encoded.decode()
    assert auth_client.post("/api/facebook/data-deletion", data={"signed_request":"bad."+encoded.decode()}).status_code == 403
    result = auth_client.post("/api/facebook/data-deletion", data={"signed_request":signed})
    assert result.status_code == 200
    code = result.json["confirmation_code"]
    assert auth_client.get(f"/api/deletion-status/{code}").json["status"] == "complete"
    assert auth_client.get("/api/facebook/insights").status_code == 401


@pytest.mark.parametrize("value", ["=HYPERLINK(\"evil\")", "+SUM(1,1)", "-1+1", "@SUM(1)", "  =1+1", "\t=1+1"])
def test_csv_formula_injection_is_escaped(value):
    assert csv_cell(value).startswith("'")


def test_api_errors_are_json_and_unknown_routes_are_404(client):
    assert client.get("/api/facebook/insights?days=nope").status_code == 400
    result = client.get("/api/missing")
    assert result.status_code == 404 and "error" in result.json
    assert client.get("/api/facebook/export?dataset=bad").status_code == 400
