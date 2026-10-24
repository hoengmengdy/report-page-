from unittest.mock import Mock
import pytest
import requests
from backend.meta import MetaClient
from backend.validation import APIError


def response(body, status=200, headers=None):
    value = Mock(status_code=status, headers=headers or {})
    value.json.return_value = body
    return value


@pytest.mark.parametrize("code,status,name", [(190,401,"reauthorize"), (200,403,"permission_denied"), (10,403,"permission_denied"),
                                             (100,422,"metric_unavailable"), (3001,422,"metric_unavailable"),
                                             (4,429,"rate_limited"), (80001,429,"rate_limited"), (613,429,"rate_limited"), (2,502,"meta_error")])
def test_graph_error_translation(app, code, status, name):
    client = MetaClient(app)
    client.http.get = Mock(return_value=response({"error":{"code":code, "message":"PRIVATE_TOKEN_MUST_NOT_LEAK"}}, 400, {"Retry-After":"23"}))
    with pytest.raises(APIError) as caught: client.get("me", "PRIVATE_ACCESS_TOKEN")
    assert caught.value.status == status
    assert caught.value.code == name
    assert "PRIVATE" not in caught.value.message
    if status == 429: assert caught.value.retry_after == 23


def test_network_error_is_sanitized(app, caplog):
    client = MetaClient(app)
    client.http.get = Mock(side_effect=requests.Timeout("url?access_token=PRIVATE_TOKEN"))
    with pytest.raises(APIError) as caught: client.get("me", "PRIVATE_TOKEN")
    assert caught.value.status == 503
    assert "PRIVATE_TOKEN" not in caplog.text


def test_bad_json_and_invalid_response(app):
    client = MetaClient(app)
    bad = response(None)
    bad.json.side_effect = ValueError()
    client.http.get = Mock(return_value=bad)
    with pytest.raises(APIError) as caught: client.get("me")
    assert caught.value.status == 502


def test_bearer_token_and_proof_stay_on_backend(app):
    client = MetaClient(app)
    client.http.get = Mock(return_value=response({"id":"1"}))
    client.get("me", "SECRET_TOKEN", fields="id")
    args, kwargs = client.http.get.call_args
    assert args[0] == "https://graph.facebook.com/v26.0/me"
    assert kwargs["headers"]["Authorization"] == "Bearer SECRET_TOKEN"
    assert "access_token" not in kwargs["params"]
    assert len(kwargs["params"]["appsecret_proof"]) == 64
    assert kwargs["allow_redirects"] is False


def test_accounts_follow_cursors_without_following_untrusted_urls(app):
    client = MetaClient(app)
    client.get = Mock(side_effect=[{"data":[{"id":"1"}], "paging":{"next":"https://evil.test?access_token=SECRET", "cursors":{"after":"cursor1"}}}, {"data":[{"id":"2"}]}])
    assert [p["id"] for p in client.accounts("USER_TOKEN")] == ["1","2"]
    assert client.get.call_args_list[1].args[0] == "me/accounts"
    assert client.get.call_args_list[1].kwargs["after"] == "cursor1"


def test_pagination_cycle_fails(app):
    client = MetaClient(app)
    client.get = Mock(return_value={"data":[],"paging":{"next":"next", "cursors":{"after":"same"}}})
    with pytest.raises(APIError) as caught: client.accounts("token")
    assert caught.value.code == "pagination_limit"
