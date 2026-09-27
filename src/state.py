# GeneanetForGramps - Shared runtime state, configuration, and i18n
import logging

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale, URL_MANUAL_PAGE

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


def close_selenium_driver():
    """Best-effort cleanup of the shared Selenium driver that ALWAYS clears
    selenium_driver, even if quit() itself fails. A narrower except here
    (e.g. only Selenium's own WebDriverException) can leave a failed quit()
    both hiding the browser window from every later call (which sees
    selenium_driver as still "open") and skipping whatever cleanup the
    caller runs right after this - which is exactly how the browser was
    observed staying open at the end of an import."""
    global selenium_driver
    if selenium_driver is not None:
        try:
            selenium_driver.quit()
        except Exception:
            LOG.debug(_("Failed to close the Selenium browser cleanly"), exc_info=True)
        selenium_driver = None


TIMEOUT = 5
ROOTURL = 'https://gw.geneanet.org/'
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
selenium_driver = None
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
