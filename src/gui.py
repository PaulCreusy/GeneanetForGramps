# GeneanetForGramps - Gramps GUI plugin classes
import src.state as state
from src.state import _, CONFIG, ROOTURL, save_config
from src.importer import g2gaction

from gramps.gui.plug import MenuToolOptions, PluginWindows
from gramps.gen.plug.menu import StringOption, PersonOption, BooleanOption, NumberOption
from gramps.gui.utils import ProgressMeter


class GeneanetForGrampsOptions(MenuToolOptions):

    def __init__(self, name, person_id=None, dbstate=None):
        if state.verbosity >= 3:
            print(_("Init Plugin Options"))
        MenuToolOptions.__init__(self, name, person_id, dbstate)

    def add_menu_options(self, menu):
        if state.verbosity >= 3:
            print(_("Add Plugin Menu Options"))
        category_name = _("Geneanet Import Options")

        self.__pid = PersonOption(_("Center Person"))
        self.__pid.set_help(_("The center person for the filter"))
        menu.add_option(category_name, "pid", self.__pid)

        if state.verbosity >= 3:
            print(_("Before URL"))
        self.__gui_url = StringOption(_("Geneanet URL for the selected person"), ROOTURL)
        self.__gui_url.set_help(
            _("URL on Geneanet of the person you have selected which will be used as an import base such as https://gw.geneanet.org/agnesy?lang=fr&n=queffelec&oc=17&p=marie+anne"))
        menu.add_option(category_name, "gui_url", self.__gui_url)

        if state.verbosity >= 3:
            print(_("Before ASC"))
        gui_asc = CONFIG.get('pref.ascendants')
        if state.verbosity >= 3:
            print(_("ASC True") if gui_asc else _("ASC False"))
        self.__gui_asc = BooleanOption(_("Import ascendants"), gui_asc)
        self.__gui_asc.set_help(_("Import ascendants of the selected person up to level number"))
        menu.add_option(category_name, "gui_asc", self.__gui_asc)

        if state.verbosity >= 3:
            print(_("Before DSC"))
        gui_dsc = CONFIG.get('pref.descendants')
        if state.verbosity >= 3:
            print(_("DSC True") if gui_dsc else _("DSC False"))
        self.__gui_dsc = BooleanOption(_("Import descendants"), gui_dsc)
        self.__gui_dsc.set_help(_("Import descendants of the selected person up to level number"))
        menu.add_option(category_name, "gui_dsc", self.__gui_dsc)

        if state.verbosity >= 3:
            print(_("Before SPO"))
        gui_spo = CONFIG.get('pref.spouses')
        if state.verbosity >= 3:
            print(_("SPO True") if gui_spo else _("SPO False"))
        self.__gui_spo = BooleanOption(_("Import spouses"), gui_spo)
        self.__gui_spo.set_help(_("Import all spouses of the selected person"))
        menu.add_option(category_name, "gui_spo", self.__gui_spo)

        if state.verbosity >= 3:
            print(_("Before LVL"))
        gui_lvl = CONFIG.get('pref.level')
        if state.verbosity >= 3:
            print(_("LVL:"), gui_lvl)
        self.__gui_level = NumberOption(_("Level of Import"), gui_lvl, 1, 100)
        self.__gui_level.set_help(
            _("Maximum of upper or lower search done in the family tree - keep it small"))
        menu.add_option(category_name, "gui_level", self.__gui_level)

        if state.verbosity >= 3:
            print(_("Before FORCE"))
        gui_force = CONFIG.get('pref.force')
        if state.verbosity >= 3:
            print(_("FORCE True") if gui_force else _("FORCE False"))
        self.__gui_force = BooleanOption(_("Force Import"), gui_force)
        self.__gui_force.set_help(_("Force import of existing persons"))
        menu.add_option(category_name, "gui_force", self.__gui_force)

        if state.verbosity >= 3:
            print(_("Before VRB"))
        gui_verb = CONFIG.get('pref.verbosity')
        if state.verbosity >= 3:
            print(_("VRB:"), gui_verb)
        self.__gui_verb = NumberOption(_("Verbosity"), gui_verb, 0, 3)
        self.__gui_verb.set_help(_("Verbosity level from 0 (minimal) to 3 (very verbose)"))
        menu.add_option(category_name, "gui_verb", self.__gui_verb)

        if state.verbosity >= 3:
            print(_("Menu Added"))


class GeneanetForGramps(PluginWindows.ToolManagedWindowBatch):

    def __init__(self, dbstate, user, options_class, name, callback):
        if state.verbosity >= 3:
            print(_("Init Plugin itself"))
        PluginWindows.ToolManagedWindowBatch.__init__(
            self, dbstate, user, options_class, name, callback)

    def get_title(self):
        if state.verbosity >= 3:
            print(_("Plugin get_title"))
        return _("Geneanet Import Tool")

    def initial_frame(self):
        if state.verbosity >= 3:
            print(_("Plugin initial_frame"))
        return _("Geneanet Import Options")

    def run(self):
        if state.verbosity >= 3:
            print(_("Plugin run"))
        state.db = self.dbstate.db
        self.__get_menu_options()
        hdr = _('Importing from %s for user %s') % (self.purl, self.gid)
        msg = _('Geneanet Import into Gramps')
        state.progress = ProgressMeter(msg, hdr)
        state.progress.set_pass(hdr, 100, mode=ProgressMeter.MODE_ACTIVITY)
        if state.verbosity >= 2:
            print(msg)
        state.GUIMODE = True
        g2gaction(self.gid, self.purl)

    def __get_menu_options(self):
        state.selenium_driver = None

        if state.verbosity >= 3:
            print(_("Plugin __get_menu_options"))

        self.gid = self.options.menu.get_option_by_name('pid').get_value()
        if state.verbosity >= 3:
            print(_("GID:"), self.gid)
        self.purl = self.options.menu.get_option_by_name('gui_url').get_value()
        if state.verbosity >= 3:
            print(_("URL:"), self.purl)
        state.force = self.options.menu.get_option_by_name('gui_force').get_value()
        state.ascendants = self.options.menu.get_option_by_name('gui_asc').get_value()
        if state.verbosity >= 3:
            print(_("ASC True") if state.ascendants else _("ASC False"))
        state.descendants = self.options.menu.get_option_by_name('gui_dsc').get_value()
        state.spouses = self.options.menu.get_option_by_name('gui_spo').get_value()
        state.LEVEL = self.options.menu.get_option_by_name('gui_level').get_value()
        state.verbosity = self.options.menu.get_option_by_name('gui_verb').get_value()
        if state.verbosity >= 3:
            print(_("LVL:"), state.LEVEL)
        save_config()
