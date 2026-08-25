#!/usr/bin/env python3
"""
Standalone Geneanet HTML parsing debugger.
No Gramps or Selenium required — only lxml.

Usage:
    python3 test_parsing.py                        # reads /tmp/geneanet-selenium.html
    python3 test_parsing.py path/to/page.html
    python3 test_parsing.py page.html --lang en
"""
import sys
import re
import argparse
from datetime import datetime
from lxml import html

ROOTURL = 'https://gw.geneanet.org/'

# strptime('%B') only works for the active C locale; use an explicit map instead
_MONTHS = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

# Language-specific keyword strings (must match what the Gramps translation returns)
STRINGS = {
    'fr': {
        'born':     'Né',
        'deceased': 'Décédé',
        'about':    'vers',
        'before':   'avant',
        'after':    'après',
        'in':       'en',
    },
    'en': {
        'born':     'Born',
        'deceased': 'Deceased',
        'about':    'about',
        'before':   'before',
        'after':    'after',
        'in':       'in',
    },
}


# ---------------------------------------------------------------------------
# Standalone versions of src/date_utils helpers (no Gramps / state dependency)
# ---------------------------------------------------------------------------

def _format_ca(date, about_str):
    if date and date[0:2] == "ca":
        date = about_str + date[2:]
    return date


def _convert_date(datetab, strings):
    if len(datetab) == 0:
        return None
    idx = 0
    if datetab[0] == 'en':
        if len(datetab) > 1 and datetab[1].isalpha():
            return datetab[2][0:4] if len(datetab) > 2 else None
        elif len(datetab) > 1 and datetab[1].isnumeric():
            return datetab[1][0:4]
    ab, af, be = strings['about'], strings['after'], strings['before']
    if (datetab[0][0:2] in (ab[0:2], af[0:2], be[0:2])) and len(datetab) == 2:
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
    return datetime(year, month, day).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Parsing logic (mirrors src/gperson.py from_geneanet, raises instead of swallows)
# ---------------------------------------------------------------------------

def _parse_event(raw_list, strings):
    """Return (date, place, place_code) from a birth/death raw XPath list."""
    raw = raw_list[0] if raw_list else ""
    parts = raw.split('-')
    date_tokens = parts[0].split()[1:]
    ld = _convert_date(date_tokens, strings)
    date = _format_ca(ld, strings['about'])
    place = str(' '.join(parts[1:]).split(',')[0].strip()).title() if len(parts) > 1 else None
    try:
        code_str = str(' '.join(parts[1:]).split(',')[1]).strip()
        m = re.search(r'\d{5}', code_str)
        code = m.group(0) if m else None
    except IndexError:
        code = None
    return date, place, code


