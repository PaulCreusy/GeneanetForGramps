# GeneanetForGramps - Top-level import orchestration
import sys

import src.state as state
from src.state import _
from src.gperson import GPerson
from src.exceptions import GeneanetAccessError
from gramps.gui.dialog import ErrorDialog


def _report_conflict(title, detail):
    """Report a blocking conflict: stop the CLI, or show a popup in GUI mode."""
    print(detail)
    if not state.GUIMODE:
        state.db.close()
        sys.exit(_("Do not continue without force"))
    else:
        ErrorDialog(title, detail + "\n\n" + _("Please fix the person in Gramps, or enable Force Import to overwrite it."))


def _dates_conflict(gramps_date, geneanet_date):
    """A conflict only exists when BOTH sides have a value and they differ.
    An empty value on either side is not a conflict: it is simply filled in
    from Geneanet (or left as-is in Gramps) by the smart-copy logic."""
    if not gramps_date or not geneanet_date:
        return False
    return gramps_date != geneanet_date


def geneanet_to_gramps(p, level, gid, url):
    if not p:
        p = GPerson(level)
    p.from_geneanet(url)
    p.from_gramps(gid)

    if gid is not None:
        if (p.firstname != p.g_firstname or p.lastname != p.g_lastname) and not state.force:
            detail = (_("Gramps   person: %s %s") % (p.firstname, p.lastname) + "\n" +
                      _("Geneanet person: %s %s") % (p.g_firstname, p.g_lastname))
            _report_conflict(_("Geneanet import: name conflict"), detail)
            return None

        # Fix potential empty dates
        if p.g_birthdate == "":
            p.g_birthdate = None
        if p.birthdate == "":
            p.birthdate = None
        if p.g_deathdate == "":
            p.g_deathdate = None
        if p.deathdate == "":
            p.deathdate = None

        birth_conflict = _dates_conflict(p.birthdate, p.g_birthdate)
        death_conflict = _dates_conflict(p.deathdate, p.g_deathdate)

        if (birth_conflict or death_conflict) and not state.force:
            detail = (_("Gramps   person birth/death: %s / %s") % (p.birthdate, p.deathdate) + "\n" +
                      _("Geneanet person birth/death: %s / %s") % (p.g_birthdate, p.g_deathdate))
            _report_conflict(_("Geneanet import: birth/death conflict"), detail)
            return None

    p.to_gramps()
    if state.GUIMODE:
        state.progress.set_header(_("Adding Gramps Person %s %s (%s | %s)") % (
            p.firstname, p.lastname, p.birthdate, p.deathdate))
        state.progress.step()
    return p


def g2gaction(gid, purl):
    try:
        try:
            gp = geneanet_to_gramps(None, 0, gid, purl)

            if gp is not None:
                if state.ascendants:
                    gp.recurse_parents(0)

                fam = []
                if state.spouses:
                    fam = gp.add_spouses(0)
                else:
                    # TODO: If we don't ask for spouses, we won't get children at all
                    pass

                if state.descendants:
                    for f in fam:
                        f.recurse_children(0)
        except GeneanetAccessError as e:
            detail = str(e)
            print(detail)
            if state.GUIMODE:
                ErrorDialog(_("Geneanet import stopped"), detail)
            else:
                print(_("Geneanet import stopped."))
    finally:
        if state.selenium_driver is not None:
            try:
                state.selenium_driver.quit()
            except Exception:
                pass
            state.selenium_driver = None
        if state.GUIMODE:
            state.progress.close()
