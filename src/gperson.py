# GeneanetForGramps - GPerson class
import re
import time
import random
import traceback

import src.state as state
from src.state import _
from src.gbase import GBase
from src.date_utils import format_ca, format_year, convert_date

from lxml import html
from gramps.gen.db import DbTxn
from gramps.gen.lib import Person, Name, NameType, EventType, Url, UrlType


class GPerson(GBase):

    def __init__(self, level):
        if state.verbosity >= 3:
            print(_("Initialize Person at level %d") % (level))
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
        if state.verbosity >= 2:
            print(_("Smart Copying Person"), self.gid)
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
        ''' Use XPath to retrieve the details of a person
        Used example from https://gist.github.com/IanHopkinson/ad45831a2fb73f537a79
        and doc from https://www.w3schools.com/xml/xpath_axes.asp
        and https://docs.python-guide.org/scenarios/scrape/

        lxml can return _ElementUnicodeResult instead of str so cast
        '''
        if state.verbosity >= 3:
            print(_("Purl:"), purl)
        if not purl:
            return ()
        try:
            if state.verbosity >= 1:
                print("-----------------------------------------------------------")
                print(_("Page considered:"), purl)
            driver = self.get_selenium_driver()

            driver.get(purl)

            # Wait for Cloudflare challenge to be resolved (manually or automatically)
            cf_timeout = 120
            poll_interval = 2
            elapsed = 0
            while elapsed < cf_timeout:
                title = driver.title.lower()
                if "challenge" not in title and "just a moment" not in title and "attention required" not in title:
                    break
                if elapsed == 0:
                    print(_("Cloudflare verification detected. Please complete the challenge in the browser window."))
                time.sleep(poll_interval)
                elapsed += poll_interval
            else:
                print(_("Cloudflare challenge was not resolved within the timeout."))

            # Detect connexion/login redirect (includes view_limit_redirect) and auto-login
            if 'connexion' in driver.current_url or 'login' in driver.current_url:
                print(_("Geneanet login required for %s.") % purl)
                if not self._do_login(driver, purl):
                    return ()

            if state.verbosity >= 3:
                print(_("URL:"), driver.current_url)
                print(_("Title:"), driver.title)

            page_content = driver.page_source
            with open("/tmp/geneanet-selenium.html", "w", encoding="utf-8") as f:
                f.write(page_content)
        except Exception as e:
            print(_("We failed to reach the server at"), purl)
            print("Exception:", repr(e))
            traceback.print_exc()
            if state.stop_on_error:
                raise
        else:
            try:
                tree = html.fromstring(page_content)
            except:
                print(_("Unable to perform HTML analysis"))

            self.url = purl

            # Wait after a Geneanet request to be fair with the site
            # between 2 and 7 seconds
            time.sleep(random.randint(2, 7))
            try:
                # Should return M or F
                sex = tree.xpath('//div[@id="person-title"]//img/attribute::alt')
                self.g_sex = sex[0]
                # Seems we have a french codification on the site
                if sex[0][0] == 'H':
                    self.g_sex = 'M'
                elif sex[0][0] == 'F':
                    self.g_sex = 'F'
            except:
                self.g_sex = 'U'
            try:
                name = tree.xpath('//span[@class="gw-individual-info-name-firstname"]//a/text()')
                self.g_firstname = " ".join(str(name[0]).split()).title()

                if self.g_firstname == "":
                    print("Name not detected, html has changed")

                name = tree.xpath('//span[@class="gw-individual-info-name-lastname"]//a/text()')
                self.g_lastname = " ".join(str(name[0]).split()).title()
            except:
                print("Name not detected")
                self.g_firstname = ""
                self.g_lastname = ""
            if state.verbosity >= 1:
                print(_("==> GENEANET Name (L%d): %s %s") % (self.level, self.g_firstname, self.g_lastname))
            if state.verbosity >= 2:
                print(_("Sex:"), self.g_sex)
            try:
                sstring = '//li[contains(., "' + _("Born") + '")]/text()'
                if state.verbosity >= 3:
                    print("sstring: " + sstring)
                birth = tree.xpath(sstring)
            except:
                birth = [""]
            if state.verbosity >= 3:
                print(_("birth") + ": %s" % (birth))
            try:
                sstring = '//li[contains(., "' + _("Deceased") + '")]/text()'
                if state.verbosity >= 3:
                    print("sstring: " + sstring)
                death = tree.xpath(sstring)
            except:
                death = [""]
            if state.verbosity >= 3:
                print(_("death") + ": %s" % (death))
            try:
                # sometime parents are using circle, sometimes disc !
                parents = tree.xpath(
                    '//ul[not(descendant-or-self::*[@class="fiche_union"])]//li[@style="vertical-align:middle;list-style-type:disc" or @style="vertical-align:middle;list-style-type:circle"]')
            except:
                parents = []
            try:
                spouses = tree.xpath('//ul[@class="fiche_union"]/li')
            except:
                spouses = []
            try:
                ld = convert_date(birth[0].split('-')[0].split()[1:])
                if state.verbosity >= 2:
                    print(_("Birth:"), ld)
                self.g_birthdate = format_ca(ld)
                print("Birth after post:", ld)
            except:
                print("Error in birt date process")
                self.g_birthdate = None
            try:
                self.g_birthplace = str(
                    ' '.join(birth[0].split('-')[1:]).split(',')[0].strip()).title()
                if state.verbosity >= 2:
                    print(_("Birth place:"), self.g_birthplace)
            except:
                self.g_birthplace = None
            try:
                self.g_birthplacecode = str(
                    ' '.join(birth[0].split('-')[1:]).split(',')[1]).strip()
                match = re.search(r'\d\d\d\d\d', self.g_birthplacecode)
                if not match:
                    self.g_birthplacecode = None
                else:
                    if state.verbosity >= 2:
                        print(_("Birth place code:"), self.g_birthplacecode)
            except:
                self.g_birthplacecode = None
            try:
                ld = convert_date(death[0].split('-')[0].split()[1:])
                if state.verbosity >= 2:
                    print(_("Death:"), ld)
                self.g_deathdate = format_ca(ld)
            except:
                self.g_deathdate = None
            try:
                self.g_deathplace = str(
                    ' '.join(death[0].split('-')[1:]).split(',')[0]).strip().title()
                if state.verbosity >= 2:
                    print(_("Death place:"), self.g_deathplace)
            except:
                self.g_deathplace = None
            try:
                self.g_deathplacecode = str(
                    ' '.join(death[0].split('-')[1:]).split(',')[1]).strip()
                match = re.search(r'\d\d\d\d\d', self.g_deathplacecode)
                if not match:
                    self.g_deathplacecode = None
                else:
                    if state.verbosity >= 2:
                        print(_("Death place code:"), self.g_deathplacecode)
            except:
                self.g_deathplacecode = None

            s = 0
            sname = []
            sref = []
            marriage = []
            for spouse in spouses:
                for a in spouse.xpath('a'):
                    sosa = a.find('img')
                    if sosa is None:
                        try:
                            sname.append(str(a.xpath('text()')[0]).title())
                            if state.verbosity >= 2:
                                print(_("Spouse name:"), sname[s])
                        except:
                            sname.append("")
                        try:
                            sref.append(str(a.xpath('attribute::href')[0]))
                            if state.verbosity >= 2:
                                print(_("Spouse ref:"), state.ROOTURL + sref[s])
                        except:
                            sref.append("")

                self.spouseref.append(state.ROOTURL + sref[s])

                try:
                    marriage.append(str(spouse.xpath('em/text()')[0]))
                except:
                    marriage.append(None)
                try:
                    ld = convert_date(marriage[s].split(',')[0].split()[1:])
                    if state.verbosity >= 2:
                        print(_("Married:"), ld)
                    self.marriagedate.append(format_ca(ld))
                except:
                    self.marriagedate.append(None)
                try:
                    self.marriageplace.append(str(marriage[s].split(',')[1][1:]).title())
                    if state.verbosity >= 2:
                        print(_("Married place:"), self.marriageplace[s])
                except:
                    self.marriageplace.append(None)
                try:
                    marriageplacecode = str(marriage[s].split(',')[2][1:])
                    match = re.search(r'\d\d\d\d\d', marriageplacecode)
                    if not match:
                        self.marriageplacecode.append(None)
                    else:
                        if state.verbosity >= 2:
                            print(_("Married place code:"), self.marriageplacecode[s])
                        self.marriageplacecode.append(marriageplacecode)
                except:
                    self.marriageplacecode.append(None)

                cnum = 0
                clist = []
                for c in spouse.xpath('ul/li'):
                    for a in c.xpath('a'):
                        sosa = a.find('img')
                        if sosa is None:
                            try:
                                cname = c.xpath('a/text()')[0].title()
                                if state.verbosity >= 2:
                                    print(_("Child %d name: %s") % (cnum, cname))
                            except:
                                cname = ""
                            try:
                                cref = state.ROOTURL + str(a.xpath('attribute::href')[0])
                                if state.verbosity >= 2:
                                    print(_("Child %d ref: %s") % (cnum, cref))
                            except:
                                cref = None

                    clist.append(cref)
                    cnum = cnum + 1
                self.childref.append(clist)
                s = s + 1
                # End spouse loop

            self.fref = ""
            self.mref = ""
            prefl = []
            for p in parents:
                if state.verbosity >= 3:
                    print(p.xpath('text()'))
                if p.xpath('text()')[0] == '\n':
                    for a in p.xpath('a'):
                        sosa = a.find('img')
                        if sosa is None:
                            try:
                                pname = a.xpath('text()')[0].title()
                            except:
                                pname = ""
                            try:
                                pref = a.xpath('attribute::href')[0]
                            except:
                                pref = ""
                            # only consider first valid link instead of overwriting with eg "seigneur de XYZ" or "propriétaire à XYZ":
                            if pname and pref:
                                break

                    if state.verbosity >= 1:
                        print(_("Parent name: %s (%s)") % (pname, state.ROOTURL + pref))
                    prefl.append(state.ROOTURL + str(pref))
            try:
                self.fref = prefl[0]
            except:
                self.fref = ""
            try:
                self.mref = prefl[1]
            except:
                self.mref = ""
            if state.verbosity >= 2:
                print("-----------------------------------------------------------")

    def create_grampsp(self):
        with DbTxn("Geneanet import", state.db) as tran:
            grampsp = Person()
            state.db.add_person(grampsp, tran)
            self.gid = grampsp.gramps_id
            self.grampsp = grampsp
            if state.verbosity >= 1:
                print(_("Create new Gramps Person: ") + self.gid +
                      ' (' + self.g_firstname + ' ' + self.g_lastname + ')')

    def find_grampsp(self):
        # Fast path: match by the stored Geneanet URL (set by to_gramps) — unambiguous
        if self.url:
            for handle in state.db.get_person_handles():
                p = state.db.get_person_from_handle(handle)
                for u in p.get_url_list():
                    if u.get_path() == self.url:
                        self.grampsp = p
                        self.gid = p.gramps_id
                        if state.verbosity >= 2:
                            print(_("Found a Gramps Person by URL: ") + self.g_firstname +
                                  ' ' + self.g_lastname + " (" + self.gid + ")")
                        return

        # Fallback: match by name + date
        p = None
        ids = state.db.get_person_gramps_ids()
        for i in ids:
            if state.verbosity >= 3:
                print(_("DEBUG: Looking after ") + i)
            p = state.db.get_person_from_gramps_id(i)
            try:
                name = p.primary_name.get_name().split(', ')
            except:
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
            if state.verbosity >= 3:
                pbd = bd if bd else "None"
                pdd = dd if dd else "None"
                g_pbd = self.g_birthdate if self.g_birthdate else "None"
                g_pdd = self.g_deathdate if self.g_deathdate else "None"
                print(_("DEBUG: firstname: ") + firstname + _(" vs g_firstname: ") + self.g_firstname)
                print(_("DEBUG: lastname: ") + lastname + _(" vs g_lastname: ") + self.g_lastname)
                print(_("DEBUG: bd: ") + pbd + _(" vs g_bd: ") + g_pbd)
                print(_("DEBUG: dd: ") + pdd + _(" vs g_dd: ") + g_pdd)
            if firstname != self.g_firstname or lastname != self.g_lastname:
                self.grampsp = None
                continue
            if not bd and not dd and not self.g_birthdate and not self.g_deathdate:
                # No dates on either side: accept the name match to avoid creating duplicates
                self.gid = p.gramps_id
                if state.verbosity >= 2:
                    print(_("Found a Gramps Person by name (no dates): ") + self.g_firstname +
                          ' ' + self.g_lastname + " (" + self.gid + ")")
                break
            if bd == self.g_birthdate or dd == self.g_deathdate:
                self.gid = p.gramps_id
                if state.verbosity >= 2:
                    print(_("Found a Gramps Person: ") + self.g_firstname +
                          ' ' + self.g_lastname + " (" + self.gid + ")")
                break
            else:
                self.grampsp = None

    def to_gramps(self):
        self.smartcopy()

        with DbTxn("Geneanet import", state.db) as tran:
            state.db.disable_signals()
            grampsp = self.grampsp
            if not grampsp:
                if state.verbosity >= 2:
                    print(_("ERROR: Unable sync unknown Gramps Person"))
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

        if state.verbosity >= 2:
            print(_("Calling from_gramps with gid: %s") % (gid))

        if not gid and self.gid:
            gid = self.gid

        if state.verbosity >= 3:
            print(_("Now gid is: %s") % (gid))

        found = None
        try:
            found = state.db.get_person_from_gramps_id(gid)
            self.gid = gid
            self.grampsp = found
            if state.verbosity >= 2 and self.gid:
                print(_("Existing Gramps Person: %s") % (self.gid))
        except:
            if state.verbosity >= 1:
                print(_("WARNING: Unable to retrieve id %s from the gramps db %s") % (gid, state.gname))

        if not found:
            self.find_grampsp()
            if self.grampsp is None:
                self.create_grampsp()

        if self.grampsp.gender:
            self.sex = GENDER[self.grampsp.gender]
            if state.verbosity >= 2:
                print(_("Gender:"), self.sex)

        try:
            name = self.grampsp.primary_name.get_name().split(', ')
        except:
            name = [None, None]

        if name[0]:
            self.firstname = name[1]
        if name[1]:
            self.lastname = name[0]
        if state.verbosity >= 2:
            print(_("===> Gramps Name of %s: %s %s") % (self.gid, self.firstname, self.lastname))

        try:
            bd = self.get_gramps_date(EventType.BIRTH)
            if bd:
                if state.verbosity >= 2:
                    print(_("Birth:"), bd)
                self.birthdate = bd
            else:
                if state.verbosity >= 2:
                    print(_("No Birth date"))
        except:
            if state.verbosity >= 1:
                print(_("WARNING: Unable to retrieve birth date for id %s") % (self.gid))

        try:
            dd = self.get_gramps_date(EventType.DEATH)
            if dd:
                if state.verbosity >= 2:
                    print(_("Death:"), dd)
                self.deathdate = dd
            else:
                if state.verbosity >= 2:
                    print(_("No Death date"))
        except:
            if state.verbosity >= 1:
                print(_("WARNING: Unable to retrieve death date for id %s") % (self.gid))

        # Deal with the parents now, as they necessarily exist
        self.father = GPerson(self.level + 1)
        self.mother = GPerson(self.level + 1)
        try:
            fh = self.grampsp.get_main_parents_family_handle()
            if fh:
                if state.verbosity >= 3:
                    print(_("Family:"), fh)
                fam = state.db.get_family_from_handle(fh)
                if fam:
                    if state.verbosity >= 3:
                        print(_("Family:"), fam)

                    fh = fam.get_father_handle()
                    if fh:
                        if state.verbosity >= 3:
                            print(_("Father H:"), fh)
                        father = state.db.get_person_from_handle(fh)
                        if father:
                            if state.verbosity >= 1:
                                print(_("Father name:"), father.primary_name.get_name())
                            self.father.gid = father.gramps_id

                    mh = fam.get_mother_handle()
                    if mh:
                        if state.verbosity >= 3:
                            print(_("Mother H:"), mh)
                        mother = state.db.get_person_from_handle(mh)
                        if mother:
                            if state.verbosity >= 1:
                                print(_("Mother name:"), mother.primary_name.get_name())
                            self.mother.gid = mother.gramps_id

        except:
            if state.verbosity >= 1:
                print(_("NOTE: Unable to retrieve family for id %s") % (self.gid))

    def add_spouses(self, level):
        # Local imports to break circular dependencies with gfamily and importer
        from src.gfamily import GFamily
        from src.importer import geneanet_to_gramps
        i = 0
        ret = []
        while i < len(self.spouseref):
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
                    if state.verbosity >= 2:
                        print(_("=> Initialize Family of ") + self.firstname + " " +
                              self.lastname + " & " + spouse.firstname + " " + spouse.lastname)
                if self.sex == 'M':
                    f = GFamily(self, spouse)
                elif self.sex == 'F':
                    f = GFamily(spouse, self)
                else:
                    if state.verbosity >= 1:
                        print(_("Unable to Initialize Family of ") +
                              self.firstname + " " + self.lastname + _(" sex unknown"))
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
        if level <= state.LEVEL and (self.fref != "" or self.mref != ""):
            loop = True
            level = level + 1

            if self.father:
                geneanet_to_gramps(self.father, level, self.father.gid, self.fref)
                if self.mother:
                    self.mother.spouse.append(self.father)

                if state.verbosity >= 2:
                    print(_("=> Recursing on the parents of ") +
                          self.father.firstname + " " + self.father.lastname)
                self.father.recurse_parents(level)

                if state.verbosity >= 2:
                    print(_("=> End of recursion on the parents of ") +
                          self.father.firstname + " " + self.father.lastname)

            if self.mother:
                geneanet_to_gramps(self.mother, level, self.mother.gid, self.mref)
                if self.father:
                    self.father.spouse.append(self.mother)
                if state.verbosity >= 2:
                    print(_("=> Recursing on the mother of ") +
                          self.mother.firstname + " " + self.mother.lastname)
                self.mother.recurse_parents(level)

                if state.verbosity >= 2:
                    print(_("=> End of recursing on the mother of ") +
                          self.mother.firstname + " " + self.mother.lastname)

            if state.verbosity >= 2:
                print(_("=> Initialize Parents Family of ") + self.firstname + " " + self.lastname)
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

            if state.descendants:
                f.recurse_children(level)
            else:
                f.add_child(self)

        if not loop:
            if level > state.LEVEL:
                if state.verbosity >= 2:
                    print(_("Stopping exploration as we reached level ") + str(level))
            else:
                if state.verbosity >= 1:
                    print(_("Stopping exploration as there are no more parents"))
