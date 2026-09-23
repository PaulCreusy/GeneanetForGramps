# GeneanetForGramps - GPerson class
import re
import time
import random
from urllib.parse import urljoin, urlparse, parse_qs

import src.state as state
from src.state import _, LOG
from src.gbase import GBase
from src.date_utils import format_ca, format_year, convert_date, geneanet_strings
from src.exceptions import GeneanetAccessError

from lxml import html
from lxml.etree import ParserError, XMLSyntaxError, XPathEvalError
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
        ''' Use XPath to retrieve the details of a person
        Used example from https://gist.github.com/IanHopkinson/ad45831a2fb73f537a79
        and doc from https://www.w3schools.com/xml/xpath_axes.asp
        and https://docs.python-guide.org/scenarios/scrape/

        lxml can return _ElementUnicodeResult instead of str so cast
        '''
        LOG.debug(_("Purl: %s"), purl)
        if not purl:
            return ()
        try:
            LOG.info(_("Page considered: %s"), purl)
            driver = self.get_selenium_driver()

            driver.get(purl)

            # Wait for the real page content to appear, tolerating a
            # Cloudflare challenge that can be shown more than once (e.g. a
            # second checkbox click) and a login/CAPTCHA redirect happening
            # in between. Poll for the actual target element instead of
            # trusting the page title, which is also localized (French on
            # this site) and unreliable to match reliably against a fixed
            # set of English substrings.
            from selenium.webdriver.common.by import By
            from selenium.common.exceptions import WebDriverException

            total_timeout = 180
            poll_interval = 2
            elapsed = 0
            notice_shown = False
            login_attempted = False
            while True:
                try:
                    found = bool(driver.find_elements(By.ID, "person-title"))
                    current_url = driver.current_url
                except WebDriverException:
                    found, current_url = False, ""

                if found:
                    break

                if ('connexion' in current_url or 'login' in current_url) and not login_attempted:
                    login_attempted = True
                    LOG.info(_("Geneanet login required for %s."), purl)
                    if not self._do_login(driver, purl):
                        raise GeneanetAccessError(
                            _("Geneanet requires logging in (possibly behind a CAPTCHA) for %s, "
                              "and auto-login could not complete it.") % purl)
                    continue

                if not notice_shown:
                    LOG.warning(_("Cloudflare verification detected. Please complete the challenge in the browser window."))
                    notice_shown = True

                if elapsed >= total_timeout:
                    raise GeneanetAccessError(
                        _("The page for %s never finished loading real content "
                          "(Cloudflare check likely still pending).") % purl)

                time.sleep(poll_interval)
                elapsed += poll_interval

            LOG.debug(_("URL: %s"), driver.current_url)
            LOG.debug(_("Title: %s"), driver.title)

            page_content = driver.page_source
            with open("/tmp/geneanet-selenium.html", "w", encoding="utf-8") as f:
                f.write(page_content)
        except GeneanetAccessError:
            # Always fatal: never continue parsing a page we could not
            # legitimately reach, as that produces phantom, nameless persons.
            raise
        except Exception:
            LOG.error(_("We failed to reach the server at %s"), purl, exc_info=True)
            if state.stop_on_error:
                raise
        else:
            try:
                tree = html.fromstring(page_content)
            except (ParserError, XMLSyntaxError):
                LOG.error(_("Unable to perform HTML analysis"))

            self.url = purl

            # The page's language is set by its own "lang=" URL parameter,
            # independent from the Gramps UI locale (gettext _()) - do not
            # conflate the two or keyword matching silently finds nothing.
            page_lang = parse_qs(urlparse(purl).query).get('lang', ['fr'])[0]
            strings = geneanet_strings(page_lang)

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
            except IndexError:
                self.g_sex = 'U'
            try:
                name = tree.xpath('//span[@class="gw-individual-info-name-firstname"]//a/text()')
                self.g_firstname = " ".join(str(name[0]).split()).title()

                if self.g_firstname == "":
                    LOG.warning(_("Name not detected, html has changed"))

                name = tree.xpath('//span[@class="gw-individual-info-name-lastname"]//a/text()')
                self.g_lastname = " ".join(str(name[0]).split()).title()
            except IndexError:
                LOG.warning(_("Name not detected"))
                self.g_firstname = ""
                self.g_lastname = ""
            LOG.info(_("==> GENEANET Name (L%d): %s %s"), self.level, self.g_firstname, self.g_lastname)
            LOG.debug(_("Sex: %s"), self.g_sex)
            try:
                sstring = '//li[contains(., "' + strings['born'] + '")]/text()'
                LOG.debug("sstring: %s", sstring)
                birth = tree.xpath(sstring)
            except XPathEvalError:
                birth = [""]
            LOG.debug(_("birth: %s"), birth)
            try:
                sstring = '//li[contains(., "' + strings['deceased'] + '")]/text()'
                LOG.debug("sstring: %s", sstring)
                death = tree.xpath(sstring)
            except XPathEvalError:
                death = [""]
            LOG.debug(_("death: %s"), death)
            try:
                # sometime parents are using circle, sometimes disc !
                parents = tree.xpath(
                    '//ul[not(descendant-or-self::*[@class="fiche_union"])]//li[@style="vertical-align:middle;list-style-type:disc" or @style="vertical-align:middle;list-style-type:circle"]')
            except XPathEvalError:
                parents = []
            try:
                spouses = tree.xpath('//ul[@class="fiche_union"]/li')
            except XPathEvalError:
                spouses = []
            try:
                ld = convert_date(birth[0].split('-')[0].split()[1:], page_lang)
                LOG.debug(_("Birth: %s"), ld)
                self.g_birthdate = format_ca(ld, page_lang)
            except (IndexError, ValueError, AttributeError):
                LOG.debug(_("Error in birth date process"), exc_info=True)
                self.g_birthdate = None
            try:
                self.g_birthplace = str(
                    ' '.join(birth[0].split('-')[1:]).split(',')[0].strip()).title()
                LOG.debug(_("Birth place: %s"), self.g_birthplace)
            except (IndexError, AttributeError):
                self.g_birthplace = None
            try:
                self.g_birthplacecode = str(
                    ' '.join(birth[0].split('-')[1:]).split(',')[1]).strip()
                match = re.search(r'\d\d\d\d\d', self.g_birthplacecode)
                if not match:
                    self.g_birthplacecode = None
                else:
                    LOG.debug(_("Birth place code: %s"), self.g_birthplacecode)
            except (IndexError, AttributeError):
                self.g_birthplacecode = None
            try:
                ld = convert_date(death[0].split('-')[0].split()[1:], page_lang)
                LOG.debug(_("Death: %s"), ld)
                self.g_deathdate = format_ca(ld, page_lang)
            except (IndexError, ValueError, AttributeError):
                self.g_deathdate = None
            try:
                self.g_deathplace = str(
                    ' '.join(death[0].split('-')[1:]).split(',')[0]).strip().title()
                LOG.debug(_("Death place: %s"), self.g_deathplace)
            except (IndexError, AttributeError):
                self.g_deathplace = None
            try:
                self.g_deathplacecode = str(
                    ' '.join(death[0].split('-')[1:]).split(',')[1]).strip()
                match = re.search(r'\d\d\d\d\d', self.g_deathplacecode)
                if not match:
                    self.g_deathplacecode = None
                else:
                    LOG.debug(_("Death place code: %s"), self.g_deathplacecode)
            except (IndexError, AttributeError):
                self.g_deathplacecode = None

            s = 0
            sname = []
            sref = []
            marriage = []
            for spouse in spouses:
                # Pre-fill a slot for this spouse before looking for its <a>
                # tag: a fully private/hidden spouse has none at all, and
                # without this, sname[s]/sref[s] below would index past the
                # end of the list and crash.
                sname.append("")
                sref.append("")
                for a in spouse.xpath('a'):
                    sosa = a.find('img')
                    if sosa is None:
                        try:
                            sname[s] = str(a.xpath('text()')[0]).title()
                            LOG.debug(_("Spouse name: %s"), sname[s])
                        except IndexError:
                            sname[s] = ""
                        try:
                            sref[s] = str(a.xpath('attribute::href')[0])
                            LOG.debug(_("Spouse ref: %s"), urljoin(state.ROOTURL, sref[s]))
                        except IndexError:
                            sref[s] = ""

                # An empty href means Geneanet shows this spouse without a
                # clickable profile (private/hidden individual) - keep an
                # empty ref rather than fabricating a link to the site root.
                self.spouseref.append(urljoin(state.ROOTURL, sref[s]) if sref[s] else "")

                try:
                    marriage.append(str(spouse.xpath('em/text()')[0]))
                except IndexError:
                    marriage.append(None)
                try:
                    ld = convert_date(marriage[s].split(',')[0].split()[1:], page_lang)
                    LOG.debug(_("Married: %s"), ld)
                    self.marriagedate.append(format_ca(ld, page_lang))
                except (AttributeError, IndexError, ValueError):
                    self.marriagedate.append(None)
                try:
                    self.marriageplace.append(str(marriage[s].split(',')[1][1:]).title())
                    LOG.debug(_("Married place: %s"), self.marriageplace[s])
                except (AttributeError, IndexError):
                    self.marriageplace.append(None)
                try:
                    marriageplacecode = str(marriage[s].split(',')[2][1:])
                    match = re.search(r'\d\d\d\d\d', marriageplacecode)
                    if not match:
                        self.marriageplacecode.append(None)
                    else:
                        LOG.debug(_("Married place code: %s"), marriageplacecode)
                        self.marriageplacecode.append(marriageplacecode)
                except (AttributeError, IndexError):
                    self.marriageplacecode.append(None)

                cnum = 0
                clist = []
                for c in spouse.xpath('ul/li'):
                    # Reset for each child - a private/hidden child has no
                    # <a> at all, and must not silently reuse the previous
                    # child's name/ref (or leave cref undefined on the very
                    # first child of the union).
                    cname, cref = "", None
                    for a in c.xpath('a'):
                        sosa = a.find('img')
                        if sosa is None:
                            try:
                                cname = c.xpath('a/text()')[0].title()
                                LOG.debug(_("Child %d name: %s"), cnum, cname)
                            except IndexError:
                                cname = ""
                            try:
                                cref = urljoin(state.ROOTURL, str(a.xpath('attribute::href')[0]))
                                LOG.debug(_("Child %d ref: %s"), cnum, cref)
                            except IndexError:
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
                LOG.debug("%s", p.xpath('text()'))
                texts = p.xpath('text()')
                if texts and texts[0] == '\n':
                    # Reset for each parent entry - a private/hidden parent
                    # has no <a> at all, and must not silently reuse the
                    # previous parent's name/ref.
                    pname, pref = "", ""
                    for a in p.xpath('a'):
                        sosa = a.find('img')
                        if sosa is None:
                            try:
                                pname = a.xpath('text()')[0].title()
                            except IndexError:
                                pname = ""
                            try:
                                pref = a.xpath('attribute::href')[0]
                            except IndexError:
                                pref = ""
                            # only consider first valid link instead of overwriting with eg "seigneur de XYZ" or "propriétaire à XYZ":
                            if pname and pref:
                                break

                    if pref:
                        ref = urljoin(state.ROOTURL, str(pref))
                        LOG.info(_("Parent name: %s (%s)"), pname, ref)
                        prefl.append(ref)
                    else:
                        # Geneanet shows this parent without a clickable
                        # profile (private/hidden individual) - keep the
                        # slot empty rather than fabricating a link to the
                        # site root.
                        LOG.info(_("Parent has no navigable link (private profile)"))
                        prefl.append("")
            try:
                self.fref = prefl[0]
            except IndexError:
                self.fref = ""
            try:
                self.mref = prefl[1]
            except IndexError:
                self.mref = ""

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
