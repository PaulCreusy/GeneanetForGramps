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

from src.state import _, LOG
from src.worker_env import ensure_worker_env, REPO_ROOT
from src.exceptions import GeneanetAccessError

_LOG_LEVEL_FOR_VERBOSITY = {0: "WARNING", 1: "INFO"}


class WorkerClient:
    # Bounds how long Gramps' own (single-threaded, GTK) process can be
    # frozen waiting on a worker reply. Comfortably above the worker's own
    # scrape budget (3 retry attempts x 60s, see worker/scraper.py) so a
    # normal slow page never trips it - this is only meant to catch a
    # worker that is genuinely stuck (e.g. a redirect leaving the browser
    # wedged on something Selenium never raises an exception for) and would
    # otherwise hang Gramps indefinitely with no error at all.
    SCRAPE_TIMEOUT = 240
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
        if state.GUIMODE and state.progress:
            state.progress.set_header(message)
        else:
            LOG.info(message)

    def _request(self, payload, timeout):
        if self._proc is None or self._proc.poll() is not None:
            raise GeneanetAccessError(_("The scraper worker process is not running."))
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

        # readline() has no timeout of its own, so a worker stuck on a
        # Selenium call that never raises (rather than one that fails
        # cleanly) would otherwise block this call - and with it Gramps'
        # own GTK thread - forever. Reading on a background thread lets the
        # timeout below apply regardless: the thread itself may keep
        # blocking on the dead worker's pipe, but it is a daemon thread and
        # the process is killed right after, so it cannot leak.
        replies = queue.Queue(maxsize=1)

        def _read():
            try:
                replies.put(self._proc.stdout.readline())
            except Exception:
                replies.put("")

        threading.Thread(target=_read, daemon=True).start()
        try:
            line = replies.get(timeout=timeout)
        except queue.Empty:
            LOG.error(_("The scraper worker did not respond within %ds - terminating it."), timeout)
            self._proc.kill()
            self._proc = None
            raise GeneanetAccessError(
                _("The scraper worker stopped responding (the browser may be stuck) and was terminated."))

        if not line:
            self._proc = None
            raise GeneanetAccessError(_("The scraper worker process closed unexpectedly."))
        return json.loads(line)

    def scrape(self, url):
        response = self._request({"cmd": "scrape", "url": url}, self.SCRAPE_TIMEOUT)
        if not response.get("ok"):
            error = response.get("error", _("Unknown scraper worker error"))
            if response.get("error_type") == "access":
                raise GeneanetAccessError(error)
            raise RuntimeError(error)
        return response["data"]

    def close(self):
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._request({"cmd": "close"}, self.CLOSE_TIMEOUT)
                if self._proc is not None:
                    self._proc.wait(timeout=15)
        except Exception:
            LOG.debug(_("Failed to close the scraper worker cleanly, killing it"), exc_info=True)
        finally:
            if self._proc is not None:
                if self._proc.poll() is None:
                    self._proc.kill()
                self._proc = None
