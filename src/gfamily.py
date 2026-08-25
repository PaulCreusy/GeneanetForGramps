# GeneanetForGramps - GFamily class
import src.state as state
from src.state import _
from src.gbase import GBase

from gramps.gen.db import DbTxn
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

        if state.verbosity >= 1:
            print(_("Creating GFamily: ") + father.firstname + " " +
                  father.lastname + " - " + mother.firstname + " " + mother.lastname)
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
            if state.verbosity >= 2:
                print(_("Create new Gramps Family: ") + self.gid)

    def find_grampsf(self):
        if state.verbosity >= 2:
            print(_("Look for a Gramps Family"))
        f = None
        ids = state.db.get_family_gramps_ids()
        for i in ids:
            f = state.db.get_family_from_gramps_id(i)
            if state.verbosity >= 3:
                print(_("Analysing Gramps Family ") + f.gramps_id)
            father = None
            fh = f.get_father_handle()
            if fh:
                father = state.db.get_person_from_handle(fh)
            mother = None
            mh = f.get_mother_handle()
            if mh:
                mother = state.db.get_person_from_handle(mh)
            if state.verbosity >= 3:
                fgid = father.gramps_id if father else "None"
                sfgid = self.father.gid if self.father.gid else "None"
                print(_("Check father ids: ") + fgid + _(" vs ") + sfgid)
                mgid = mother.gramps_id if mother else "None"
                smgid = self.mother.gid if self.mother.gid else "None"
                print(_("Check mother ids: ") + mgid + _(" vs ") + smgid)
            if self.father and father and father.gramps_id == self.father.gid \
                    and self.mother and mother and mother.gramps_id == self.mother.gid:
                return f
            # TODO: What about preexisting families not created in this run ?
        return None

    def from_geneanet(self):
        idx = 0
        for sr in self.father.spouseref:
            if state.verbosity >= 3:
                print(_("Comparing sr %s to %s (idx: %d)") % (sr, self.mother.url, idx))
            if sr == self.mother.url:
                if state.verbosity >= 2:
                    print(_("Spouse %s found (idx: %d)") % (sr, idx))
                break
            idx = idx + 1

        if idx < len(self.father.spouseref):
            self.g_marriagedate = self.father.marriagedate[idx]
            self.g_marriageplace = self.father.marriageplace[idx]
            self.g_marriageplacecode = self.father.marriageplacecode[idx]
            for c in self.father.childref[idx]:
                self.g_childref.append(c)

        if self.g_marriagedate and self.g_marriageplace and self.g_marriageplacecode:
            if state.verbosity >= 2:
                print(_("Geneanet Marriage found the %s at %s (%s)") % (
                    self.g_marriagedate, self.g_marriageplace, self.g_marriageplacecode))

    def from_gramps(self, gid):
        if state.verbosity >= 2:
            print(_("Calling from_gramps with gid: %s") % (gid))

        if not gid and self.gid:
            gid = self.gid

        if state.verbosity >= 2:
            print(_("Now gid is: %s") % (gid))

        found = None
        try:
            found = state.db.get_family_from_gramps_id(gid)
            self.gid = gid
            self.family = found
            if state.verbosity >= 2:
                print(_("Existing gid of a Gramps Family: %s") % (self.gid))
        except:
            if state.verbosity >= 1:
                print(_("WARNING: Unable to retrieve id %s from the gramps db %s") % (gid, state.gname))

        if not found:
            self.family = self.find_grampsf()
            if self.family:
                if state.verbosity >= 2:
                    print(_("Found an existing Gramps family ") + self.family.gramps_id)
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

            if state.verbosity >= 2:
                if self.marriagedate and self.marriageplace and self.marriageplacecode:
                    print(_("Gramps Marriage found the %s at %s (%s)") % (
                        self.marriagedate, self.marriageplace, self.marriageplacecode))

    def to_gramps(self):
        self.smartcopy()
        with DbTxn("Geneanet import", state.db) as tran:
            if self.family is None:
                self.family = Family()
                state.db.add_family(self.family, tran)

            try:
                grampsp0 = state.db.get_person_from_gramps_id(self.father.gid)
            except:
                if state.verbosity >= 2:
                    print(_("No father for this family"))
                grampsp0 = None

            if grampsp0:
                try:
                    self.family.set_father_handle(grampsp0.get_handle())
                except:
                    if state.verbosity >= 2:
                        print(_("Can't affect father to the family"))
                state.db.commit_family(self.family, tran)
                grampsp0.add_family_handle(self.family.get_handle())
                state.db.commit_person(grampsp0, tran)

            try:
                grampsp1 = state.db.get_person_from_gramps_id(self.mother.gid)
            except:
                if state.verbosity >= 2:
                    print(_("No mother for this family"))
                grampsp1 = None

            if grampsp1:
                try:
                    self.family.set_mother_handle(grampsp1.get_handle())
                except:
                    if state.verbosity >= 2:
                        print(_("Can't affect mother to the family"))
                state.db.commit_family(self.family, tran)
                grampsp1.add_family_handle(self.family.get_handle())
                state.db.commit_person(grampsp1, tran)

            self.get_or_create_event(self.family, 'marriage', tran)

    def smartcopy(self):
        if state.verbosity >= 2:
            print(_("Smart Copying Family"))
        self._smartcopy("marriagedate")
        self._smartcopy("marriageplace")
        self._smartcopy("marriageplacecode")

    def add_child(self, child):
        found = None
        for cr in self.family.get_child_ref_list():
            c = state.db.get_person_from_handle(cr.ref)
            if c.gramps_id == child.gid:
                found = child
                if state.verbosity >= 1:
                    print(_("Child already existing : ") + child.firstname + " " + child.lastname)
                break

        if not found:
            if child:
                if state.verbosity >= 2:
                    print(_("Adding child: ") + child.firstname + " " + child.lastname)
                childref = ChildRef()
                if child.grampsp:
                    try:
                        childref.set_reference_handle(child.grampsp.get_handle())
                    except:
                        if state.verbosity >= 2:
                            print(_("No handle for this child"))
                    self.family.add_child_ref(childref)
                    with DbTxn("Geneanet import", state.db) as tran:
                        state.db.commit_family(self.family, tran)
                        child.grampsp.add_parent_family_handle(self.family.get_handle())
                        state.db.commit_person(child.grampsp, tran)

    def recurse_children(self, level):
        # Local import to break the circular dependency with importer
        from src.importer import geneanet_to_gramps
        try:
            cpt = len(self.g_childref)
        except:
            if state.verbosity >= 1:
                print(_("Stopping exploration as there are no more children for family ") + self.fater.firstname +
                      " " + self.father.lastname + " - " + self.mother.firstname + " " + self.mother.lastname)
            return
        loop = False
        if level <= state.LEVEL and cpt > 0:
            loop = True
            level = level + 1

            if not self.family:
                print(_("WARNING: No family found whereas there should be one :-("))
                return

            for c in self.g_childref:
                child = geneanet_to_gramps(None, level - 1, None, c)
                if state.verbosity >= 2:
                    print(_("=> Recursion on the child of ") + self.father.lastname + ' - ' +
                          self.mother.lastname + ': ' + child.firstname + ' ' + child.lastname)
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

                if state.verbosity >= 2:
                    print(_("=> End of recursion on the child of ") + self.father.lastname +
                          ' - ' + self.mother.lastname + ': ' + child.firstname + ' ' + child.lastname)

        if not loop:
            if cpt == 0:
                if state.verbosity >= 1:
                    print(_("Stopping exploration for family ") + self.father.firstname + " " + self.father.lastname +
                          ' - ' + self.mother.firstname + " " + self.mother.lastname + _(" as there are no more children"))
                return

            if level > state.LEVEL:
                if state.verbosity >= 1:
                    print(_("Stopping exploration for family ") + self.father.firstname + " " + self.father.lastname +
                          ' - ' + self.mother.firstname + " " + self.mother.lastname + _(" as we reached level ") + str(level))
