# GeneanetForGramps - Date formatting and conversion helpers
import re
from datetime import date as _date

# strptime('%B') only works for the active C locale; use an explicit map instead
_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

import src.state as state
from src.state import _

# Geneanet page keywords, keyed by the page's own "lang=" URL parameter.
# These must NOT be derived from Gramps' UI locale (gettext _()): the page
# being scraped and the Gramps interface can be in two different languages,
# and matching against the wrong one silently finds nothing.
GENEANET_STRINGS = {
    'fr': {'born': 'Né', 'deceased': 'Décédé', 'about': 'vers', 'before': 'avant', 'after': 'après', 'in': 'en'},
    'en': {'born': 'Born', 'deceased': 'Deceased', 'about': 'about', 'before': 'before', 'after': 'after', 'in': 'in'},
}


def geneanet_strings(lang):
    return GENEANET_STRINGS.get(lang, GENEANET_STRINGS['fr'])


def format_ca(date, lang='fr'):
    if date and date[0:2] == "ca":
        date = geneanet_strings(lang)['about'] + date[2:]
    return date


def format_year(date):
    if not date:
        return date
    if date[-6:] == "-00-00":
        return date[0:-6]
    return date


def format_iso(date_tuple):
    year, month, day = date_tuple
    month = str(month).zfill(2)
    day = str(day).zfill(2)
    if year is None or year == 0:
        return ''
    elif month is None or month == 0:
        return str(year)
    elif day is None or day == 0:
        return '%s-%s' % (year, month)
    return '%s-%s-%s' % (year, month, day)


def format_noniso(date_tuple):
    day, month, year = date_tuple
    return (format_iso(year, month, day))


def convert_date(datetab, lang='fr'):
    strings = geneanet_strings(lang)
    if state.verbosity >= 3:
        print(_("datetab received:"), datetab)
    if len(datetab) == 0:
        return None
    idx = 0
    if datetab[0] == 'en':
        if datetab[1].isalpha():
            return datetab[2][0:4]
        elif datetab[1].isnumeric():
            return datetab[1][0:4]
    if (datetab[0][0:2] == strings['about'][0:2] or datetab[0][0:2] == strings['after'][0:2]
            or datetab[0][0:2] == strings['before'][0:2]) and len(datetab) == 2:
        return datetab[0] + " " + datetab[1][0:4]
    if datetab[0] == 'le':
        idx = 1
    if datetab[idx] == "1er":
        datetab[idx] = "1"
    day = int(datetab[idx])
    month = _MONTHS.get(datetab[idx + 1].lower())
    year = int(datetab[idx + 2][0:4])
    if not month:
        raise ValueError("Unknown month name: %s" % datetab[idx + 1])
    return _date(year, month, day).strftime("%Y-%m-%d")