def parse_page(tree, lang='fr'):
    """
    Parse a Geneanet person page tree.
    Returns (fields dict, errors dict).
    Each entry in errors is {field_name: exception}.
    """
    s = STRINGS.get(lang, STRINGS['fr'])
    fields = {}
    errors = {}

    # --- Sex ---
    try:
        raw = tree.xpath('//div[@id="person-title"]//img/attribute::alt')
        fields['sex_raw'] = raw
        if raw:
            fields['sex'] = 'M' if raw[0][0] == 'H' else ('F' if raw[0][0] == 'F' else 'U')
        else:
            fields['sex'] = 'U'
    except Exception as e:
        fields['sex'] = 'U'
        errors['sex'] = e

    # --- Name ---
    try:
        raw = tree.xpath('//span[@class="gw-individual-info-name-firstname"]//a/text()')
        fields['firstname_raw'] = raw
        fields['firstname'] = " ".join(str(raw[0]).split()).title() if raw else ""
    except Exception as e:
        fields['firstname'] = ""
        errors['firstname'] = e

    try:
        raw = tree.xpath('//span[@class="gw-individual-info-name-lastname"]//a/text()')
        fields['lastname_raw'] = raw
        fields['lastname'] = " ".join(str(raw[0]).split()).title() if raw else ""
    except Exception as e:
        fields['lastname'] = ""
        errors['lastname'] = e

    # --- Birth ---
    born_xpath = '//li[contains(., "' + s['born'] + '")]/text()'
    try:
        birth_raw = tree.xpath(born_xpath)
        fields['birth_raw'] = birth_raw
    except Exception as e:
        birth_raw = []
        errors['birth_raw'] = e

    try:
        fields['birthdate'], fields['birthplace'], fields['birthplacecode'] = \
            _parse_event(birth_raw, s)
    except Exception as e:
        fields['birthdate'] = fields['birthplace'] = fields['birthplacecode'] = None
        errors['birth_parse'] = e

    # --- Death ---
    death_xpath = '//li[contains(., "' + s['deceased'] + '")]/text()'
    try:
        death_raw = tree.xpath(death_xpath)
        fields['death_raw'] = death_raw
    except Exception as e:
        death_raw = []
        errors['death_raw'] = e

    try:
        fields['deathdate'], fields['deathplace'], fields['deathplacecode'] = \
            _parse_event(death_raw, s)
    except Exception as e:
        fields['deathdate'] = fields['deathplace'] = fields['deathplacecode'] = None
        errors['death_parse'] = e

    # --- Parents ---
    parent_xpath = (
        '//ul[not(descendant-or-self::*[@class="fiche_union"])]'
        '//li[@style="vertical-align:middle;list-style-type:disc" or '
        '@style="vertical-align:middle;list-style-type:circle"]'
    )
    try:
        parent_nodes = tree.xpath(parent_xpath)
        parent_refs = []
        for p in parent_nodes:
            texts = p.xpath('text()')
            if not texts or texts[0] != '\n':
                continue
            for a in p.xpath('a'):
                if a.find('img') is not None:
                    continue
                pname = a.xpath('text()')[0].title() if a.xpath('text()') else ""
                pref  = a.xpath('attribute::href')[0] if a.xpath('attribute::href') else ""
                if pname and pref:
                    parent_refs.append({'name': pname, 'ref': ROOTURL + pref})
                    break
        fields['parents'] = parent_refs
    except Exception as e:
        fields['parents'] = []
        errors['parents'] = e

    # --- Spouses & children ---
    try:
        spouse_nodes = tree.xpath('//ul[@class="fiche_union"]/li')
        spouses = []
        for sp_node in spouse_nodes:
            sp = {'name': '', 'ref': '', 'marriage_raw': None, 'marriage_date': None,
                  'marriage_place': None, 'children': []}
            for a in sp_node.xpath('a'):
                if a.find('img') is not None:
                    continue
                sp['name'] = str(a.xpath('text()')[0]).title() if a.xpath('text()') else ""
                sp['ref']  = ROOTURL + str(a.xpath('attribute::href')[0]) \
                             if a.xpath('attribute::href') else ""
            em = sp_node.xpath('em/text()')
            if em:
                sp['marriage_raw'] = str(em[0])
                try:
                    tokens = sp['marriage_raw'].split(',')[0].split()[1:]
                    sp['marriage_date'] = _format_ca(_convert_date(tokens, s), s['about'])
                except Exception as e:
                    errors[f"marriage_date_{len(spouses)}"] = e
                try:
                    sp['marriage_place'] = str(sp['marriage_raw'].split(',')[1][1:]).title()
                except Exception:
                    pass
            for c_node in sp_node.xpath('ul/li'):
                for a in c_node.xpath('a'):
                    if a.find('img') is not None:
                        continue
                    cname = c_node.xpath('a/text()')[0].title() if c_node.xpath('a/text()') else ""
                    cref  = ROOTURL + str(a.xpath('attribute::href')[0]) \
                            if a.xpath('attribute::href') else None
                    sp['children'].append({'name': cname, 'ref': cref})
            spouses.append(sp)
        fields['spouses'] = spouses
    except Exception as e:
        fields['spouses'] = []
        errors['spouses'] = e

    return fields, errors


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def _fmt(val):
    if val is None:
        return "\033[33m(none)\033[0m"
    if val == "" or val == []:
        return "\033[33m(empty)\033[0m"
    return repr(val)


