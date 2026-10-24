"""Bounded background exports. Jobs and PDFs are private to the initiating session."""
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .analytics import DEMO_PAGE, demo_insights, live_insights_combined
from .meta import MetaClient
from .pdf_report import render_pages_pdf
from .validation import APIError

logger = logging.getLogger(__name__)


class PDFExports:
    def __init__(self, app):
        self.app = app
        self.client_factory = lambda: MetaClient(app)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pagepulse-pdf")
        self.jobs = {}
        self.lock = threading.Lock()

    def start(self, owner, token, since, until, demo=False, cache=None):
        with self.lock:
            now = time.time()
            self.jobs = {key: job for key, job in self.jobs.items() if now-job["created"] < 3600 or job["status"] in ("queued", "running", "cancelling")}
            active = next((job for job in self.jobs.values() if job["owner"] == owner and job["status"] in ("queued", "running", "cancelling")), None)
            if active:
                raise APIError("A PDF export is already in progress. Wait for it or cancel it first.", 409, "export_busy")
            if len(self.jobs) >= 30:
                raise APIError("PDF export capacity is busy. Try again later.", 503, "export_busy", 60)
            job_id = secrets.token_urlsafe(24)
            job = {"id": job_id, "owner": owner, "created": now, "status": "queued", "total": 0,
                   "since": str(since), "until": str(until),
                   "completed": 0, "current_page": "", "error": None, "limited_pages": 0,
                   "filename": f"pagepulse-all-pages-{since}-{until}{'-sample' if demo else ''}.pdf",
                   "cancel": threading.Event(), "pdf": None}
            self.jobs[job_id] = job
        args = (job_id, token, since, until, demo, cache or {})
        if self.app.config.get("TESTING"):
            self._run(*args)
        else:
            self.executor.submit(self._run, *args)
        return self.get(job_id, owner)

    def get(self, job_id, owner, download=False):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["owner"] != owner or time.time()-job["created"] >= 3600:
                raise APIError("This PDF export is unavailable or expired. Start a new export.", 404, "export_not_found")
            if download:
                if job["status"] != "ready":
                    raise APIError("The PDF is not ready yet.", 409, "export_not_ready")
                return job["pdf"], job["filename"]
            return {key: job[key] for key in ("id", "status", "total", "completed", "current_page", "error", "limited_pages", "filename", "since", "until")}

    def cancel(self, job_id, owner):
        self.get(job_id, owner)
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in ("queued", "running"):
                job["cancel"].set()
                job["status"] = "cancelling"
        return self.get(job_id, owner)

    def forget(self, owner):
        """Stop future requests and discard generated PDFs when a session is deleted."""
        with self.lock:
            for job_id, job in list(self.jobs.items()):
                if job["owner"] != owner:
                    continue
                job["cancel"].set()
                job["pdf"] = None
                if job["status"] in ("queued", "running", "cancelling"):
                    job["status"] = "cancelling"
                else:
                    del self.jobs[job_id]

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)

    def _run(self, job_id, token, since, until, demo, cache):
        try:
            if self.jobs[job_id]["cancel"].is_set():
                self._update(job_id, status="cancelled")
                return
            self._update(job_id, status="running")
            client = self.client_factory()
            pages = [DEMO_PAGE] if demo else client.accounts(token)
            if not pages:
                raise APIError("Facebook did not authorize any Pages for this export. Reconnect Facebook and grant Page access.", 403, "page_required")
            if len(pages) > 500:
                raise APIError("This export supports at most 500 authorized Pages per report.", 422, "export_limit")
            pages.sort(key=lambda page: (page.get("name", "").casefold(), str(page["id"])))
            self._update(job_id, total=len(pages))
            entries, limited, failures, halt = [], 0, 0, None
            for page in pages:
                if self.jobs[job_id]["cancel"].is_set():
                    self._update(job_id, status="cancelled", current_page="")
                    return
                self._update(job_id, current_page=page.get("name", "Facebook Page"))
                # Only public metadata and normalized metrics enter the PDF.
                entry = {"page": {"id": str(page["id"]), "name": page.get("name", "Facebook Page")}, "report": None}
                if halt:
                    entry["error"] = halt
                else:
                    try:
                        cached = cache.get(f"{page['id']}:{since}:{until}")
                        if cached and time.time()-cached["time"] < 300:
                            entry["report"] = cached["data"]
                        else:
                            entry["report"] = demo_insights(since, until) if demo else live_insights_combined(client, page, since, until)
                        failures = 0
                    except APIError as exc:
                        entry["error"] = exc.message
                        failures += 1
                        if exc.code == "rate_limited":
                            halt = "Not fetched: Meta rate limit reached. Export again after the cooldown."
                        elif exc.code == "reauthorize" or failures >= 3:
                            halt = "Not fetched after repeated authorization or network failures. Reconnect Facebook or try again later."
                if entry.get("error") or any(entry["report"]["metrics"][key]["status"] != "available" for key in ("views", "interactions", "followers")):
                    limited += 1
                entries.append(entry)
                self._update(job_id, completed=len(entries), limited_pages=limited)
            if self.jobs[job_id]["cancel"].is_set():
                self._update(job_id, status="cancelled", current_page="")
                return
            pdf = render_pages_pdf(entries, since, until, demo=demo)
            self._update(job_id, status="ready", current_page="", pdf=pdf)
        except APIError as exc:
            self._update(job_id, status="failed", error=exc.message, current_page="")
        except Exception:
            logger.error("PDF export failed; details suppressed to protect Meta credentials.")
            self._update(job_id, status="failed", error="The PDF export could not be completed. Please try again.", current_page="")
