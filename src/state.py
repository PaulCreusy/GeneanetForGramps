# GeneanetForGramps - Shared runtime state, configuration, and i18n
import logging

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale, URL_MANUAL_PAGE

from src.constants import ROOTURL  # noqa: F401 - re-exported for `from src.state import ROOTURL`

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger("GeneanetForGramps")

# Maps the 0-3 verbosity slider (CLI -v count / GUI "Verbosity" option) onto
# standard logging levels. 2 and 3 both map to DEBUG: the extra granularity
# the old ad-hoc "if verbosity >= 3" checks had is not worth a custom level.
_VERBOSITY_TO_LEVEL = {0: logging.WARNING, 1: logging.INFO}


def configure_logging():
    """(Re)apply the current verbosity to the LOG logger. Safe to call more
    than once - it will not stack duplicate handlers."""
    level = _VERBOSITY_TO_LEVEL.get(verbosity, logging.DEBUG)
    LOG.setLevel(level)
    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOG.addHandler(handler)


def get_worker_client():
    """Return the shared WorkerClient, starting the scraper worker
    subprocess (in its own dedicated venv) on first use."""
    global worker_client
    if worker_client is None:
        from src.worker_client import WorkerClient
        worker_client = WorkerClient()
        worker_client.start()
    return worker_client


def close_worker():
    """Best-effort shutdown of the shared worker subprocess that ALWAYS
    clears worker_client, even if the clean shutdown itself fails - a
    narrower except here can leave a failed close() both hiding the worker
    from every later call (which sees worker_client as still "open") and
    skipping whatever cleanup the caller runs right after this."""
    global worker_client
    if worker_client is not None:
        try:
            worker_client.close()
        except Exception:
            LOG.debug(_("Failed to close the scraper worker cleanly"), exc_info=True)
        worker_client = None


TIMEOUT = 5
WIKI_HELP_PAGE = '%s_-_Tools' % URL_MANUAL_PAGE
WIKI_HELP_SEC = _('manual|GeneanetForGramps')

# Mutable runtime state
db = None
gname = None
verbosity = 0
force = False
ascendants = False
descendants = False
spouses = False
LEVEL = 2
GUIMODE = False
progress = None
worker_client = None
stop_on_error = False

CONFIG_NAME = "geneanetforgramps"
CONFIG = config.register_manager(CONFIG_NAME)
CONFIG.register("pref.ascendants", ascendants)
CONFIG.register("pref.descendants", descendants)
CONFIG.register("pref.spouses", spouses)
CONFIG.register("pref.level", LEVEL)
CONFIG.register("pref.force", force)
CONFIG.register("pref.verbosity", verbosity)
CONFIG.load()


def save_config():
    CONFIG.set("pref.ascendants", ascendants)
    CONFIG.set("pref.descendants", descendants)
    CONFIG.set("pref.spouses", spouses)
    CONFIG.set("pref.level", LEVEL)
    CONFIG.set("pref.force", force)
    CONFIG.set("pref.verbosity", verbosity)
    CONFIG.save()


save_config()
