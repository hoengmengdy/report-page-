from datetime import date, timedelta
import pytest
from backend.validation import APIError, cursor_arg, date_range, page_size, parse_page_url


@pytest.mark.parametrize("url,identity", [
    ("https://www.facebook.com/YourPageName", "yourpagename"),
    (" https://facebook.com/My.Page/ ", "my.page"),
    ("https://m.facebook.com/YourPage?ref=bookmarks", "yourpage"),
    ("https://web.facebook.com/profile.php?id=123456789&ref=page", "123456789"),
    ("https://www.facebook.com/pages/Example-Page/123456789", "123456789"),
    ("https://www.facebook.com:443/ExamplePage", "examplepage"),
])
def test_valid_page_urls(url, identity):
    assert parse_page_url(url)["identity"] == identity


@pytest.mark.parametrize("url", [
    None, 42, "", "javascript:alert(1)", "http://facebook.com/PageName", "https://facebook.com.evil.test/PageName",
    "https://evil.test/?url=https://facebook.com/PageName", "https://facebook.com@evil.test/PageName",
    "https://name:password@facebook.com/PageName", "https://facebook.com:8080/PageName",
    "https://facebook.com:bad/PageName", "https://facebook.com/", "https://facebook.com/groups/12345",
    "https://facebook.com/PageName/posts/123", "https://facebook.com/profile.php?id=abc",
    "https://facebook.com/profile.php?id=123456&id=123457", "https://facebook.com/PageName#access_token=secret",
    "https://facebook.com/PageName%2Fposts", "https://facebook.com/..", "https://facebook.com/login.php",
    "https://127.0.0.1/PageName", "https://facebook.com/"+"a"*2050,
])
def test_invalid_page_urls(url):
    with pytest.raises(APIError):
        parse_page_url(url)


@pytest.mark.parametrize("args", [{"days":"8"}, {"days":"oops"}, {"since":"2026-01-01"},
                                     {"since":"2026-02-30", "until":"2026-03-01"},
                                     {"since":"2020-01-01", "until":"2020-01-02"},
                                     {"since":"2099-01-01", "until":"2099-01-02"}])
def test_invalid_dates(args):
    with pytest.raises(APIError): date_range(args)


def test_ranges_are_inclusive_and_end_yesterday():
    for days in (7,28,90):
        since, until = date_range({"days":str(days)})
        assert until == date.today()-timedelta(days=1)
        assert (until-since).days+1 == days
    since, until = date_range({"since":str(date.today()-timedelta(days=89)), "until":str(date.today())})
    assert (until-since).days == 89


@pytest.mark.parametrize("args", [{"limit":"0"}, {"limit":"101"}, {"limit":"bad"}])
def test_invalid_page_sizes(args):
    with pytest.raises(APIError): page_size(args)


def test_cursor_is_not_a_url():
    with pytest.raises(APIError): cursor_arg({"after":"https://evil.test/steal?access_token=secret"})
