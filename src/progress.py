# GeneanetForGramps - Import progress: estimated bar plus textual status.
#
# Wraps Gramps' ProgressMeter in the GUI (or just logs in command-line mode)
# and feeds it from the traversal: the bar comes from src/estimator.py, the
# text says which page is being handled, what the worker is waiting for
# (e.g. a Cloudflare check) and how long it has taken.
import time

import src.state as state
from src.state import _, LOG
from src.estimator import TreeEstimator

BAR_STEPS = 100


def format_duration(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


class ImportProgress:

    def __init__(self, meter=None):
        """`meter` is a gramps.gui.utils.ProgressMeter already set up with
        set_pass(header, BAR_STEPS), or None to only log progress."""
        self.meter = meter
        self.estimator = TreeEstimator(state.LEVEL)
        self.started = time.monotonic()
        self._bar_index = 0
        self._person = ""
        self._status = ""

    def set_tree_size(self, size):
        self.estimator.set_tree_size(size)
        if size:
            LOG.info(_("The Geneanet tree has %d persons"), size)

    def elapsed(self):
        return time.monotonic() - self.started

    def cancelled(self):
        return bool(self.meter and self.meter.get_cancelled())

    def page_started(self, url, level):
        self._status = _("Fetching the Geneanet page...")
        LOG.debug("Fetching %s (level %d)", url, level)
        self._refresh()

    def set_status(self, text):
        """A short message about what is being waited for; replaced by the
        next page. Also used while the scraper environment is prepared."""
        self._status = text
        self._refresh()

    def page_done(self, person, level, url):
        """Called once a page has been fetched and parsed: counts the links
        the traversal will follow from it and updates the display."""
        self.estimator.page_done(url, level, self._followed_links(person, level))
        names = ("%s %s" % (person.g_firstname, person.g_lastname)).strip() or _("(no name)")
        dates = " - ".join(d for d in (person.g_birthdate, person.g_deathdate) if d)
        self._person = "%s (%s)" % (names, dates) if dates else names
        self._status = ""
        self._advance_bar()
        LOG.info("[%d/~%d] %s", self.estimator.done, round(self.estimator.total()), self._person)
        self._refresh()

    def _followed_links(self, person, level):
        """The (url, level) of the links on this page that the options and
        the depth limit mean will be fetched. An estimate: the exact path
        taken depends on how the pages are reached."""
        links = []
        if state.ascendants and level < state.LEVEL:
            links += [(ref, level + 1) for ref in (person.fref, person.mref) if ref]
        if state.spouses:
            links += [(ref, level) for ref in person.spouseref if ref]
            if state.descendants and level < state.LEVEL:
                for children in person.childref:
                    links += [(ref, level + 1) for ref in children if ref]
        return links

    def _advance_bar(self):
        if not self.meter:
            return
        target = int(self.estimator.fraction() * BAR_STEPS)
        while self._bar_index < target:
            self.meter.step()
            self._bar_index += 1

    def _text(self):
        est = self.estimator
        lines = []
        if est.done:
            if est.capped():
                # The projection exceeds the tree: its size is the real limit.
                lines.append(_("Page %(done)d of at most %(total)d (size of the Geneanet tree)") % {
                    "done": est.done, "total": round(est.total())})
            else:
                lines.append(_("Page %(done)d of about %(total)d (estimated)") % {
                    "done": est.done, "total": round(est.total())})
        if self._status:
            lines.append(self._status)
        elif self._person:
            lines.append(self._person)
        elapsed = time.monotonic() - self.started
        timing = _("Elapsed: %s") % format_duration(elapsed)
        if est.done >= 3 and est.remaining() >= 1:
            eta = elapsed / est.done * est.remaining()
            timing += " - " + _("about %s remaining") % format_duration(eta)
        lines.append(timing)
        return "\n".join(lines)

    def _refresh(self):
        if self.meter:
            # set_header also lets Gtk process pending events, which is what
            # keeps the window repainting and the Cancel button working.
            self.meter.set_header(self._text())

    def pump(self):
        """Keep the window alive while waiting on the worker."""
        self._refresh()

    def close(self):
        if self.meter:
            while self._bar_index < BAR_STEPS:
                self.meter.step()
                self._bar_index += 1
            self.meter.close()
        LOG.info(_("Import finished: %d Geneanet pages processed in %s"),
                 self.estimator.done, format_duration(time.monotonic() - self.started))
