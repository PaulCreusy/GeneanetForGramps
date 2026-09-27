# GeneanetForGramps - GFamily class
import src.state as state
from src.state import _, LOG
from src.gbase import GBase

from gramps.gen.db import DbTxn
from gramps.gen.errors import HandleError
from gramps.gen.lib import Family, ChildRef, EventType, EventRoleType


class GFamily(GBase):

    def __init__(self, father, mother):
        # The 2 GPersons parents in this family should exist
        # and properties filled before we create the family
        # Gramps properties
        self.marriagedate = None
        self.marriageplace = None
        self.marriageplacecode = None
        self.gid = None
        # Pointer to the Gramps Family instance
        self.family = None
        # Geneanet properties
        self.g_marriagedate = None
        self.g_marriageplace = None
        self.g_marriageplacecode = None
        self.g_childref = []

        LOG.info(_("Creating GFamily: %s %s - %s %s"),
                 father.firstname, father.lastname, mother.firstname, mother.lastname)
        self.url = father.url
        if self.url == "":
            self.url = mother.url
        # TODO: what if father or mother is None
        self.father = father
        self.mother = mother

    def create_grampsf(self):
        with DbTxn("Geneanet import", state.db) as tran:
            grampsf = Family()
            state.db.add_family(grampsf, tran)
            self.gid = grampsf.gramps_id
            self.family = grampsf
            LOG.info(_("Create new Gramps Family: %s"), self.gid)

    def find_grampsf(self):
        LOG.debug(_("Look for a Gramps Family"))
        f = None
        ids = state.db.get_family_gramps_ids()
        for i in ids:
            f = state.db.get_family_from_gramps_id(i)
            LOG.debug(_("Analysing Gramps Family %s"), f.gramps_id)
            father = None
            fh = f.get_father_handle()
            if fh:
                father = state.db.get_person_from_handle(fh)
            mother = None
            mh = f.get_mother_handle()
            if mh:
                mother = state.db.get_person_from_handle(mh)
            LOG.debug(_("Check father ids: %s vs %s"),
                      father.gramps_id if father else "None", self.father.gid or "None")
            LOG.debug(_("Check mother ids: %s vs %s"),
                      mother.gramps_id if mother else "None", self.mother.gid or "None")
            if self.father and father and father.gramps_id == self.father.gid \
                    and self.mother and mother and mother.gramps_id == self.mother.gid:
                return f
            # TODO: What about preexisting families not created in this run ?
        return None

    def from_geneanet(self):
        idx = 0
        for sr in self.father.spouseref:
            LOG.debug(_("Comparing sr %s to %s (idx: %d)"), sr, self.mother.url, idx)
            if sr == self.mother.url:
                LOG.debug(_("Spouse %s found (idx: %d)"), sr, idx)
                break
            idx = idx + 1

        if idx < len(self.father.spouseref):
            self.g_marriagedate = self.father.marriagedate[idx]
            self.g_marriageplace = self.father.marriageplace[idx]
            self.g_marriageplacecode = self.father.marriageplacecode[idx]
            for c in self.father.childref[idx]:
                self.g_childref.append(c)

        if self.g_marriagedate and self.g_marriageplace and self.g_marriageplacecode:
            LOG.debug(_("Geneanet Marriage found the %s at %s (%s)"),
                      self.g_marriagedate, self.g_marriageplace, self.g_marriageplacecode)

    def from_gramps(self, gid):
        LOG.debug(_("Calling from_gramps with gid: %s"), gid)

        if not gid and self.gid:
            gid = self.gid

        LOG.debug(_("Now gid is: %s"), gid)

        found = None
        try:
            found = state.db.get_family_from_gramps_id(gid)
            self.gid = gid
            self.family = found
            LOG.debug(_("Existing gid of a Gramps Family: %s"), self.gid)
        except HandleError:
            LOG.warning(_("Unable to retrieve id %s from the gramps db %s"), gid, state.gname)

        if not found:
            self.family = self.find_grampsf()
            if self.family:
                LOG.debug(_("Found an existing Gramps family %s"), self.family.gramps_id)
                self.gid = self.family.gramps_id
            if self.family is None:
                self.create_grampsf()

        if self.family:
            self.marriagedate = self.get_gramps_date(EventType.MARRIAGE)
            if self.marriagedate == "":
                self.marriagedate = None
            for eventref in self.family.get_event_ref_list():
                event = state.db.get_event_from_handle(eventref.ref)
                if (event.get_type() == EventType.MARRIAGE
                    and (eventref.get_role() == EventRoleType.FAMILY
                         or eventref.get_role() == EventRoleType.PRIMARY)):
                    place = self.get_or_create_place(event, None)
                    self.marriageplace = place.get_name().value
                    self.marriageplacecode = place.get_code()
                    break

            if self.marriagedate and self.marriageplace and self.marriageplacecode:
                LOG.debug(_("Gramps Marriage found the %s at %s (%s)"),
                          self.marriagedate, self.marriageplace, self.marriageplacecode)

    def to_gramps(self):
        self.smartcopy()
        with DbTxn("Geneanet import", state.db) as tran:
            if self.family is None:
                self.family = Family()
                state.db.add_family(self.family, tran)

            try:
                grampsp0 = state.db.get_person_from_gramps_id(self.father.gid)
            except HandleError:
                LOG.debug(_("No father for this family"))
                grampsp0 = None

            if grampsp0:
                try:
                    self.family.set_father_handle(grampsp0.get_handle())
                except AttributeError:
                    LOG.debug(_("Can't affect father to the family"))
                state.db.commit_family(self.family, tran)
                grampsp0.add_family_handle(self.family.get_handle())
                state.db.commit_person(grampsp0, tran)

            try:
                grampsp1 = state.db.get_person_from_gramps_id(self.mother.gid)
            except HandleError:
                LOG.debug(_("No mother for this family"))
                grampsp1 = None

            if grampsp1:
                try:
                    self.family.set_mother_handle(grampsp1.get_handle())
                except AttributeError:
                    LOG.debug(_("Can't affect mother to the family"))
                state.db.commit_family(self.family, tran)
                grampsp1.add_family_handle(self.family.get_handle())
                state.db.commit_person(grampsp1, tran)

            self.get_or_create_event(self.family, 'marriage', tran)

    def smartcopy(self):
        LOG.debug(_("Smart Copying Family"))
        self._smartcopy("marriagedate")
        self._smartcopy("marriageplace")
        self._smartcopy("marriageplacecode")

    def add_child(self, child):
        found = None
        for cr in self.family.get_child_ref_list():
            c = state.db.get_person_from_handle(cr.ref)
            if c.gramps_id == child.gid:
                found = child
                LOG.info(_("Child already existing : %s %s"), child.firstname, child.lastname)
                break

        if not found:
            if child:
                LOG.debug(_("Adding child: %s %s"), child.firstname, child.lastname)
                childref = ChildRef()
                if child.grampsp:
                    try:
                        childref.set_reference_handle(child.grampsp.get_handle())
                    except AttributeError:
                        LOG.debug(_("No handle for this child"))
                    self.family.add_child_ref(childref)
                    with DbTxn("Geneanet import", state.db) as tran:
                        state.db.commit_family(self.family, tran)
                        child.grampsp.add_parent_family_handle(self.family.get_handle())
                        state.db.commit_person(child.grampsp, tran)

    def recurse_children(self, level):
        # Local import to break the circular dependency with importer
        from src.importer import geneanet_to_gramps
        # self.g_childref always exists (set to [] in __init__), so this
        # never actually raises - the length is always defined.
        cpt = len(self.g_childref)
        loop = False
        # Strict "<": level reflects how many generations of descent already
        # led to this family, so stop recursing into a child's own family
        # once that count reaches the requested depth - otherwise one extra
        # generation gets fetched (LEVEL=1 would actually explore
        # grandchildren too).
        if level < state.LEVEL and cpt > 0:
            loop = True
            level = level + 1

            if not self.family:
                LOG.error(_("No family found whereas there should be one :-("))
                return

            for c in self.g_childref:
                if not c:
                    # Geneanet shows this child without a clickable profile
                    # (private/hidden individual) - nothing we can fetch or
                    # attach, so skip it instead of creating a nameless
                    # person.
                    LOG.info(_("No navigable link for a child of %s %s - %s %s (private profile), skipping"),
                              self.father.firstname, self.father.lastname,
                              self.mother.firstname, self.mother.lastname)
                    continue
                child = geneanet_to_gramps(None, level - 1, None, c)
                LOG.debug(_("=> Recursion on the child of %s - %s: %s %s"),
                          self.father.lastname, self.mother.lastname, child.firstname, child.lastname)
                self.add_child(child)

                fam = []
                if state.spouses:
                    fam = child.add_spouses(level)
                    if state.ascendants:
                        for f in fam:
                            if child.sex == 'M':
                                f.mother.recurse_parents(level - 1)
                            if child.sex == 'F':
                                f.father.recurse_parents(level - 1)
                    if state.descendants:
                        for f in fam:
                            f.recurse_children(level)

                LOG.debug(_("=> End of recursion on the child of %s - %s: %s %s"),
                          self.father.lastname, self.mother.lastname, child.firstname, child.lastname)

        if not loop:
            if cpt == 0:
                LOG.info(_("Stopping exploration for family %s %s - %s %s as there are no more children"),
                         self.father.firstname, self.father.lastname,
                         self.mother.firstname, self.mother.lastname)
                return

            if level >= state.LEVEL:
                LOG.info(_("Stopping exploration for family %s %s - %s %s as we reached level %s"),
                         self.father.firstname, self.father.lastname,
                         self.mother.firstname, self.mother.lastname, level)
