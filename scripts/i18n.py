#!/usr/bin/python3
"""Translation tooling for the addon, in pure Python (no gettext tools needed).

    python3 scripts/i18n.py extract   # source files -> po/template.pot
    python3 scripts/i18n.py update    # merge template.pot into every po/<lang>.po
    python3 scripts/i18n.py compile   # po/<lang>.po -> locale/<lang>/LC_MESSAGES/addon.mo
    python3 scripts/i18n.py check     # untranslated strings, broken placeholders

To add a language: copy po/template.pot to po/<lang>.po, fill in the header and
the msgstr entries, then run `compile`.

Strings are the ones wrapped in _("...") in the Python sources (and in the
.gpr.py registration). The addon's translations live in locale/ at the addon's
root, which is where Gramps looks for them (see src/state.py).
"""
import ast
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PO_DIR = os.path.join(ROOT, "po")
LOCALE_DIR = os.path.join(ROOT, "locale")
TEMPLATE = os.path.join(PO_DIR, "template.pot")
SOURCE_DIRS = ["src", "worker"]
# Wrapped in _() in the code but deliberately never translated: they are
# compared with, or used as keys for, other text (see src/gbase.py's
# get_gramps_date and the Gramps wiki page name in src/state.py).
NOT_TRANSLATED = {"before", "after", "about", "manual|GeneanetForGramps"}
SOURCE_FILES = ["GeneanetForGramps.py", "GeneanetForGramps.gpr.py"]

HEADER = """\
# %(lang_name)s translation for GeneanetForGramps.
# This file is distributed under the same license as the GeneanetForGramps package.
#
msgid ""
msgstr ""
"Project-Id-Version: GeneanetForGramps\\n"
"Report-Msgid-Bugs-To: \\n"
"Language: %(lang)s\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"""


# ---------------------------------------------------------------------------
# .po reading and writing
# ---------------------------------------------------------------------------

def _unquote(text):
    return ast.literal_eval(text)


def _quote(text):
    parts = text.split("\n")
    if len(parts) == 1:
        return '"%s"' % _escape(text)
    lines = ['""']
    for i, part in enumerate(parts):
        piece = part + ("\n" if i < len(parts) - 1 else "")
        if piece:
            lines.append('"%s"' % _escape(piece))
    return "\n".join(lines)


