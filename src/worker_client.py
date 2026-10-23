# GeneanetForGramps - Client-side driver for the isolated scraper worker.
#
# Runs inside Gramps' own process. Starts the worker subprocess (in its own
# dedicated venv, see worker_env.py) and exchanges line-delimited JSON
# requests/responses with it over stdin/stdout. Selenium/lxml never get
# imported into Gramps' interpreter, and a Chrome crash in the worker cannot
# take Gramps down with it.
import json
import queue
import subprocess
import sys
import threading
import time

from src.state import _, LOG
from src.worker_env import ensure_worker_env, REPO_ROOT
from src.exceptions import GeneanetAccessError, ImportCancelled

_LOG_LEVEL_FOR_VERBOSITY = {0: "WARNING", 1: "INFO"}

# How often the wait for a worker reply wakes up to keep the window alive,
# show new status messages and notice a click on Cancel.
_POLL_INTERVAL = 0.1


def _access_error_text(code, params, fallback):
    """The user-language text of a GeneanetAccessError raised by the worker;
    the worker's own (English) message is the fallback for unknown codes."""
    if code == "login_failed":
        return _("Geneanet requires logging in to view %(url)s, and auto-login could not "
                 "complete it (no credentials configured, or login failed or blocked by "
                 "a CAPTCHA). Open this tool's options and fill in '%(user)s' and '%(password)s' "
                 "under '%(section)s', then try again.") % {
            "url": params.get("url", ""), "user": _("Geneanet username (email)"),
            "password": _("Geneanet password"), "section": _("Geneanet Login (optional)")}
    if code == "page_unresolved":
        return _("The page for %(url)s never resolved to a person page after %(attempts)d attempts "
                 "(Cloudflare check likely still pending, or the site kept redirecting "
                 "elsewhere).") % {"url": params.get("url", ""), "attempts": params.get("attempts", 0)}
    return fallback


def _status_text(event):
    """Translate a status event sent by the worker. The worker has no
    access to Gramps' translations, so it only sends a code and parameters."""
    code = event.get("code")
    if code == "cloudflare":
        return _("Waiting for the Cloudflare check: please tick the checkbox in the browser window")
    if code == "login":
        return _("Logging in to Geneanet...")
    if code == "retry":
        return _("Page not recognized, retrying (attempt %(attempt)d of %(max)d)...") % {
            "attempt": event.get("attempt", 0), "max": event.get("max", 0)}
    if code == "media":
        return _("Downloading media %(index)d of %(total)d...") % {
            "index": event.get("index", 0), "total": event.get("total", 0)}
    if code == "pause":
        return _("Short pause between two requests, to be fair with Geneanet...")
    return ""


class WorkerClient:
    # Bounds how long Gramps' own (single-threaded, GTK) process can be
    # frozen waiting on a worker reply. Comfortably above the worker's own
    # scrape budget (3 retry attempts x 60s, see worker/scraper.py) so a
    # normal slow page never trips it - this is only meant to catch a
    # worker that is genuinely stuck (e.g. a redirect leaving the browser
    # wedged on something Selenium never raises an exception for) and would
    # otherwise hang Gramps indefinitely with no error at all.
    SCRAPE_TIMEOUT = 240
    # The worker itself gives up reading the tree size after 120s.
    TREE_SIZE_TIMEOUT = 150
    # Allowed between two media downloads, which have no fixed number.
    MEDIA_TIMEOUT = 120
    CLOSE_TIMEOUT = 20

    def __init__(self):
        self._proc = None

    def start(self):
        import src.state as state
        python = ensure_worker_env(progress_callback=self._report_progress)
        level = _LOG_LEVEL_FOR_VERBOSITY.get(state.verbosity, "DEBUG")
        LOG.debug(_("Starting scraper worker: %s"), python)
        self._proc = subprocess.Popen(
            [python, "-u", "-m", "worker.main", level],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )

    def _report_progress(self, message):
        import src.state as state
        LOG.info(message)
        if state.progress:
            state.progress.set_status(message)

    def _stop(self):
        """End the worker without leaving its browser behind: SIGTERM lets it
        close Chrome itself (see worker/main.py); kill only if it ignores it."""
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _request(self, payload, timeout, cancellable=True):
        import src.state as state
        if self._proc is None or self._proc.poll() is not None:
            raise GeneanetAccessError(_("The scraper worker process is not running."))
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

        # readline() has no timeout of its own, so it is done on a background
        # thread: a worker stuck on a call that never raises would otherwise
        # block this one - and with it Gramps' own GTK thread - forever. The
        # thread forwards the status events the worker sends while it works,
        # then the final reply, and ends with the process (it is a daemon
        # thread, and the process is stopped on every error path below).
        proc = self._proc
        messages = queue.Queue()

        def _read():
            try:
                for line in proc.stdout:
                    message = json.loads(line)
                    messages.put(message)
                    if "event" not in message:
                        return
            except (OSError, ValueError):
                pass
            messages.put(None)

        threading.Thread(target=_read, daemon=True).start()

        deadline = time.monotonic() + timeout
        while True:
            try:
                message = messages.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                # Keep the window repainting (and Cancel clickable) while the
                # worker is busy, e.g. waiting on a Cloudflare check.
                if state.progress:
                    state.progress.pump()
                    if cancellable and state.progress.cancelled():
                        self._stop()
                        raise ImportCancelled()
                if time.monotonic() > deadline:
                    LOG.error(_("The scraper worker did not respond within %ds - terminating it."), timeout)
                    self._stop()
                    raise GeneanetAccessError(
                        _("The scraper worker stopped responding (the browser may be stuck) and was terminated."))
                continue

            if message is None:
                self._proc = None
                raise GeneanetAccessError(_("The scraper worker process closed unexpectedly."))
            if "event" in message:
                text = _status_text(message)
                if text and state.progress:
                    state.progress.set_status(text)
                if message.get("code") == "media":
                    # Files keep coming in: the worker is working, not stuck.
                    deadline = max(deadline, time.monotonic() + self.MEDIA_TIMEOUT)
                continue
            return message

    def tree_size(self, url):
        """Number of persons in the Geneanet tree url belongs to, or None if
        it could not be read (the import does not depend on it)."""
        response = self._request({"cmd": "tree_size", "url": url}, self.TREE_SIZE_TIMEOUT)
        return (response.get("data") or {}).get("size")

    def scrape(self, url, media_dir=None):
        """Fetch and parse a person page; with media_dir, also download the
        photos and documents attached to the person into that directory."""
        response = self._request({"cmd": "scrape", "url": url, "media_dir": media_dir},
                                 self.SCRAPE_TIMEOUT)
        if not response.get("ok"):
            error = response.get("error", _("Unknown scraper worker error"))
            if response.get("error_type") == "access":
                code, params = response.get("code"), response.get("params") or {}
                raise GeneanetAccessError(_access_error_text(code, params, error), code=code, **params)
            raise RuntimeError(error)
        return response["data"]

    def close(self):
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._request({"cmd": "close"}, self.CLOSE_TIMEOUT, cancellable=False)
                if self._proc is not None:
                    self._proc.wait(timeout=15)
        except Exception:
            LOG.debug(_("Failed to close the scraper worker cleanly, killing it"), exc_info=True)
        finally:
            self._stop()
