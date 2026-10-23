# GeneanetForGramps - What an import did, shown once it is over.
#
# One ImportReport is kept for the run in `current` (call start() to begin a
# new one). Code that creates, skips or fails to import something records it
# with `report.current.<method>(...)`; g2gaction() shows the result at the end.
from src.state import _
from src.progress import format_duration

# Lists in the summary are cut after this many entries.
MAX_LISTED = 15

COMPLETED = "completed"
CANCELLED = "cancelled"
STOPPED = "stopped"


class ImportReport:

    def __init__(self):
        self._persons = {}  # gramps id -> created during this import?
        self._families = {}
        self.skipped = []
        self.media_enabled = False  # set by the import: shows the media line
        self.media_added = 0
        self.media_failures = []
        self.conflicts = []
        self.failures = []
        self.outcome = COMPLETED
        self.reason = ""

    def person_done(self, gid, created):
        self._persons.setdefault(gid, created)

    def family_done(self, gid, created):
        self._families.setdefault(gid, created)

    def media_attached(self):
        self.media_added += 1

    def media_failure(self, text):
        self.media_failures.append(text)

    def skip(self, text):
        self.skipped.append(text)

    def conflict(self, text):
        self.conflicts.append(text)

    def failure(self, text):
        self.failures.append(text)

    def finish(self, outcome, reason=""):
        self.outcome = outcome
        self.reason = reason

    def title(self):
        return {
            COMPLETED: _("Geneanet import finished"),
            CANCELLED: _("Geneanet import cancelled"),
            STOPPED: _("Geneanet import stopped"),
        }[self.outcome]

    def render(self, pages, seconds):
        persons_new = sum(1 for created in self._persons.values() if created)
        families_new = sum(1 for created in self._families.values() if created)
        lines = []
        if self.outcome == CANCELLED:
            lines.append(_("The import was cancelled before the end: what is below is what was done so far."))
        elif self.outcome == STOPPED:
            lines.append(_("The import had to stop before the end: what is below is what was done so far."))
            if self.reason:
                lines.append(_("Reason: %s") % self.reason)
        lines += [
            "",
            _("Geneanet pages processed: %(pages)d (in %(time)s)") % {
                "pages": pages, "time": format_duration(seconds)},
            _("Persons created: %d") % persons_new,
            _("Persons already in the tree: %d") % (len(self._persons) - persons_new),
            _("Families created: %d") % families_new,
            _("Families already in the tree: %d") % (len(self._families) - families_new),
        ]
        if self.media_enabled:
            lines.append(_("Media added: %d") % self.media_added)
        lines += self._section(_("Skipped, private profile without a link"), self.skipped)
        lines += self._section(_("Not imported because of a conflict with the tree"), self.conflicts)
        if self.conflicts:
            lines.append(_("Fix these persons in Gramps, or enable Force Import to overwrite them, "
                           "then run the import again."))
        lines += self._section(_("Pages that could not be read"), self.failures)
        lines += self._section(_("Media that could not be downloaded"), self.media_failures)
        return "\n".join(lines)

    @staticmethod
    def _section(title, entries):
        if not entries:
            return []
        lines = ["", "%s (%d):" % (title, len(entries))]
        lines += ["  - %s" % entry for entry in entries[:MAX_LISTED]]
        if len(entries) > MAX_LISTED:
            lines.append("  " + _("... and %d more") % (len(entries) - MAX_LISTED))
        return lines


current = ImportReport()


def start():
    global current
    current = ImportReport()
    return current
