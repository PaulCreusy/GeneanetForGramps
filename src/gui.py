# GeneanetForGramps - Gramps GUI plugin classes
import src.state as state
from src.state import _, LOG, CONFIG, ROOTURL, save_config
from src.importer import g2gaction

from gramps.gui.plug import MenuToolOptions, PluginWindows
from gramps.gen.plug.menu import StringOption, PersonOption, BooleanOption, NumberOption
from gramps.gui.utils import ProgressMeter


class GeneanetForGrampsOptions(MenuToolOptions):

    def __init__(self, name, person_id=None, dbstate=None):
        MenuToolOptions.__init__(self, name, person_id, dbstate)

    def add_menu_options(self, menu):
        category_name = _("Geneanet Import Options")

        self.__pid = PersonOption(_("Center Person"))
        self.__pid.set_help(_("The center person for the filter"))
        menu.add_option(category_name, "pid", self.__pid)

        self.__gui_url = StringOption(_("Geneanet URL for the selected person"), ROOTURL)
        self.__gui_url.set_help(
            _("URL on Geneanet of the person you have selected which will be used as an import base such as https://gw.geneanet.org/agnesy?lang=fr&n=queffelec&oc=17&p=marie+anne"))
        menu.add_option(category_name, "gui_url", self.__gui_url)

        gui_asc = CONFIG.get('pref.ascendants')
        self.__gui_asc = BooleanOption(_("Import ascendants"), gui_asc)
        self.__gui_asc.set_help(_("Import ascendants of the selected person up to level number"))
        menu.add_option(category_name, "gui_asc", self.__gui_asc)

        gui_dsc = CONFIG.get('pref.descendants')
        self.__gui_dsc = BooleanOption(_("Import descendants"), gui_dsc)
        self.__gui_dsc.set_help(_("Import descendants of the selected person up to level number"))
        menu.add_option(category_name, "gui_dsc", self.__gui_dsc)

        gui_spo = CONFIG.get('pref.spouses')
        self.__gui_spo = BooleanOption(_("Import spouses"), gui_spo)
        self.__gui_spo.set_help(_("Import all spouses of the selected person"))
        menu.add_option(category_name, "gui_spo", self.__gui_spo)

        gui_lvl = CONFIG.get('pref.level')
        self.__gui_level = NumberOption(_("Level of Import"), gui_lvl, 1, 100)
        self.__gui_level.set_help(
            _("Maximum of upper or lower search done in the family tree - keep it small"))
        menu.add_option(category_name, "gui_level", self.__gui_level)

        gui_force = CONFIG.get('pref.force')
        self.__gui_force = BooleanOption(_("Force Import"), gui_force)
        self.__gui_force.set_help(_("Force import of existing persons"))
        menu.add_option(category_name, "gui_force", self.__gui_force)

        gui_verb = CONFIG.get('pref.verbosity')
        self.__gui_verb = NumberOption(_("Verbosity"), gui_verb, 0, 3)
        self.__gui_verb.set_help(_("Verbosity level from 0 (minimal) to 3 (very verbose)"))
        menu.add_option(category_name, "gui_verb", self.__gui_verb)


class GeneanetForGramps(PluginWindows.ToolManagedWindowBatch):

    def __init__(self, dbstate, user, options_class, name, callback):
        PluginWindows.ToolManagedWindowBatch.__init__(
            self, dbstate, user, options_class, name, callback)

    def get_title(self):
        return _("Geneanet Import Tool")

    def initial_frame(self):
        return _("Geneanet Import Options")

    def run(self):
        state.db = self.dbstate.db
        self.__get_menu_options()
        hdr = _('Importing from %s for user %s') % (self.purl, self.gid)
        msg = _('Geneanet Import into Gramps')
        state.progress = ProgressMeter(msg, hdr)
        state.progress.set_pass(hdr, 100, mode=ProgressMeter.MODE_ACTIVITY)
        LOG.info(msg)
        state.GUIMODE = True
        g2gaction(self.gid, self.purl)

    def __get_menu_options(self):
        state.selenium_driver = None

        self.gid = self.options.menu.get_option_by_name('pid').get_value()
        self.purl = self.options.menu.get_option_by_name('gui_url').get_value()
        state.force = self.options.menu.get_option_by_name('gui_force').get_value()
        state.ascendants = self.options.menu.get_option_by_name('gui_asc').get_value()
        state.descendants = self.options.menu.get_option_by_name('gui_dsc').get_value()
        state.spouses = self.options.menu.get_option_by_name('gui_spo').get_value()
        state.LEVEL = self.options.menu.get_option_by_name('gui_level').get_value()
        state.verbosity = self.options.menu.get_option_by_name('gui_verb').get_value()
        state.configure_logging()
        LOG.debug(_("GID: %s, URL: %s, ascendants=%s descendants=%s spouses=%s level=%s force=%s"),
                  self.gid, self.purl, state.ascendants, state.descendants,
                  state.spouses, state.LEVEL, state.force)
        save_config()
