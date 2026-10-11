# GeneanetForGramps - GPerson class
import src.state as state
from src.state import _, LOG
from src.gbase import GBase
from src.date_utils import format_year
from src.exceptions import GeneanetAccessError

from gramps.gen.db import DbTxn
from gramps.gen.errors import HandleError
from gramps.gen.lib import Person, Name, NameType, EventType, Url, UrlType


class GPerson(GBase):

    def __init__(self, level):
        LOG.debug(_("Initialize Person at level %d"), level)
        self.level = level
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
        self.gid = None
        self.grampsp = None
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

    def from_geneanet(self, purl):
        ''' Delegate the actual page fetch/parse to the isolated scraper
        worker process (see worker/scraper.py, driven via
        state.get_worker_client()), and copy its result onto self.g_* -
        this keeps Selenium/lxml out of Gramps' own Python process. '''
        LOG.debug(_("Purl: %s"), purl)
        if not purl:
            return ()
        try:
            data = state.get_worker_client().scrape(purl)
        except GeneanetAccessError:
            # Always fatal: never continue parsing a page we could not
            # legitimately reach, as that produces phantom, nameless persons.
            raise
        except Exception:
            LOG.error(_("We failed to reach the server at %s"), purl, exc_info=True)
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
            self.spouseref = data['spouseref']
            self.marriagedate = data['marriagedate']
            self.marriageplace = data['marriageplace']
            self.marriageplacecode = data['marriageplacecode']
            self.childref = data['childref']
            self.fref = data['fref']
            self.mref = data['mref']

    def create_grampsp(self):
        with DbTxn("Geneanet import", state.db) as tran:
            grampsp = Person()
            state.db.add_person(grampsp, tran)
            self.gid = grampsp.gramps_id
            self.grampsp = grampsp
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

        # Fallback: match by name + date
        p = None
        ids = state.db.get_person_gramps_ids()
        for i in ids:
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
            self.grampsp = p
            bd = self.get_gramps_date(EventType.BIRTH)
            # Remove empty month/day if needed to compare below with just a year potentially
            bd = format_year(bd)
            dd = self.get_gramps_date(EventType.DEATH)
            dd = format_year(dd)
            LOG.debug(_("firstname: %s vs g_firstname: %s"), firstname, self.g_firstname)
            LOG.debug(_("lastname: %s vs g_lastname: %s"), lastname, self.g_lastname)
            LOG.debug(_("bd: %s vs g_bd: %s"), bd, self.g_birthdate)
            LOG.debug(_("dd: %s vs g_dd: %s"), dd, self.g_deathdate)
            if firstname != self.g_firstname or lastname != self.g_lastname:
                self.grampsp = None
                continue
            if not bd and not dd and not self.g_birthdate and not self.g_deathdate:
                # No dates on either side: accept the name match to avoid creating duplicates
                self.gid = p.gramps_id
                LOG.debug(_("Found a Gramps Person by name (no dates): %s %s (%s)"),
                          self.g_firstname, self.g_lastname, self.gid)
                break
            if bd == self.g_birthdate or dd == self.g_deathdate:
                self.gid = p.gramps_id
                LOG.debug(_("Found a Gramps Person: %s %s (%s)"),
                          self.g_firstname, self.g_lastname, self.gid)
                break
            else:
                self.grampsp = None

    def to_gramps(self):
        self.smartcopy()

        with DbTxn("Geneanet import", state.db) as tran:
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

            # Store the importation place as an Internet note
            if self.url != "":
                found = False
                for u in grampsp.get_url_list():
                    if u.get_type() == UrlType.WEB_HOME and u.get_path() == self.url:
                        found = True
                if not found:
                    url = Url()
                    url.set_description("Imported from Geneanet")
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
                i = i + 1
                continue
            spouse = None
            for s in self.spouse:
                if s.url == self.spouseref[i]:
                    spouse = s
                    break
            if not spouse:
                spouse = geneanet_to_gramps(None, level, None, self.spouseref[i])
                if spouse:
                    self.spouse.append(spouse)
                    spouse.spouse.append(self)
                    LOG.debug(_("=> Initialize Family of %s %s & %s %s"),
                              self.firstname, self.lastname, spouse.firstname, spouse.lastname)
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
            if self.fref:
                geneanet_to_gramps(self.father, level, self.father.gid, self.fref)
                if self.mother:
                    self.mother.spouse.append(self.father)

                LOG.debug(_("=> Recursing on the parents of %s %s"), self.father.firstname, self.father.lastname)
                self.father.recurse_parents(level)
                LOG.debug(_("=> End of recursion on the parents of %s %s"), self.father.firstname, self.father.lastname)
            else:
                LOG.info(_("No navigable link for the father (private profile), skipping"))

            if self.mref:
                geneanet_to_gramps(self.mother, level, self.mother.gid, self.mref)
                if self.father:
                    self.father.spouse.append(self.mother)
                LOG.debug(_("=> Recursing on the mother of %s %s"), self.mother.firstname, self.mother.lastname)
                self.mother.recurse_parents(level)
                LOG.debug(_("=> End of recursing on the mother of %s %s"), self.mother.firstname, self.mother.lastname)
            else:
                LOG.info(_("No navigable link for the mother (private profile), skipping"))

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
                fam = self.father.add_spouses(level)
                if state.ascendants:
                    for ff in fam:
                        if ff.gid != f.gid:
                            ff.mother.recurse_parents(level)
                if state.descendants:
                    for ff in fam:
                        if ff.gid != f.gid:
                            ff.recurse_children(level)
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
