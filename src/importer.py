# GeneanetForGramps - Top-level import orchestration
import sys

import src.state as state
from src.state import _
from src.gperson import GPerson


def geneanet_to_gramps(p, level, gid, url):
    if not p:
        p = GPerson(level)
    p.from_geneanet(url)
    p.from_gramps(gid)

    if gid is not None:
        if (p.firstname != p.g_firstname or p.lastname != p.g_lastname) and not state.force:
            print(_("Gramps   person: %s %s") % (p.firstname, p.lastname))
            print(_("Geneanet person: %s %s") % (p.g_firstname, p.g_lastname))
            if not state.GUIMODE:
                state.db.close()
                sys.exit(_("Do not continue without force"))
            else:
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

        if p.birthdate == p.g_birthdate or p.deathdate == p.g_deathdate or state.force:
            pass
        else:
            print(_("Gramps   person birth/death: %s / %s") % (p.birthdate, p.deathdate))
            print(_("Geneanet person birth/death: %s / %s") % (p.g_birthdate, p.g_deathdate))
            if not state.GUIMODE:
                state.db.close()
                sys.exit(_("Do not continue without force"))
            else:
                print(_("Please fix the person in gramps"))
                return None

    p.to_gramps()
    if state.GUIMODE:
        state.progress.set_header(_("Adding Gramps Person %s %s (%s | %s)") % (
            p.firstname, p.lastname, p.birthdate, p.deathdate))
        state.progress.step()
    return p


def g2gaction(gid, purl):
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
    if state.GUIMODE:
        state.progress.close()
