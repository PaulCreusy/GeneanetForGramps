# GeneanetForGramps - GBase shared base class
import re
import time
from urllib.parse import urlparse

import src.state as state
from src.state import _, LOG
from src.date_utils import format_iso, format_noniso, geneanet_strings

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from gramps.gen.errors import HandleError
from gramps.gen.lib import (
    Event, EventType, Date, Place, EventRoleType, EventRef,
    PlaceName, FamilyRelType,
)


class GBase:

    def __init__(self):
        pass

    def get_selenium_driver(self):
        if state.selenium_driver is None:
            options = Options()
            options.binary_location = "/usr/bin/chromium-browser"
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--remote-debugging-port=9222")
            options.add_argument("--window-size=800,800")
            # Hide automation indicators so Cloudflare allows manual checkbox clicks
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            state.selenium_driver = webdriver.Chrome(options=options)
            # Remove the webdriver property from navigator to bypass Cloudflare detection
            state.selenium_driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        return state.selenium_driver

    def _do_login(self, driver, purl):
        """Fill the Geneanet login form with stored credentials then navigate to purl."""
        from src.credentials import get_credentials, CREDENTIALS_FILE
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        username, password = get_credentials()
        if not username:
            LOG.warning(_("No credentials found. Populate %s to enable auto-login:"), CREDENTIALS_FILE)
            LOG.warning("  [geneanet]")
            LOG.warning("  username = your@email.com")
            LOG.warning("  password = yourpassword")
            return False
        try:
            wait = WebDriverWait(driver, 10)
            # Geneanet (Symfony) uses _username/_password; fall back to type-based selectors
            user_field = None
            for sel in [(By.NAME, '_username'), (By.CSS_SELECTOR, 'input[type="email"]'), (By.NAME, 'email')]:
                try:
                    user_field = wait.until(EC.presence_of_element_located(sel))
                    break
                except TimeoutException:
                    pass
            if user_field is None:
                LOG.warning(_('Could not locate the username field on the Geneanet login page.'))
                return False
            user_field.clear()
            user_field.send_keys(username)
            pass_field = None
            for sel in [(By.NAME, '_password'), (By.CSS_SELECTOR, 'input[type="password"]')]:
                try:
                    pass_field = driver.find_element(*sel)
                    break
                except NoSuchElementException:
                    pass
            if pass_field is None:
                LOG.warning(_('Could not locate the password field on the Geneanet login page.'))
                return False
            pass_field.clear()
            pass_field.send_keys(password)
            pass_field.submit()
            # Wait until the browser leaves the login page
            WebDriverWait(driver, 15).until(
                lambda d: 'connexion' not in d.current_url and 'login' not in d.current_url
            )
            LOG.info(_("Login successful."))
            driver.get(purl)
            time.sleep(3)
            # Geneanet sometimes bounces straight to the homepage right
            # after login instead of honoring the page we just requested -
            # detect that and re-issue the request for the originally
            # targeted page.
            retries = 0
            while urlparse(driver.current_url).path in ('', '/') and retries < 3:
                LOG.info(_("Redirected to the Geneanet homepage after login, retrying %s."), purl)
                time.sleep(2)
                driver.get(purl)
                time.sleep(3)
                retries += 1
            return True
        except Exception:
            # Auto-login is best-effort: any unexpected failure here must
            # not crash the whole import, so this catch stays broad - but
            # log it so the reason is not lost.
            LOG.debug(_("Auto-login failed"), exc_info=True)
            return False

    def _smartcopy(self, attr):
        LOG.debug(_("Smart Copying Attributes %s"), attr)

        scopy = False

        if not self.__dict__[attr]:
            scopy = True

        if self.__dict__[attr] and self.__dict__[attr] == "" and self.__dict__['g_' + attr] and self.__dict__['g_' + attr] != "":
            scopy = True

        if self.__dict__[attr] != self.__dict__['g_' + attr] and state.force:
            scopy = True

        if attr == 'sex' and self.__dict__[attr] == 'U' and self.__dict__['g_' + attr] != 'U':
            scopy = True
            if (self.__dict__[attr] == 'F' and self.__dict__['g_' + attr] == 'M') \
                    or (self.__dict__[attr] == 'M' and self.__dict__['g_' + attr] == 'F'):
                LOG.warning(_("Gender conflict between Geneanet (%s) and Gramps (%s), keeping Gramps value"),
                            self.__dict__['g_' + attr], self.__dict__[attr])
                scopy = False

        if attr == 'lastname' and self.__dict__[attr] != self.__dict__['g_' + attr]:
            if self.__dict__[attr] != "":
                LOG.warning(_("Lastname conflict between Geneanet (%s) and Gramps (%s), keeping Gramps value"),
                            self.__dict__['g_' + attr], self.__dict__[attr])
        if attr == 'lastname' and self.__dict__[attr] == "":
            scopy = True

        if attr == 'firstname' and self.__dict__[attr] != self.__dict__['g_' + attr]:
            if self.__dict__[attr] != "":
                LOG.warning(_("Firstname conflict between Geneanet (%s) and Gramps (%s), keeping Gramps value"),
                            self.__dict__['g_' + attr], self.__dict__[attr])
        if attr == 'firstname' and self.__dict__[attr] == "":
            scopy = True

        match = re.search(r'code$', attr)
        if match:
            if not self.__dict__[attr]:
                scopy = True
            else:
                if not self.__dict__['g_' + attr]:
                    scopy = False
                else:
                    if int(self.__dict__[attr]) < int(self.__dict__['g_' + attr]):
                        scopy = True

        match = re.search(r'date$', attr)
        if match:
            if not self.__dict__[attr]:
                scopy = True
            else:
                if not self.__dict__['g_' + attr]:
                    scopy = False
                else:
                    if self.__dict__[attr] == "" and self.__dict__['g_' + attr] != "":
                        scopy = True
                    elif self.__dict__[attr] < self.__dict__['g_' + attr]:
                        scopy = True

        if scopy:
            LOG.info(_("Copying Person attribute %s (former value %s newer value %s)"),
                     attr, self.__dict__[attr], self.__dict__['g_' + attr])
            self.__dict__[attr] = self.__dict__['g_' + attr]
        else:
            LOG.debug(_("Not Copying Person attribute (%s, value %s) onto %s"),
                      attr, self.__dict__[attr], self.__dict__['g_' + attr])

    def get_or_create_place(self, event, placename):
        try:
            pl = event.get_place_handle()
        except AttributeError:
            return Place()

        if pl:
            try:
                place = state.db.get_place_from_handle(pl)
                LOG.debug(_("Reuse Place from Event: %s"), place.get_name().value)
            except HandleError:
                place = Place()
        else:
            if placename is None:
                return Place()
            keep = None
            for handle in state.db.get_place_handles():
                pl = state.db.get_place_from_handle(handle)
                explace = pl.get_name().value
                LOG.debug(_("search for %s in %s"), placename, explace)
                if str(explace) == str(placename):
                    keep = pl
                    break
            if keep is None:
                LOG.debug(_("Create Place: %s"), placename)
                place = Place()
            else:
                LOG.debug(_("Reuse existing Place: %s"), placename)
                place = keep
        return place

    def get_or_create_event(self, gobj, attr, tran):
        event = None
        if gobj.__class__.__name__ == 'Person':
            role = EventRoleType.PRIMARY
            func = getattr(gobj, 'get_' + attr + '_ref')
            reffunc = func()
            if reffunc:
                event = state.db.get_event_from_handle(reffunc.ref)
                LOG.debug(_("Existing %s Event"), attr)
        elif gobj.__class__.__name__ == 'Family':
            role = EventRoleType.FAMILY
            if attr == 'marriage':
                marev = None
                for event_ref in gobj.get_event_ref_list():
                    event = state.db.get_event_from_handle(event_ref.ref)
                    if (event.get_type() == EventType.MARRIAGE and
                            (event_ref.get_role() == EventRoleType.FAMILY or
                             event_ref.get_role() == EventRoleType.PRIMARY)):
                        marev = event
                if marev:
                    event = marev
                    LOG.debug(_("Existing %s Event"), attr)
        else:
            LOG.error(_("Unable to handle class %s in get_or_create_all_event"), gobj.__class__.__name__)

        if event is None:
            event = Event()
            uptype = getattr(EventType, attr.upper())
            event.set_type(EventType(uptype))
            event.set_description('Imported from Geaneanet')
            state.db.add_event(event, tran)

            eventref = EventRef()
            eventref.set_role(role)
            eventref.set_reference_handle(event.get_handle())
            if gobj.__class__.__name__ == 'Person':
                func = getattr(gobj, 'set_' + attr + '_ref')
                reffunc = func(eventref)
                state.db.commit_event(event, tran)
                state.db.commit_person(gobj, tran)
            elif gobj.__class__.__name__ == 'Family':
                eventref.set_role(EventRoleType.FAMILY)
                gobj.add_event_ref(eventref)
                if attr == 'marriage':
                    gobj.set_relationship(FamilyRelType(FamilyRelType.MARRIED))
                state.db.commit_event(event, tran)
                state.db.commit_family(gobj, tran)
            LOG.info(_("Creating %s (%s) Event"), attr, uptype)

        if self.__dict__[attr + 'date'] \
                or self.__dict__[attr + 'place'] \
                or self.__dict__[attr + 'placecode']:
            date = event.get_date_object()
            if self.__dict__[attr + 'date']:
                # The modifier prefix ("vers"/"about", "avant"/"before", ...)
                # was written by format_ca() using the GENEANET PAGE's own
                # language (see date_utils.geneanet_strings), not Gramps' UI
                # locale - so it must be recognized the same way here,
                # against every supported Geneanet language, regardless of
                # which one Gramps' gettext _() currently resolves to.
                prefix = self.__dict__[attr + 'date'][0:2]
                idx = 0
                mod = Date.MOD_NONE
                for lang_strings in (geneanet_strings('fr'), geneanet_strings('en')):
                    if prefix == lang_strings['about'][0:2]:
                        idx, mod = 1, Date.MOD_ABOUT
                        break
                    elif prefix == lang_strings['before'][0:2]:
                        idx, mod = 1, Date.MOD_BEFORE
                        break
                    elif prefix == lang_strings['after'][0:2]:
                        idx, mod = 1, Date.MOD_AFTER
                        break
                    elif prefix == lang_strings['in'][0:2]:
                        idx = 1
                        break
                if idx == 1:
                    string = self.__dict__[attr + 'date'].split(' ', 1)[1]
                else:
                    string = self.__dict__[attr + 'date']
                tab = string.split('-')
                if len(tab) == 3:
                    date.set_yr_mon_day(int(tab[0]), int(tab[1]), int(tab[2]))
                elif len(tab) == 2:
                    date.set_yr_mon_day(int(tab[0]), int(tab[1]), 0)
                elif len(tab) == 1:
                    date.set_year(int(tab[0]))
                elif len(tab) == 0:
                    LOG.warning(_("Trying to affect an empty date"))
                else:
                    LOG.warning(_("Trying to affect an extra numbered date"))
                if mod:
                    date.set_modifier(mod)
            if self.__dict__[attr + 'date']:
                LOG.info(_("Update %s Date to %s"), attr, self.__dict__[attr + 'date'])
            event.set_date_object(date)
            state.db.commit_event(event, tran)

            if self.__dict__[attr + 'place'] or self.__dict__[attr + 'placecode']:
                placename = self.__dict__[attr + 'place'] if self.__dict__[attr + 'place'] else ""
                place = self.get_or_create_place(event, placename)
                # TODO: Here we overwrite any existing value.
                place.set_name(PlaceName(value=placename))
                if self.__dict__[attr + 'placecode']:
                    place.set_code(self.__dict__[attr + 'placecode'])
                state.db.add_place(place, tran)
                event.set_place_handle(place.get_handle())
                state.db.commit_event(event, tran)

        state.db.commit_event(event, tran)

    def get_gramps_date(self, evttype):
        LOG.debug(_("EventType: %d"), evttype)

        if not self:
            return None

        if evttype == EventType.BIRTH:
            ref = self.grampsp.get_birth_ref()
        elif evttype == EventType.DEATH:
            ref = self.grampsp.get_death_ref()
        elif evttype == EventType.MARRIAGE:
            eventref = None
            for eventref in self.family.get_event_ref_list():
                event = state.db.get_event_from_handle(eventref.ref)
                if (event.get_type() == EventType.MARRIAGE
                    and (eventref.get_role() == EventRoleType.FAMILY
                         or eventref.get_role() == EventRoleType.PRIMARY)):
                    break
            ref = eventref
        else:
            LOG.error(_("Didn't find a known EventType: %s"), evttype)
            return None

        if not ref:
            return None

        LOG.debug(_("Ref: %s"), ref)
        try:
            event = state.db.get_event_from_handle(ref.ref)
        except HandleError:
            LOG.error(_("Didn't find a known ref for this ref date: %s"), ref)
            return None
        if not event:
            return None

        LOG.debug(_("Event: %s"), event)
        date = event.get_date_object()
        moddate = date.get_modifier()
        tab = date.get_dmy()
        LOG.debug(_("Found date: %s"), tab)
        if len(tab) == 3:
            tab = date.get_ymd()
            LOG.debug(_("Found date2: %s"), tab)
            ret = format_iso(tab)
        else:
            ret = format_noniso(tab)
        if moddate == Date.MOD_BEFORE:
            pref = _("before") + " "
        elif moddate == Date.MOD_AFTER:
            pref = _("after") + " "
        elif moddate == Date.MOD_ABOUT:
            pref = _("about") + " "
        else:
            pref = ""
        LOG.debug(_("Returned date: %s"), pref + ret)
        return pref + ret
