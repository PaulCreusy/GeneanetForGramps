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


def format_ca(date):
    if date[0:2] == "ca":
        date = _("about") + date[2:]
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


def convert_date(datetab):
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
    if (datetab[0][0:2] == _("about")[0:2] or datetab[0][0:2] == _("after")[0:2]
            or datetab[0][0:2] == _("before")[0:2]) and len(datetab) == 2:
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