def print_report(fields, errors, lang, born_xpath, death_xpath):
    W = 18

    def row(label, key, raw_key=None):
        err = errors.get(key)
        val = fields.get(key)
        raw = fields.get(raw_key) if raw_key else None
        status = "\033[31mFAIL\033[0m" if err else "\033[32mOK  \033[0m"
        line = f"  {status} {label:<{W}} {_fmt(val)}"
        if raw is not None:
            line += f"\n       {'raw':<{W+5}} {_fmt(raw)}"
        if err:
            line += f"\n       {'error':<{W+5}} \033[31m{type(err).__name__}: {err}\033[0m"
        print(line)

    print(f"\n{'='*65}")
    print(f"  BASIC INFO  (lang={lang})")
    print(f"{'='*65}")
    row("sex",          'sex',       'sex_raw')
    row("firstname",    'firstname', 'firstname_raw')
    row("lastname",     'lastname',  'lastname_raw')

    print(f"\n{'='*65}")
    print(f"  BIRTH  (xpath: {born_xpath})")
    print(f"{'='*65}")
    row("raw",          'birth_raw')
    row("date",         'birthdate')
    row("place",        'birthplace')
    row("place code",   'birthplacecode')

    print(f"\n{'='*65}")
    print(f"  DEATH  (xpath: {death_xpath})")
    print(f"{'='*65}")
    row("raw",          'death_raw')
    row("date",         'deathdate')
    row("place",        'deathplace')
    row("place code",   'deathplacecode')

    print(f"\n{'='*65}")
    print("  PARENTS")
    print(f"{'='*65}")
    parents = fields.get('parents', [])
    if parents:
        roles = ['father', 'mother']
        for i, p in enumerate(parents):
            role = roles[i] if i < 2 else f"parent[{i}]"
            print(f"  \033[32mOK  \033[0m {role:<{W}} {p['name']!r}")
            print(f"       {'ref':<{W+5}} {p['ref']!r}")
    else:
        err = errors.get('parents')
        if err:
            print(f"  \033[31mFAIL\033[0m {'parents':<{W}} {type(err).__name__}: {err}")
        else:
            print(f"  \033[33m(none found)\033[0m")

    print(f"\n{'='*65}")
    print("  SPOUSES & CHILDREN")
    print(f"{'='*65}")
    spouses = fields.get('spouses', [])
    if spouses:
        for i, sp in enumerate(spouses):
            print(f"  Spouse [{i}]")
            print(f"    name         {sp['name']!r}")
            print(f"    ref          {sp['ref']!r}")
            print(f"    marriage_raw {_fmt(sp['marriage_raw'])}")
            print(f"    date         {_fmt(sp['marriage_date'])}")
            print(f"    place        {_fmt(sp['marriage_place'])}")
            mde = errors.get(f"marriage_date_{i}")
            if mde:
                print(f"    \033[31mdate error   {type(mde).__name__}: {mde}\033[0m")
            if sp['children']:
                for j, c in enumerate(sp['children']):
                    print(f"    child[{j}]      {c['name']!r}  ->  {c['ref']!r}")
            else:
                print("    (no children)")
    else:
        err = errors.get('spouses')
        if err:
            print(f"  \033[31mFAIL\033[0m {type(err).__name__}: {err}")
        else:
            print("  (none found)")

    if errors:
        print(f"\n{'='*65}")
        print("  ERROR SUMMARY")
        print(f"{'='*65}")
        for k, e in errors.items():
            print(f"  \033[31m{k:<22}\033[0m {type(e).__name__}: {e}")

    print(f"{'='*65}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Debug Geneanet HTML parsing — no Gramps or Selenium needed")
    parser.add_argument(
        "html_file", nargs="?", default="/tmp/geneanet-selenium.html",
        help="HTML file to parse (default: /tmp/geneanet-selenium.html, "
             "saved automatically by the importer on each page load)")
    parser.add_argument(
        "--lang", default="fr", choices=list(STRINGS.keys()),
        help="Language of the page (default: fr)")
    args = parser.parse_args()

    try:
        with open(args.html_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File not found: {args.html_file}")
        print("Run the importer once so it saves a page to /tmp/geneanet-selenium.html, "
              "then re-run this script.")
        sys.exit(1)

    tree = html.fromstring(content)
    s = STRINGS.get(args.lang, STRINGS['fr'])
    born_xpath  = '//li[contains(., "' + s['born']     + '")]/text()'
    death_xpath = '//li[contains(., "' + s['deceased'] + '")]/text()'

    fields, errors = parse_page(tree, lang=args.lang)
    print_report(fields, errors, args.lang, born_xpath, death_xpath)

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
