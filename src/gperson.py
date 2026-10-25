# GeneanetForGramps - GPerson class
import src.state as state
from src.state import _, LOG
from src.gbase import GBase
from src.date_utils import format_year, dates_identify
from src.exceptions import GeneanetAccessError, ImportCancelled
from src import report
from src.names import same_name

import os
import re

from gramps.gen.db import DbTxn
from gramps.gen.errors import HandleError
from gramps.gen.lib import (
    Person, Name, NameType, Event, EventRef, EventType, EventRoleType,
    Url, UrlType, Media, MediaRef, Date,
)
from gramps.gen.mime import get_type
from gramps.gen.utils.file import media_path, media_path_full, relative_path

# Subfolder of the media base path of the tree where the files are stored.
MEDIA_SUBDIRECTORY = "Geneanet"


class GPerson(GBase):

    def __init__(self, level):
        LOG.debug(_("Initialize Person at level %d"), level)
        self.level = level
        # Geneanet shows this person as "? ?": never imported, but the family
        # it belongs to is still created with the known parent only.
        self.unknown = False
        # Gramps
        self.firstname = ""
        self.lastname = ""
        self.sex = 'U'
        self.birthdate = None
        self.birthplace = None
        self.birthplacecode = None
        self.deathdate = None
        self.deathplace = None
        self.deathplacecode = None
        self.occupation = None
        self.gid = None
        self.grampsp = None
        self.created = False
        # Father and Mother and Spouses GPersons
        self.father = None
        self.mother = None
        self.spouse = []
        # GFamilies
        self.family = []
        # Geneanet
        self.g_firstname = ""
        self.g_lastname = ""
        self.g_sex = 'U'
        self.g_birthdate = None
        self.g_birthplace = None
        self.g_birthplacecode = None
        self.g_deathdate = None
        self.g_deathplace = None
        self.g_deathplacecode = None
        self.g_occupation = None
        self.g_titles = []
        self.g_media = []  # [{title, date, file, is_default}] downloaded for this person
        self.url = ""
        self.spouseref = []
        self.fref = ""
        self.mref = ""
        self.marriagedate = []
        self.marriageplace = []
        self.marriageplacecode = []
        self.childref = []

    def smartcopy(self):
        LOG.debug(_("Smart Copying Person %s"), self.gid)
        self._smartcopy("firstname")
        self._smartcopy("lastname")
        self._smartcopy("sex")
        self._smartcopy("birthdate")
        self._smartcopy("birthplace")
        self._smartcopy("birthplacecode")
        self._smartcopy("deathdate")
        self._smartcopy("deathplace")
        self._smartcopy("deathplacecode")
        self._smartcopy("occupation")

    def from_geneanet(self, purl):
        ''' Delegate the actual page fetch/parse to the isolated scraper
        worker process (see worker/scraper.py, driven via
        state.get_worker_client()), and copy its result onto self.g_* -
        this keeps Selenium/lxml out of Gramps' own Python process. '''
        LOG.debug(_("Purl: %s"), purl)
        if not purl:
            return ()
        try:
            data = state.get_worker_client().scrape(purl, self._media_directory())
        except (GeneanetAccessError, ImportCancelled):
            # Always fatal: never continue parsing a page we could not
            # legitimately reach, as that produces phantom, nameless persons.
            raise
        except Exception as err:
            LOG.error(_("We failed to reach the server at %s"), purl, exc_info=True)
            report.current.failure("%s (%s)" % (purl, err))
            if state.stop_on_error:
                raise
        else:
            self.url = data['url']
            self.g_sex = data['g_sex']
            self.g_firstname = data['g_firstname']
            self.g_lastname = data['g_lastname']
            LOG.info(_("==> GENEANET Name (L%d): %s %s"), self.level, self.g_firstname, self.g_lastname)
            LOG.debug(_("Sex: %s"), self.g_sex)
            self.g_birthdate = data['g_birthdate']
            self.g_birthplace = data['g_birthplace']
            self.g_birthplacecode = data['g_birthplacecode']
            self.g_deathdate = data['g_deathdate']
            self.g_deathplace = data['g_deathplace']
            self.g_deathplacecode = data['g_deathplacecode']
            self.g_occupation = data.get('occupation')
            self.g_titles = data.get('titles') or []
            self.g_media = data.get('media') or []
            for error in data.get('media_errors') or []:
                report.current.media_failure(error)
            self.spouseref = data['spouseref']
            self.marriagedate = data['marriagedate']
            self.marriageplace = data['marriageplace']
            self.marriageplacecode = data['marriageplacecode']
            self.childref = data['childref']
            self.fref = data['fref']
            self.mref = data['mref']

    @staticmethod
    def _occupation_event(grampsp):
        """The first Occupation event of the person, or None."""
        for ref in grampsp.get_event_ref_list():
            event = state.db.get_event_from_handle(ref.ref)
            if event.get_type() == EventType.OCCUPATION:
                return event
        return None

    def _set_occupation_event(self, grampsp, tran):
        """The occupation is an Occupation event whose description is the text
        found on Geneanet, with no date and no place (Geneanet gives none).
        An existing Occupation event is updated, not duplicated."""
        event = self._occupation_event(grampsp)
        if event is None:
            event = Event()
            event.set_type(EventType(EventType.OCCUPATION))
            event.set_description(self.occupation)
            state.db.add_event(event, tran)
            ref = EventRef()
            ref.set_role(EventRoleType.PRIMARY)
            ref.set_reference_handle(event.get_handle())
            grampsp.add_event_ref(ref)
        else:
            event.set_description(self.occupation)
        state.db.commit_event(event, tran)

    def _add_title_events(self, grampsp, tran):
        """Each nobility title is a Nobility Title event whose description is
        the title, with no date and no place. A title the person already has
        is not added again."""
        known = set()
        for ref in grampsp.get_event_ref_list():
            event = state.db.get_event_from_handle(ref.ref)
            if event.get_type() == EventType.NOB_TITLE:
                known.add(event.get_description())
        for title in self.g_titles:
            if title in known:
                continue
            event = Event()
            event.set_type(EventType(EventType.NOB_TITLE))
            event.set_description(title)
            state.db.add_event(event, tran)
            ref = EventRef()
            ref.set_role(EventRoleType.PRIMARY)
            ref.set_reference_handle(event.get_handle())
            grampsp.add_event_ref(ref)
            state.db.commit_event(event, tran)
            known.add(title)
            LOG.info(_("Nobility title: %s"), title)

    @staticmethod
    def _media_directory():
        """Where the media files of this import are stored (and so where the
        worker downloads them): a Geneanet folder in the media base path of
        the tree. None when the media are not requested."""
        if not state.media:
            return None
        return os.path.join(media_path(state.db), MEDIA_SUBDIRECTORY)

    @staticmethod
    def _media_date(text):
        """A Gramps Date from "YYYY", "YYYY-MM" or "YYYY-MM-DD", else None."""
        match = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", (text or "").strip())
        if not match:
            return None
        year, month, day = (int(part) if part else 0 for part in match.groups())
        date = Date()
        date.set_yr_mon_day(year, month, day)
        return date

    def _attach_media(self, grampsp, tran):
        """Add the downloaded files to the person as Media objects. A file
        already known to the tree is reused, and one already attached to this
        person is left alone, so importing again adds nothing twice. The
        default photo of Geneanet goes first (the first media of a person is its
        portrait in Gramps)."""
        base = media_path(state.db)
        # Compared by full path: the tree may store the same file as a path
        # relative to the base path or as an absolute one.
        known = {os.path.normpath(media_path_full(state.db, media.get_path())): media
                 for media in state.db.iter_media()}
        attached = {ref.ref for ref in grampsp.get_media_list()}
        for item in sorted(self.g_media, key=lambda m: not m.get("is_default")):
            full = os.path.normpath(item["file"])
            media = known.get(full)
            if media is None:
                path = relative_path(item["file"], base)
                media = Media()
                media.set_path(path)
                media.set_mime_type(get_type(item["file"]))
                media.set_description(item.get("title") or os.path.basename(item["file"]))
                date = self._media_date(item.get("date"))
                if date:
                    media.set_date_object(date)
                state.db.add_media(media, tran)
                known[full] = media
                LOG.info(_("Adding media %s"), path)
            if media.get_handle() in attached:
                continue
            ref = MediaRef()
            ref.set_reference_handle(media.get_handle())
            grampsp.add_media_reference(ref)
            attached.add(media.get_handle())
            report.current.media_attached()

    def create_grampsp(self):
        with DbTxn(_("Geneanet import"), state.db) as tran:
            grampsp = Person()
            state.db.add_person(grampsp, tran)
            self.gid = grampsp.gramps_id
            self.grampsp = grampsp
            self.created = True
            LOG.info(_("Create new Gramps Person: %s (%s %s)"),
                     self.gid, self.g_firstname, self.g_lastname)

    def find_grampsp(self):
        # Fast path: match by the stored Geneanet URL (set by to_gramps) — unambiguous
        if self.url:
            for handle in state.db.get_person_handles():
                p = state.db.get_person_from_handle(handle)
                for u in p.get_url_list():
                    if u.get_path() == self.url:
                        self.grampsp = p
                        self.gid = p.gramps_id
                        LOG.debug(_("Found a Gramps Person by URL: %s %s (%s)"),
                                  self.g_firstname, self.g_lastname, self.gid)
                        return

        # Fallback: match by name + date. Only a certain match is used: two
        # persons with the same name and no date to tell them apart are not
        # assumed to be the same, nor is a name shared by several persons of
        # the tree whose dates all agree - merging homonyms gave the same
        # person several sets of parents.
        matches = []
        for i in state.db.get_person_gramps_ids():
            LOG.debug(_("Looking after %s"), i)
            p = state.db.get_person_from_gramps_id(i)
            try:
                name = p.primary_name.get_name().split(', ')
            except AttributeError:
                continue
            if len(name) == 0:
                continue
            elif len(name) == 1:
                name.append(None)
            lastname = name[0] if name[0] else ""
            firstname = name[1] if name[1] else ""
            if not same_name(firstname, self.g_firstname) or not same_name(lastname, self.g_lastname):
                continue
            self.grampsp = p
            bd = self.get_gramps_date(EventType.BIRTH)
            # Remove empty month/day if needed to compare below with just a year potentially
            bd = format_year(bd)
            dd = self.get_gramps_date(EventType.DEATH)
            dd = format_year(dd)
            LOG.debug(_("bd: %s vs g_bd: %s"), bd, self.g_birthdate)
            LOG.debug(_("dd: %s vs g_dd: %s"), dd, self.g_deathdate)
            if dates_identify(bd, self.g_birthdate, dd, self.g_deathdate):
                matches.append(p)

        self.grampsp = None
        if len(matches) == 1:
            self.grampsp = matches[0]
            self.gid = self.grampsp.gramps_id
            LOG.debug(_("Found a Gramps Person: %s %s (%s)"),
                      self.g_firstname, self.g_lastname, self.gid)
        elif matches:
            LOG.info(_("Several Gramps persons match %s %s, creating a new one"),
                     self.g_firstname, self.g_lastname)

    def to_gramps(self):
        self.smartcopy()

        with DbTxn(_("Geneanet import"), state.db) as tran:
            state.db.disable_signals()
            grampsp = self.grampsp
            if not grampsp:
                LOG.error(_("Unable to sync unknown Gramps Person"))
                return

            if self.sex == 'M':
                grampsp.set_gender(Person.MALE)
            elif self.sex == 'F':
                grampsp.set_gender(Person.FEMALE)
            else:
                grampsp.set_gender(Person.UNKNOWN)

            n = Name()
            n.set_type(NameType(NameType.BIRTH))
            n.set_first_name(self.firstname)
            s = n.get_primary_surname()
            s.set_surname(self.lastname)
            grampsp.set_primary_name(n)

            for ev in ['birth', 'death']:
                self.get_or_create_event(grampsp, ev, tran)

            if self.occupation:
                self._set_occupation_event(grampsp, tran)
                LOG.info(_("Occupation: %s"), self.occupation)

            self._add_title_events(grampsp, tran)

            if state.media and self.g_media:
                self._attach_media(grampsp, tran)

            # Store the importation place as an Internet note
            if self.url != "":
                found = False
                for u in grampsp.get_url_list():
                    if u.get_type() == UrlType.WEB_HOME and u.get_path() == self.url:
                        found = True
                if not found:
                    url = Url()
                    url.set_description(_("Imported from Geneanet"))
                    url.set_type(UrlType.WEB_HOME)
                    url.set_path(self.url)
                    grampsp.add_url(url)

            state.db.commit_person(grampsp, tran)
            state.db.enable_signals()
            state.db.request_rebuild()

    def from_gramps(self, gid):
        GENDER = ['F', 'M', 'U']

        LOG.debug(_("Calling from_gramps with gid: %s"), gid)

        if not gid and self.gid:
            gid = self.gid

        LOG.debug(_("Now gid is: %s"), gid)

        found = None
        try:
            found = state.db.get_person_from_gramps_id(gid)
            self.gid = gid
            self.grampsp = found
            if self.gid:
                LOG.debug(_("Existing Gramps Person: %s"), self.gid)
        except HandleError:
            LOG.warning(_("Unable to retrieve id %s from the gramps db %s"), gid, state.gname)

        if not found:
            self.find_grampsp()
            if self.grampsp is None:
                self.create_grampsp()

        if self.grampsp.gender:
            self.sex = GENDER[self.grampsp.gender]
            LOG.debug(_("Gender: %s"), self.sex)

        try:
            name = self.grampsp.primary_name.get_name().split(', ')
        except AttributeError:
            name = [None, None]

        if name[0]:
            self.firstname = name[1]
        if name[1]:
            self.lastname = name[0]
        LOG.debug(_("===> Gramps Name of %s: %s %s"), self.gid, self.firstname, self.lastname)

        try:
            bd = self.get_gramps_date(EventType.BIRTH)
            if bd:
                LOG.debug(_("Birth: %s"), bd)
                self.birthdate = bd
            else:
                LOG.debug(_("No Birth date"))
        except AttributeError:
            LOG.warning(_("Unable to retrieve birth date for id %s"), self.gid)

        try:
            dd = self.get_gramps_date(EventType.DEATH)
            if dd:
                LOG.debug(_("Death: %s"), dd)
                self.deathdate = dd
            else:
                LOG.debug(_("No Death date"))
        except AttributeError:
            LOG.warning(_("Unable to retrieve death date for id %s"), self.gid)

        event = self._occupation_event(self.grampsp)
        if event:
            self.occupation = event.get_description()

        # Deal with the parents now, as they necessarily exist
        self.father = GPerson(self.level + 1)
        self.mother = GPerson(self.level + 1)
        try:
            fh = self.grampsp.get_main_parents_family_handle()
            if fh:
                LOG.debug(_("Family: %s"), fh)
                fam = state.db.get_family_from_handle(fh)
                if fam:
                    fh = fam.get_father_handle()
                    if fh:
                        LOG.debug(_("Father H: %s"), fh)
                        father = state.db.get_person_from_handle(fh)
                        if father:
                            LOG.info(_("Father name: %s"), father.primary_name.get_name())
                            self.father.gid = father.gramps_id

                    mh = fam.get_mother_handle()
                    if mh:
                        LOG.debug(_("Mother H: %s"), mh)
                        mother = state.db.get_person_from_handle(mh)
                        if mother:
                            LOG.info(_("Mother name: %s"), mother.primary_name.get_name())
                            self.mother.gid = mother.gramps_id

        except (AttributeError, HandleError):
            LOG.debug(_("Unable to retrieve family for id %s"), self.gid)

    def add_spouses(self, level):
        # Local imports to break circular dependencies with gfamily and importer
        from src.gfamily import GFamily
        from src.importer import geneanet_to_gramps
        i = 0
        ret = []
        while i < len(self.spouseref):
            if not self.spouseref[i]:
                # Geneanet shows this spouse without a clickable profile
                # (private/hidden individual) - nothing we can fetch or
                # attach, so skip it instead of creating a nameless person.
                LOG.info(_("No navigable link for spouse %d of %s %s (private profile), skipping"),
                         i, self.firstname, self.lastname)
                report.current.skip(_("a spouse of %s %s") % (self.firstname, self.lastname))
                i = i + 1
                continue
            spouse = None
            for s in self.spouse:
                if s.url == self.spouseref[i]:
                    spouse = s
                    break
            if not spouse:
                partner = GPerson(level)
                spouse = geneanet_to_gramps(partner, level, None, self.spouseref[i])
                if spouse:
                    self.spouse.append(spouse)
                    spouse.spouse.append(self)
                elif partner.unknown:
                    # The family exists even if the partner is not known:
                    # it holds the children of the parent who is.
                    spouse = partner
                    LOG.debug(_("=> Initialize Family of %s %s & %s %s"),
                              self.firstname, self.lastname, spouse.firstname, spouse.lastname)
                if spouse is None:
                    # Not imported (conflict with the tree): no family.
                    i = i + 1
                    continue
                if self.sex == 'M':
                    f = GFamily(self, spouse)
                elif self.sex == 'F':
                    f = GFamily(spouse, self)
                else:
                    LOG.warning(_("Unable to Initialize Family of %s %s: sex unknown"),
                                self.firstname, self.lastname)
                    break

                f.from_geneanet()
                f.from_gramps(f.gid)
                f.to_gramps()
                self.family.append(f)
                if spouse:
                    spouse.family.append(f)
                ret.append(f)
            i = i + 1
        return ret

    def recurse_parents(self, level):
        # Local imports to break circular dependencies with gfamily and importer
        from src.gfamily import GFamily
        from src.importer import geneanet_to_gramps
        loop = False
        if self.unknown:
            return
        # Strict "<": level already reflects self's own generation, so
        # stop recursing further once self is at the requested depth -
        # otherwise one extra generation gets fetched (LEVEL=1 would
        # actually explore grandparents too).
        if level < state.LEVEL and (self.fref != "" or self.mref != ""):
            loop = True
            level = level + 1

            # self.father/self.mother are always non-None placeholders (set
            # in from_gramps), so guard on fref/mref - not on the object -
            # to know whether Geneanet actually gave us a navigable parent.
            # Fetching an empty ref creates a nameless "ghost" person that
            # still gets attached to the family below.
            # A parent that geneanet_to_gramps() does not import (it differs
            # from the person already in the tree: the conflict is in the
            # report) is left out entirely - no exploration of its own
            # ancestors, no link to the family - and the rest goes on.
            father_ok = mother_ok = False
            if self.fref:
                father_ok = geneanet_to_gramps(self.father, level, self.father.gid, self.fref) is not None
            if self.fref and father_ok:
                if self.mother:
                    self.mother.spouse.append(self.father)

                LOG.debug(_("=> Recursing on the parents of %s %s"), self.father.firstname, self.father.lastname)
                self.father.recurse_parents(level)
                LOG.debug(_("=> End of recursion on the parents of %s %s"), self.father.firstname, self.father.lastname)
            elif self.fref and self.father.unknown:
                LOG.info(_("The father is unknown, the family is created without him"))
            elif self.fref:
                LOG.info(_("The father was not imported (see the conflicts in the report), skipping"))
            else:
                LOG.info(_("No navigable link for the father (private profile), skipping"))
                report.current.skip(_("the father of %s %s") % (self.firstname, self.lastname))

            if self.mref:
                mother_ok = geneanet_to_gramps(self.mother, level, self.mother.gid, self.mref) is not None
            if self.mref and mother_ok:
                if self.father:
                    self.father.spouse.append(self.mother)
                LOG.debug(_("=> Recursing on the mother of %s %s"), self.mother.firstname, self.mother.lastname)
                self.mother.recurse_parents(level)
                LOG.debug(_("=> End of recursing on the mother of %s %s"), self.mother.firstname, self.mother.lastname)
            elif self.mref and self.mother.unknown:
                LOG.info(_("The mother is unknown, the family is created without her"))
            elif self.mref:
                LOG.info(_("The mother was not imported (see the conflicts in the report), skipping"))
            else:
                LOG.info(_("No navigable link for the mother (private profile), skipping"))
                report.current.skip(_("the mother of %s %s") % (self.firstname, self.lastname))

            # No family when neither parent was imported (it would be empty),
            # nor when one was left out because it differs from the person
            # already in the tree: that person already has its family there,
            # and a second one with only the other parent would link self to
            # two families.
            # An unknown parent is not a conflict: the family is created with
            # the other parent only.
            parent_left_out = bool(self.fref and not father_ok and not self.father.unknown
                                   or self.mref and not mother_ok and not self.mother.unknown)
            if (father_ok or mother_ok) and not parent_left_out:
                LOG.debug(_("=> Initialize Parents Family of %s %s"), self.firstname, self.lastname)
                f = GFamily(self.father, self.mother)
                f.from_geneanet()
                f.from_gramps(f.gid)
                f.to_gramps()
                if self.father:
                    self.father.family.append(f)
                if self.mother:
                    self.mother.family.append(f)

                if state.spouses:
                    if father_ok:
                        fam = self.father.add_spouses(level)
                        if state.ascendants:
                            for ff in fam:
                                if ff.gid != f.gid:
                                    ff.mother.recurse_parents(level)
                        if state.descendants:
                            for ff in fam:
                                if ff.gid != f.gid:
                                    ff.recurse_children(level)
                    if mother_ok:
                        fam = self.mother.add_spouses(level)
                        if state.ascendants:
                            for mf in fam:
                                if mf.gid != f.gid:
                                    mf.father.recurse_parents(level)
                        if state.descendants:
                            for mf in fam:
                                if mf.gid != f.gid:
                                    mf.recurse_children(level)

                # self is certainly a child of this family - we found father/
                # mother via self.fref/self.mref in the first place - so link it
                # directly instead of relying solely on recurse_children below
                # re-matching self by name/date among Geneanet's own child
                # listing, which can silently fail to recognize self and leave
                # it unlinked even though the family was created.
                f.add_child(self)
                if state.descendants:
                    f.recurse_children(level)

        if not loop:
            if level >= state.LEVEL:
                LOG.debug(_("Stopping exploration as we reached level %s"), level)
            else:
                LOG.info(_("Stopping exploration as there are no more parents"))
