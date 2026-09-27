# GeneanetForGramps - Client-side driver for the isolated scraper worker.
#
# Runs inside Gramps' own process. Starts the worker subprocess (in its own
# dedicated venv, see worker_env.py) and exchanges line-delimited JSON
# requests/responses with it over stdin/stdout. Selenium/lxml never get
# imported into Gramps' interpreter, and a Chrome crash in the worker cannot
# take Gramps down with it.
import json
import subprocess
import sys

from src.state import _, LOG
from src.worker_env import ensure_worker_env, REPO_ROOT
from src.exceptions import GeneanetAccessError

_LOG_LEVEL_FOR_VERBOSITY = {0: "WARNING", 1: "INFO"}


class WorkerClient:

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

    def _request(self, payload):
        if self._proc is None or self._proc.poll() is not None:
            raise GeneanetAccessError(_("The scraper worker process is not running."))
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise GeneanetAccessError(_("The scraper worker process closed unexpectedly."))
        return json.loads(line)

    def scrape(self, url):
        response = self._request({"cmd": "scrape", "url": url})
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
                self._request({"cmd": "close"})
                self._proc.wait(timeout=15)
        except Exception:
            LOG.debug(_("Failed to close the scraper worker cleanly, killing it"), exc_info=True)
        finally:
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc = None
