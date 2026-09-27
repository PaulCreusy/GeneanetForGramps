# GeneanetForGramps - Self-managed venv for the isolated scraper worker.
#
# Gramps plugins run inside Gramps' own Python interpreter, which the addon
# has no control over: it can be the system Python, one bundled in an
# installer, or a Flatpak sandbox. Rather than requiring Selenium/lxml to be
# installed there, the addon creates and maintains its own dedicated venv on
# first use and runs the scraper (worker/) as a subprocess inside it - see
# src/worker_client.py.
import hashlib
import logging
import os
import subprocess
import sys

LOG = logging.getLogger("GeneanetForGramps")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS_FILE = os.path.join(REPO_ROOT, "requirements-worker.txt")

WORKER_ENV_DIR = os.path.expanduser("~/.local/share/geneanetforgramps/venv")
_MARKER_FILE = os.path.join(WORKER_ENV_DIR, ".requirements-hash")


class WorkerEnvError(Exception):
    """Raised when the dedicated worker venv cannot be created or used."""


def _venv_python():
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    exe = "python.exe" if sys.platform == "win32" else "python3"
    return os.path.join(WORKER_ENV_DIR, bindir, exe)


def _requirements_hash():
    with open(REQUIREMENTS_FILE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _is_up_to_date():
    if not os.path.exists(_venv_python()):
        return False
    try:
        with open(_MARKER_FILE) as f:
            return f.read().strip() == _requirements_hash()
    except FileNotFoundError:
        return False


def _check_flatpak():
    # A Flatpak-sandboxed Gramps typically cannot run venv/pip/chromium as
    # arbitrary subprocesses without explicit extra permissions - fail with
    # a clear, actionable message instead of a confusing subprocess error.
    if os.path.exists("/.flatpak-info"):
        raise WorkerEnvError(
            "GeneanetForGramps needs to run an external Python environment and a "
            "browser, which this Flatpak-sandboxed Gramps does not allow by "
            "default. Grant this Flatpak filesystem and process-spawning access "
            "(e.g. via Flatseal), or use a non-Flatpak install of Gramps.")


def ensure_worker_env(progress_callback=None):
    """Create (or refresh) the dedicated worker venv if needed. Returns the
    path to its python executable. progress_callback(message), if given, is
    called with human-readable status updates during a first-time setup
    (which downloads/builds Selenium + lxml, and can take a while)."""
    _check_flatpak()

    if _is_up_to_date():
        return _venv_python()

    def report(msg):
        LOG.info(msg)
        if progress_callback:
            progress_callback(msg)

    report("Setting up the GeneanetForGramps scraper environment (first run, this can take a minute)...")
    os.makedirs(os.path.dirname(WORKER_ENV_DIR), exist_ok=True)

    try:
        subprocess.run([sys.executable, "-m", "venv", WORKER_ENV_DIR], check=True)
        subprocess.run(
            [_venv_python(), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
        )
        subprocess.run(
            [_venv_python(), "-m", "pip", "install", "-r", REQUIREMENTS_FILE],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        raise WorkerEnvError(
            "Failed to set up the scraper worker environment: %s" % e) from e

    with open(_MARKER_FILE, "w") as f:
        f.write(_requirements_hash())

    report("Scraper environment ready.")
    return _venv_python()
