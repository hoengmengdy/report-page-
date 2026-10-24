import io
import secrets
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock

from pypdf import PdfReader

from backend.analytics import demo_insights, live_insights_combined
from backend.models import BrowserSession, db
from backend.validation import APIError
from conftest import csrf


def setup_pages(live_app, monkeypatch, count=4):
    client = Mock()
    client.accounts.return_value = [{"id": str(10000+i), "name": f"Authorized Page {i}", "access_token": "SECRET_PAGE_TOKEN"} for i in range(count)]
    live_app.extensions["pdf_exports"].client_factory = lambda: client
    insights = Mock(side_effect=lambda _client, _page, since, until: demo_insights(since, until))
    monkeypatch.setattr("backend.pdf_jobs.live_insights_combined", insights)
    return client, insights


def test_all_authorized_pages_pdf_has_three_cards_per_page_and_is_session_private(live_app, auth_client, monkeypatch):
    client, insights = setup_pages(live_app, monkeypatch)
    original_page = auth_client.get("/api/session").json["page"]
    result = auth_client.post("/api/facebook/export/jobs", json={"days": "7"}, headers=csrf(auth_client))
    assert result.status_code == 202
    job = result.json
    assert job["status"] == "ready" and job["completed"] == job["total"] == 4
    assert "SECRET" not in result.text and "token" not in result.text
    file = auth_client.get(f"/api/facebook/export/jobs/{job['id']}/file")
    assert file.status_code == 200 and file.mimetype == "application/pdf"
    assert file.headers["Cache-Control"] == "no-store"
    reader = PdfReader(io.BytesIO(file.data))
    assert len(reader.pages) == 2
    content = "\n".join(page.extract_text() for page in reader.pages)
    assert content.count("Total views") == content.count("Content interactions") == content.count("Total followers") == 4
    assert all(f"Authorized Page {i}" in content for i in range(4))
    assert "SECRET" not in content
    assert client.accounts.call_count == 1 and insights.call_count == 4
    assert auth_client.get("/api/session").json["page"] == original_page
    anonymous = live_app.test_client()
    assert anonymous.get(f"/api/facebook/export/jobs/{job['id']}").status_code == 401
    other = live_app.test_client()
    sid = secrets.token_urlsafe(32)
    with live_app.app_context():
        record = BrowserSession(id=sid, expires_at=datetime.now(timezone.utc)+timedelta(hours=8))
        record.write({"user_token": "OTHER_USER_TOKEN"})
        db.session.add(record)
        db.session.commit()
    with other.session_transaction() as state:
        state["sid"] = sid
    assert other.get(f"/api/facebook/export/jobs/{job['id']}").status_code == 404
    assert other.get(f"/api/facebook/export/jobs/{job['id']}/file").status_code == 404


def test_rate_limit_stops_meta_calls_and_marks_all_remaining_pages_unavailable(live_app, auth_client, monkeypatch):
    _, insights = setup_pages(live_app, monkeypatch, count=3)
    insights.side_effect = APIError("Meta rate limit reached.", 429, "rate_limited", 60)
    job = auth_client.post("/api/facebook/export/jobs", json={"days": "7"}, headers=csrf(auth_client)).json
    assert job["status"] == "ready" and job["total"] == job["completed"] == job["limited_pages"] == 3
    assert insights.call_count == 1
    result = auth_client.get(f"/api/facebook/export/jobs/{job['id']}/file")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(result.data)).pages)
    assert text.count("N/A") == 9 and "rate limit" in text


def test_demo_pdf_is_labeled_and_invalid_ranges_are_rejected(client):
    headers = csrf(client)
    assert client.post("/api/facebook/export/jobs", json={"days": "500"}, headers=headers).status_code == 400
    job = client.post("/api/facebook/export/jobs", json={"days": "7"}, headers=headers).json
    assert job["status"] == "ready" and job["total"] == 1
    result = client.get(f"/api/facebook/export/jobs/{job['id']}/file")
    assert "sample" in result.headers["Content-Disposition"]
    assert "SAMPLE DATA" in PdfReader(io.BytesIO(result.data)).pages[0].extract_text()


def test_cancelled_queued_job_does_not_request_meta(live_app, auth_client, monkeypatch):
    client, _ = setup_pages(live_app, monkeypatch)
    manager = live_app.extensions["pdf_exports"]
    submit = Mock()
    monkeypatch.setattr(manager.executor, "submit", submit)
    monkeypatch.setitem(live_app.config, "TESTING", False)
    job = auth_client.post("/api/facebook/export/jobs", json={"days": "7"}, headers=csrf(auth_client)).json
    assert job["status"] == "queued"
    assert auth_client.delete(f"/api/facebook/export/jobs/{job['id']}", headers=csrf(auth_client)).json["status"] == "cancelling"
    runner, *args = submit.call_args.args
    runner(*args)
    assert auth_client.get(f"/api/facebook/export/jobs/{job['id']}").json["status"] == "cancelled"
    client.accounts.assert_not_called()


def test_combined_pdf_metrics_use_two_requests_and_keep_followers_as_a_snapshot():
    client = Mock()
    def get(_path, _token, **params):
        current = params["since"] == "2026-10-16"
        return {"data": [{"name": name, "values": [{"end_time": "2026-10-23T00:00:00+00:00" if current else "2026-10-16T00:00:00+00:00", "value": value}]} for name, value in [("page_media_view", 100), ("page_post_engagements", 20), ("page_follows", 12 if current else 10)]]}
    client.get.side_effect = get
    client.next_cursor.return_value = None
    report = live_insights_combined(client, {"id": "12345", "access_token": "TOKEN"}, date(2026,10,16), date(2026,10,22))
    assert client.get.call_count == 2
    assert report["metrics"]["followers"]["value"] == 12 and report["metrics"]["followers"]["growth"] == 20
    assert report["metrics"]["views"]["value"] == 100 and report["metrics"]["views"]["status"] == "partial"