def _escape(text):
    return (text.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\t", "\\t"))


def read_po(path):
    """Return (header_lines, entries) where entries is a list of dicts with
    msgid, msgstr, comments (list of '#...' lines) and fuzzy."""
    entries, current, field = [], None, None
    comments = []

    def flush():
        nonlocal current
        if current is not None and (current["msgid"] or current["msgstr"]):
            entries.append(current)
        current = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("#"):
                if current is not None and field == "msgstr":
                    flush()
                    comments = []
                comments.append(line)
                continue
            if line.startswith("msgid "):
                flush()
                current = {"msgid": _unquote(line[6:]), "msgstr": "",
                           "comments": comments, "fuzzy": any("fuzzy" in c for c in comments)}
                comments, field = [], "msgid"
            elif line.startswith("msgstr "):
                current["msgstr"] = _unquote(line[7:])
                field = "msgstr"
            elif line.startswith('"') and current is not None:
                current[field] += _unquote(line)
            elif not line.strip():
                if current is not None and field == "msgstr":
                    flush()
                    field = None
    flush()
    return entries


def write_po(path, entries, lang=None, lang_name=None, header_text=None):
    with open(path, "w", encoding="utf-8") as f:
        if header_text is not None:
            f.write(header_text)
        else:
            f.write(HEADER % {"lang": lang or "", "lang_name": lang_name or "Template"})
        for entry in entries:
            f.write("\n")
            for comment in entry.get("comments", []):
                f.write(comment + "\n")
            if entry.get("fuzzy") and not any("fuzzy" in c for c in entry.get("comments", [])):
                f.write("#, fuzzy\n")
            f.write("msgid %s\n" % _quote(entry["msgid"]))
            f.write("msgstr %s\n" % _quote(entry["msgstr"]))


def header_of(path):
    """The file's header block (comments + the empty msgid entry), verbatim."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    marker = text.index('msgid ""')
    end = text.index("\n\n", marker) + 1 if "\n\n" in text[marker:] else len(text)
    return text[:end]


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def source_files():
    files = [os.path.join(ROOT, name) for name in SOURCE_FILES]
    for directory in SOURCE_DIRS:
        for base, dirs, names in os.walk(os.path.join(ROOT, directory)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            files += [os.path.join(base, n) for n in sorted(names) if n.endswith(".py")]
    return files


def extract_messages():
    """{msgid: [location, ...]} for every _("literal") call, in file order."""
    messages = {}
    for path in source_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        found = []
        # Developer-facing debug logging is not translated.
        skipped = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "debug"):
                for arg in node.args:
                    skipped.update(id(n) for n in ast.walk(arg))
        for node in ast.walk(tree):
            if id(node) in skipped:
                continue
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.append((node.lineno, node.args[0].value))
        for lineno, msgid in sorted(found):
            if msgid.strip() and msgid not in NOT_TRANSLATED:
                messages.setdefault(msgid, []).append(
                    "%s:%d" % (os.path.relpath(path, ROOT), lineno))
    return messages


def cmd_extract():
    messages = extract_messages()
    entries = [{"msgid": msgid, "msgstr": "",
                "comments": ["#: " + " ".join(locations[:4])]}
               for msgid, locations in messages.items()]
    write_po(TEMPLATE, entries, header_text=HEADER % {"lang": "", "lang_name": "Template"})
    print("%d messages written to %s" % (len(entries), os.path.relpath(TEMPLATE, ROOT)))


def po_files():
    return sorted(os.path.join(PO_DIR, n) for n in os.listdir(PO_DIR)
                  if n.endswith(".po") and not n.endswith("-local.po"))


def cmd_update():
    template = {e["msgid"]: e for e in read_po(TEMPLATE)}
    for path in po_files():
        old = {e["msgid"]: e for e in read_po(path)}
        entries, added = [], 0
        for msgid, tmpl in template.items():
            entry = dict(tmpl)
            if msgid in old:
                entry["msgstr"] = old[msgid]["msgstr"]
                entry["fuzzy"] = old[msgid]["fuzzy"]
            else:
                added += 1
            entries.append(entry)
        dropped = len([m for m in old if m not in template and m])
        write_po(path, entries, header_text=header_of(path))
        print("%s: %d entries, %d new, %d obsolete dropped" % (
            os.path.basename(path), len(entries), added, dropped))


# ---------------------------------------------------------------------------
# .mo compilation
# ---------------------------------------------------------------------------

def compile_mo(entries, header):
    """Binary catalog in the GNU .mo format."""
    messages = {"": header}
    for e in entries:
        if e["msgid"] and e["msgstr"] and not e["fuzzy"]:
            messages[e["msgid"]] = e["msgstr"]
    keys = sorted(messages)
    ids, strs, offsets = b"", b"", []
    for key in keys:
        kid, kstr = key.encode("utf-8"), messages[key].encode("utf-8")
        offsets.append((len(ids), len(kid), len(strs), len(kstr)))
        ids += kid + b"\0"
        strs += kstr + b"\0"
    count = len(keys)
    keystart = 7 * 4 + 16 * count
    valuestart = keystart + len(ids)
    table = []
    for o1, l1, o2, l2 in offsets:
        table += [l1, o1 + keystart]
    for o1, l1, o2, l2 in offsets:
        table += [l2, o2 + valuestart]
    out = struct.pack("Iiiiiii", 0x950412DE, 0, count, 7 * 4, 7 * 4 + count * 8, 0, 0)
    out += struct.pack("%di" % len(table), *table)
    return out + ids + strs


def header_msgstr(path):
    for e in read_po(path):
        if e["msgid"] == "" and e["msgstr"]:
            return e["msgstr"]
    return ""


def read_po_with_header(path):
    """Entries plus the header msgstr (read_po drops the empty msgid)."""
    header = ""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # The header is the first entry: msgid "" followed by a multi-line msgstr.
    match = re.search(r'msgid ""\s*\nmsgstr ""\s*\n((?:"[^\n]*"\s*\n)+)', text)
    if match:
        header = "".join(_unquote(l) for l in match.group(1).splitlines() if l.strip())
    return read_po(path), header


def cmd_compile():
    for path in po_files():
        lang = os.path.splitext(os.path.basename(path))[0]
        entries, header = read_po_with_header(path)
        target_dir = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES")
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, "addon.mo"), "wb") as f:
            f.write(compile_mo(entries, header))
        done = sum(1 for e in entries if e["msgstr"] and not e["fuzzy"])
        print("%s: %d/%d translated -> locale/%s/LC_MESSAGES/addon.mo" % (lang, done, len(entries), lang))


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"%(?:\([a-zA-Z_]+\))?[-+ 0#]*\d*(?:\.\d+)?[sdifrxXeEgG%]")


def placeholders(text):
    return sorted(p for p in _PLACEHOLDER.findall(text) if p != "%%")


def cmd_check():
    messages = extract_messages()
    problems = 0
    template = read_po(TEMPLATE)
    if {e["msgid"] for e in template if e["msgid"]} != set(messages):
        print("template.pot is out of date: run `extract`")
        problems += 1
    for path in po_files():
        name = os.path.basename(path)
        entries, _header = read_po_with_header(path)
        by_id = {e["msgid"]: e for e in entries}
        for msgid in messages:
            entry = by_id.get(msgid)
            if entry is None:
                print("%s: missing  %r" % (name, msgid)); problems += 1
            elif not entry["msgstr"]:
                print("%s: untranslated  %r" % (name, msgid)); problems += 1
            elif entry["fuzzy"]:
                print("%s: fuzzy  %r" % (name, msgid)); problems += 1
            elif placeholders(entry["msgstr"]) != placeholders(msgid):
                print("%s: placeholders differ\n    %r\n    %r" % (name, msgid, entry["msgstr"])); problems += 1
    print("check: %d problem(s)" % problems)
    return 1 if problems else 0


def main():
    commands = {"extract": cmd_extract, "update": cmd_update,
                "compile": cmd_compile, "check": cmd_check}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        return 2
    return commands[sys.argv[1]]() or 0


if __name__ == "__main__":
    sys.exit(main())
