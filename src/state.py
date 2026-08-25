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

TIMEOUT = 5
ROOTURL = 'https://gw.geneanet.org/'
WIKI_HELP_PAGE = '%s_-_Tools' % URL_MANUAL_PAGE
WIKI_HELP_SEC = _('manual|GeneanetForGramps')

# Mutable runtime state
db = None
gname = None
verbosity = 5
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
