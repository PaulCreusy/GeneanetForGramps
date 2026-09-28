# GeneanetForGramps - Selenium/lxml scraping, isolated in the worker process.
#
# This is the code that used to live directly in GBase/GPerson inside
# Gramps' own process. It now runs in a separate Python process (its own
# dedicated venv), so it never loads Selenium/lxml into Gramps' interpreter
# and a Chrome crash here cannot take Gramps down with it.
import logging
import random
import re
import socket
import tempfile
import time
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from lxml import html
from lxml.etree import ParserError, XMLSyntaxError, XPathEvalError

from src.constants import ROOTURL
from src.credentials import get_credentials, CREDENTIALS_FILE
from src.date_utils import format_ca, convert_date, geneanet_strings
from src.exceptions import GeneanetAccessError

LOG = logging.getLogger("GeneanetForGramps.worker")

# Mutable module-level state: this worker process handles exactly one
# scraping session, so a plain global (mirroring the old state.selenium_driver
# singleton) is enough - no need for a class here.
_driver = None
_profile_dir = None


def _free_tcp_port():
    """Ask the OS for a currently-unused local port, so each session gets
    its own remote-debugging port instead of a hardcoded one that can
    collide with other tools or a leftover process on the same port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get_driver():
    global _driver, _profile_dir
    if _driver is None:
        options = Options()
        options.binary_location = "/usr/bin/chromium-browser"
        # A dedicated, throwaway profile directory per session, so a
        # leftover process from an earlier run can never hold a lock on
        # the profile a fresh session tries to start against.
        _profile_dir = tempfile.mkdtemp(prefix="geneanetforgramps-chrome-")
        options.add_argument("--user-data-dir=" + _profile_dir)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=800,800")
        # An explicit --remote-debugging-port is required for the
        # chromedriver<->Chrome handshake to complete at all on some builds
        # (e.g. Ubuntu's snap-packaged chromium-browser, whose confinement
        # breaks the automatic port negotiation): without it,
        # webdriver.Chrome() hangs forever instead of raising. Picking a
        # fresh port per session (rather than a fixed one) avoids colliding
        # with other tools or an unrelated leftover process.
        options.add_argument("--remote-debugging-port=%d" % _free_tcp_port())
        # Hide automation indicators so Cloudflare allows manual checkbox clicks
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        _driver = webdriver.Chrome(options=options)
        # Remove the webdriver property from navigator to bypass Cloudflare detection
        _driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    return _driver


def close_driver():
    """Mirrors the previous state.close_selenium_driver(): always clears
    _driver even if quit() itself fails, then force-kills any leftover
    process still referencing our throwaway profile directory - some
    Chromium builds don't let chromedriver reliably track/kill the browser
    process it spawned, so quit() alone can leave a working window open."""
    global _driver, _profile_dir
    import shutil
    import subprocess
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            LOG.debug("Failed to close the Selenium browser cleanly", exc_info=True)
        _driver = None
    if _profile_dir is not None:
        try:
            subprocess.run(["pkill", "-9", "-f", _profile_dir], check=False)
        except FileNotFoundError:
            LOG.debug("pkill is not available to force-close a leftover browser process")
        shutil.rmtree(_profile_dir, ignore_errors=True)
        _profile_dir = None


def _do_login(driver, purl):
    """Fill the Geneanet login form with stored credentials then navigate to purl."""
    username, password = get_credentials()
    if not username:
        LOG.warning("No credentials found. Populate %s to enable auto-login:", CREDENTIALS_FILE)
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
            LOG.warning('Could not locate the username field on the Geneanet login page.')
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
            LOG.warning('Could not locate the password field on the Geneanet login page.')
            return False
        pass_field.clear()
        pass_field.send_keys(password)
        pass_field.submit()
        # Wait until the browser leaves the login page
        WebDriverWait(driver, 15).until(
            lambda d: 'connexion' not in d.current_url and 'login' not in d.current_url
        )
        LOG.info("Login successful.")
        driver.get(purl)
        time.sleep(3)
        # Geneanet sometimes bounces straight to the homepage right after
        # login instead of honoring the page we just requested - detect
        # that and re-issue the request for the originally targeted page.
        retries = 0
        while urlparse(driver.current_url).path in ('', '/') and retries < 3:
            LOG.info("Redirected to the Geneanet homepage after login, retrying %s.", purl)
            time.sleep(2)
            driver.get(purl)
            time.sleep(3)
            retries += 1
        return True
    except Exception:
        # Auto-login is best-effort: any unexpected failure here must not
        # crash the worker, so this catch stays broad - but log it so the
        # reason is not lost.
        LOG.debug("Auto-login failed", exc_info=True)
        return False


def scrape_person(purl):
    """Fetch and parse a Geneanet person page. Returns a plain dict of the
    fields the caller previously found on GPerson.g_* / spouseref / fref /
    mref / etc after from_geneanet(). Raises GeneanetAccessError for an
    unrecoverable access failure (Cloudflare timeout, failed login) and lets
    any other exception propagate as-is - the caller decides what to do
    with it (this mirrors the previous state.stop_on_error handling, which
    now lives on the Gramps side)."""
    LOG.info("Page considered: %s", purl)
    driver = get_driver()

    # Wait for the real page content to appear, tolerating a Cloudflare
    # challenge that can be shown more than once (e.g. a second checkbox
    # click) and a login/CAPTCHA redirect happening in between. Poll for
    # the actual target element instead of trusting the page title, which
    # is also localized (French on this site) and unreliable to match
    # reliably against a fixed set of English substrings.
    #
    # Some other, unrelated redirect page can also leave the browser stuck
    # (neither the person page, nor a recognizable Cloudflare/login page) -
    # observed ending an import outright. Rather than waiting on that one
    # navigation forever, the wait is split into bounded attempts that each
    # re-issue the request from scratch: a transient redirect quietly heals
    # itself on the next try instead of hard-failing the whole import.
    max_attempts = 3
    per_attempt_timeout = 60
    poll_interval = 2
    notice_shown = False
    login_attempted = False
    found = False
    for attempt in range(1, max_attempts + 1):
        driver.get(purl)
        elapsed = 0
        while elapsed < per_attempt_timeout:
            try:
                found = bool(driver.find_elements(By.ID, "person-title"))
                current_url = driver.current_url
            except WebDriverException:
                found, current_url = False, ""

            if found:
                break

            if ('connexion' in current_url or 'login' in current_url) and not login_attempted:
                login_attempted = True
                LOG.info("Geneanet login required for %s.", purl)
                if not _do_login(driver, purl):
                    raise GeneanetAccessError(
                        "Geneanet requires logging in (possibly behind a CAPTCHA) for %s, "
                        "and auto-login could not complete it." % purl)
                continue

            if not notice_shown:
                LOG.warning("Cloudflare verification detected. Please complete the challenge in the browser window.")
                notice_shown = True

            time.sleep(poll_interval)
            elapsed += poll_interval

        if found:
            break

        LOG.warning(
            "The page for %s did not resolve to a person page within %ds "
            "(attempt %d/%d, ended up on %s) - retrying with a fresh request.",
            purl, per_attempt_timeout, attempt, max_attempts, driver.current_url)

    if not found:
        raise GeneanetAccessError(
            "The page for %s never resolved to a person page after %d attempts "
            "(Cloudflare check likely still pending, or the site kept redirecting "
            "elsewhere)." % (purl, max_attempts))

    LOG.debug("URL: %s", driver.current_url)
    LOG.debug("Title: %s", driver.title)

    page_content = driver.page_source
    with open("/tmp/geneanet-selenium.html", "w", encoding="utf-8") as f:
        f.write(page_content)

    try:
        tree = html.fromstring(page_content)
    except (ParserError, XMLSyntaxError):
        LOG.error("Unable to perform HTML analysis")
        raise

    # The page's language is set by its own "lang=" URL parameter,
    # independent from whatever locale the caller (Gramps) runs in.
    page_lang = parse_qs(urlparse(purl).query).get('lang', ['fr'])[0]
    strings = geneanet_strings(page_lang)

    # Wait after a Geneanet request to be fair with the site
    # between 2 and 7 seconds
    time.sleep(random.randint(2, 7))

    data = {
        'url': purl,
        'g_sex': 'U',
        'g_firstname': "",
        'g_lastname': "",
        'g_birthdate': None,
        'g_birthplace': None,
        'g_birthplacecode': None,
        'g_deathdate': None,
        'g_deathplace': None,
        'g_deathplacecode': None,
        'spouseref': [],
        'marriagedate': [],
        'marriageplace': [],
        'marriageplacecode': [],
        'childref': [],
        'fref': "",
        'mref': "",
    }

    try:
        # Should return M or F
        sex = tree.xpath('//div[@id="person-title"]//img/attribute::alt')
        data['g_sex'] = sex[0]
        # Seems we have a french codification on the site
        if sex[0][0] == 'H':
            data['g_sex'] = 'M'
        elif sex[0][0] == 'F':
            data['g_sex'] = 'F'
    except IndexError:
        data['g_sex'] = 'U'
    try:
        name = tree.xpath('//span[@class="gw-individual-info-name-firstname"]//a/text()')
        data['g_firstname'] = " ".join(str(name[0]).split()).title()

        if data['g_firstname'] == "":
            LOG.warning("Name not detected, html has changed")

        name = tree.xpath('//span[@class="gw-individual-info-name-lastname"]//a/text()')
        data['g_lastname'] = " ".join(str(name[0]).split()).title()
    except IndexError:
        LOG.warning("Name not detected")
        data['g_firstname'] = ""
        data['g_lastname'] = ""
    LOG.info("==> GENEANET Name: %s %s", data['g_firstname'], data['g_lastname'])
    LOG.debug("Sex: %s", data['g_sex'])
    try:
        sstring = '//li[contains(., "' + strings['born'] + '")]/text()'
        LOG.debug("sstring: %s", sstring)
        birth = tree.xpath(sstring)
    except XPathEvalError:
        birth = [""]
    LOG.debug("birth: %s", birth)
    try:
        sstring = '//li[contains(., "' + strings['deceased'] + '")]/text()'
        LOG.debug("sstring: %s", sstring)
        death = tree.xpath(sstring)
    except XPathEvalError:
        death = [""]
    LOG.debug("death: %s", death)
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
        LOG.debug("Birth: %s", ld)
        data['g_birthdate'] = format_ca(ld, page_lang)
    except (IndexError, ValueError, AttributeError):
        LOG.debug("Error in birth date process", exc_info=True)
        data['g_birthdate'] = None
    try:
        data['g_birthplace'] = str(
            ' '.join(birth[0].split('-')[1:]).split(',')[0].strip()).title()
        LOG.debug("Birth place: %s", data['g_birthplace'])
    except (IndexError, AttributeError):
        data['g_birthplace'] = None
    try:
        g_birthplacecode = str(' '.join(birth[0].split('-')[1:]).split(',')[1]).strip()
        match = re.search(r'\d\d\d\d\d', g_birthplacecode)
        if not match:
            data['g_birthplacecode'] = None
        else:
            LOG.debug("Birth place code: %s", g_birthplacecode)
            data['g_birthplacecode'] = g_birthplacecode
    except (IndexError, AttributeError):
        data['g_birthplacecode'] = None
    try:
        ld = convert_date(death[0].split('-')[0].split()[1:], page_lang)
        LOG.debug("Death: %s", ld)
        data['g_deathdate'] = format_ca(ld, page_lang)
    except (IndexError, ValueError, AttributeError):
        data['g_deathdate'] = None
    try:
        data['g_deathplace'] = str(
            ' '.join(death[0].split('-')[1:]).split(',')[0]).strip().title()
        LOG.debug("Death place: %s", data['g_deathplace'])
    except (IndexError, AttributeError):
        data['g_deathplace'] = None
    try:
        g_deathplacecode = str(' '.join(death[0].split('-')[1:]).split(',')[1]).strip()
        match = re.search(r'\d\d\d\d\d', g_deathplacecode)
        if not match:
            data['g_deathplacecode'] = None
        else:
            LOG.debug("Death place code: %s", g_deathplacecode)
            data['g_deathplacecode'] = g_deathplacecode
    except (IndexError, AttributeError):
        data['g_deathplacecode'] = None

    s = 0
    sname = []
    sref = []
    marriage = []
    for spouse in spouses:
        # Pre-fill a slot for this spouse before looking for its <a> tag: a
        # fully private/hidden spouse has none at all, and without this,
        # sname[s]/sref[s] below would index past the end of the list and
        # crash.
        sname.append("")
        sref.append("")
        for a in spouse.xpath('a'):
            sosa = a.find('img')
            if sosa is None:
                try:
                    sname[s] = str(a.xpath('text()')[0]).title()
                    LOG.debug("Spouse name: %s", sname[s])
                except IndexError:
                    sname[s] = ""
                try:
                    sref[s] = str(a.xpath('attribute::href')[0])
                    LOG.debug("Spouse ref: %s", urljoin(ROOTURL, sref[s]))
                except IndexError:
                    sref[s] = ""

        # An empty href means Geneanet shows this spouse without a
        # clickable profile (private/hidden individual) - keep an empty
        # ref rather than fabricating a link to the site root.
        data['spouseref'].append(urljoin(ROOTURL, sref[s]) if sref[s] else "")

        try:
            marriage.append(str(spouse.xpath('em/text()')[0]))
        except IndexError:
            marriage.append(None)
        try:
            ld = convert_date(marriage[s].split(',')[0].split()[1:], page_lang)
            LOG.debug("Married: %s", ld)
            data['marriagedate'].append(format_ca(ld, page_lang))
        except (AttributeError, IndexError, ValueError):
            data['marriagedate'].append(None)
        try:
            data['marriageplace'].append(str(marriage[s].split(',')[1][1:]).title())
            LOG.debug("Married place: %s", data['marriageplace'][s])
        except (AttributeError, IndexError):
            data['marriageplace'].append(None)
        try:
            marriageplacecode = str(marriage[s].split(',')[2][1:])
            match = re.search(r'\d\d\d\d\d', marriageplacecode)
            if not match:
                data['marriageplacecode'].append(None)
            else:
                LOG.debug("Married place code: %s", marriageplacecode)
                data['marriageplacecode'].append(marriageplacecode)
        except (AttributeError, IndexError):
            data['marriageplacecode'].append(None)

        cnum = 0
        clist = []
        for c in spouse.xpath('ul/li'):
            # Reset for each child - a private/hidden child has no <a> at
            # all, and must not silently reuse the previous child's
            # name/ref (or leave cref undefined on the very first child of
            # the union).
            cname, cref = "", None
            for a in c.xpath('a'):
                sosa = a.find('img')
                if sosa is None:
                    try:
                        cname = c.xpath('a/text()')[0].title()
                        LOG.debug("Child %d name: %s", cnum, cname)
                    except IndexError:
                        cname = ""
                    try:
                        cref = urljoin(ROOTURL, str(a.xpath('attribute::href')[0]))
                        LOG.debug("Child %d ref: %s", cnum, cref)
                    except IndexError:
                        cref = None

            clist.append(cref)
            cnum = cnum + 1
        data['childref'].append(clist)
        s = s + 1
        # End spouse loop

    prefl = []
    for p in parents:
        LOG.debug("%s", p.xpath('text()'))
        texts = p.xpath('text()')
        if texts and texts[0] == '\n':
            # Reset for each parent entry - a private/hidden parent has no
            # <a> at all, and must not silently reuse the previous parent's
            # name/ref.
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
                ref = urljoin(ROOTURL, str(pref))
                LOG.info("Parent name: %s (%s)", pname, ref)
                prefl.append(ref)
            else:
                # Geneanet shows this parent without a clickable profile
                # (private/hidden individual) - keep the slot empty rather
                # than fabricating a link to the site root.
                LOG.info("Parent has no navigable link (private profile)")
                prefl.append("")
    try:
        data['fref'] = prefl[0]
    except IndexError:
        data['fref'] = ""
    try:
        data['mref'] = prefl[1]
    except IndexError:
        data['mref'] = ""

    return data
