# GeneanetForGramps - Top-level import orchestration
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import src.state as state
from src.state import _, LOG
from src.gperson import GPerson
from src.progress import ImportProgress
from src import report
from src.exceptions import GeneanetAccessError, ImportCancelled
from src.worker_env import WorkerEnvError
from src.names import same_name, is_unknown
from gramps.gui.dialog import ErrorDialog, InfoDialog


def _record_conflict(description):
    """A person that differs between Gramps and Geneanet is left untouched and
    listed in the final report; the import goes on with the rest. Stopping, or
    a popup per conflict, made a long import unusable as soon as a few persons
    differed."""
    LOG.warning(description)
    report.current.conflict(description)


def _dates_conflict(gramps_date, geneanet_date):
    """A conflict only exists when BOTH sides have a value and they differ.
    An empty value on either side is not a conflict: it is simply filled in
    from Geneanet (or left as-is in Gramps) by the smart-copy logic."""
    if not gramps_date or not geneanet_date:
        return False
    return gramps_date != geneanet_date


def _skip(p):
    """Detach a person that is not imported from the Gramps person it was
    matched with, so nothing built afterwards (a family, the parents' links)
    can be attached to a person who turned out to be different. Returns None,
    the "not imported" answer of geneanet_to_gramps()."""
    p.gid = None
    p.grampsp = None
    return None


def geneanet_to_gramps(p, level, gid, url):
    # Every person fetched during the (possibly deep) recursive import goes
    # through here first, so this is the one place that needs to check for
    # a user-requested Stop - raising unwinds the whole recursion instead of
    # fetching and reporting a conflict for every remaining person.
    if state.progress.cancelled():
        raise ImportCancelled()

    if not p:
        p = GPerson(level)
    state.progress.page_started(url, level)
    p.from_geneanet(url)
    state.progress.page_done(p, level, url)
    if is_unknown(p.g_firstname, p.g_lastname):
        # A person Geneanet knows nothing about has no date either, so every
        # one of them would be matched with, and merged into, the same Gramps
        # person: they are not imported.
        LOG.info(_("Unknown person (%s), not imported"), url)
        report.current.unknown_person(url)
        p.unknown = True
        return _skip(p)
    p.from_gramps(gid)

    if gid is not None:
        if (not same_name(p.firstname, p.g_firstname)
                or not same_name(p.lastname, p.g_lastname)) and not state.force:
            _record_conflict(_("Name - Gramps: %(gramps)s / Geneanet: %(geneanet)s (%(url)s)") % {
                "gramps": ("%s %s" % (p.firstname, p.lastname)).strip(),
                "geneanet": ("%s %s" % (p.g_firstname, p.g_lastname)).strip(),
                "url": url})
            return _skip(p)

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
            _record_conflict(_("Birth/death - Gramps: %(gramps)s / Geneanet: %(geneanet)s (%(url)s)") % {
                "gramps": "%s / %s" % (p.birthdate, p.deathdate),
                "geneanet": "%s / %s" % (p.g_birthdate, p.g_deathdate),
                "url": url})
            return _skip(p)

    p.to_gramps()
    report.current.person_done(p.gid, p.created)
    return p


def _show_summary(pages, seconds):
    """Tell the user what the import did, in a window that stays until it is
    closed (GUI) or as plain output (command line)."""
    text = report.current.render(pages, seconds)
    if state.GUIMODE:
        InfoDialog(report.current.title(), text)
    else:
        print("\n" + report.current.title() + "\n" + text)


def _read_tree_size(purl):
    """Total number of persons of the tree being imported from, used to
    bound the progress estimate. None when unavailable: that never stops
    the import, except when the scraper environment itself cannot be set
    up, which is reported now rather than as a failure on every page."""
    state.progress.set_status(_("Reading the size of the Geneanet tree..."))
    try:
        return state.get_worker_client().tree_size(purl)
    except (GeneanetAccessError, ImportCancelled):
        raise
    except WorkerEnvError as err:
        raise GeneanetAccessError(str(err)) from err
    except Exception:
        LOG.debug("Could not read the tree size", exc_info=True)
        return None


def clean_person_url(purl):
    """The URL without its "type" parameter (type=tree, ...): it selects a
    view of the page that is not the person page the scraper expects."""
    parts = urlsplit(purl.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "type"]
    return urlunsplit(parts._replace(query=urlencode(query)))


def g2gaction(gid, purl):
    purl = clean_person_url(purl)
    if state.progress is None:
        state.progress = ImportProgress()
    report.start().media_enabled = state.media
    try:
        try:
            state.progress.set_tree_size(_read_tree_size(purl))
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
            report.current.finish(report.STOPPED, detail)
            LOG.error(detail)
            if state.GUIMODE:
                ErrorDialog(_("Geneanet import stopped"), detail)
            else:
                LOG.error(_("Geneanet import stopped."))
        except ImportCancelled:
            report.current.finish(report.CANCELLED)
            LOG.info(_("Geneanet import cancelled by the user."))
    finally:
        state.close_worker()
        pages, seconds = state.progress.estimator.done, state.progress.elapsed()
        state.progress.close()
        state.progress = None
        _show_summary(pages, seconds)
