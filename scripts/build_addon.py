#!/usr/bin/python3
"""Build the Gramps addon package and the listing that lets Gramps' Addon
Manager install it from this repository.

Output (committed, then served through raw.githubusercontent.com):
    addons/gramps<MAJOR><MINOR>/download/GeneanetForGramps.addon.tgz
    addons/gramps<MAJOR><MINOR>/listings/addons-<lang>.json

Usage:
    python3 scripts/build_addon.py [--gramps-version 6.0]
"""
import argparse
import json
import os
import sys
import tarfile
import types

import i18n

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = "GeneanetForGramps"
GPR_FILE = "GeneanetForGramps.gpr.py"

# Files shipped in the archive (relative to the repo root). Directories are
# included recursively, restricted to the listed extensions.
TOP_LEVEL_FILES = [
    GPR_FILE, "GeneanetForGramps.py", "GeneanetForGramps.png",
    "requirements-worker.txt", "README.md", "LICENSE",
]
TOOL_PTYPE = 2
# The Addon Manager hides, by default, every addon that is not "Stable"
# (s == 3) and "Everyone" (a == 0). Gramps fills in 0 for both when the keys
# are missing, which makes an unmarked addon silently invisible.
STATUS_STABLE = 3
AUDIENCE_EVERYONE = 0
# Gramps asks for listings/addons-<lang>.json, trying the full locale and
# then its two-letter prefix, per language of the user's locale list, and
# only then "en". Serving the same listing for every language Gramps
# supports (po/LINGUAS) avoids a 404 warning per language tried.
LANGUAGES = (
    "ar ba bg ca cs da de de_AT el en en_GB eo es fi fr ga he hr hu is it ja "
    "ko lt nb nl nn pl pt pt_BR pt_PT ru sk sl sq sr sv ta tr uk vi zh zh_CN "
    "zh_HK zh_TW"
).split()
PACKAGE_DIRS = ["src", "worker"]
TRANSLATION_FILES = "locale"
PACKAGE_EXTENSIONS = (".py",)


def read_gpr_metadata():
    """Execute the .gpr.py with a stub register() to read its metadata."""
    captured = {}

    def register(ptype, **kwargs):
        captured.update(kwargs)

    version_module = types.ModuleType("gramps.version")
    version_module.major_version = "0.0"
    sys.modules.setdefault("gramps", types.ModuleType("gramps"))
    sys.modules["gramps.version"] = version_module

    env = {
        "register": register, "_": lambda s: s, "TOOL": "Tool", "STABLE": "Stable",
        "TOOL_DBPROC": 0, "TOOL_MODE_GUI": 0,
    }
    with open(os.path.join(REPO_ROOT, GPR_FILE), encoding="utf-8") as f:
        exec(compile(f.read(), GPR_FILE, "exec"), env)
    return captured


def translated(lang, msgid):
    """The msgstr for msgid in po/<lang>.po (or its two-letter base), else None."""
    for code in (lang, lang.split("_")[0]):
        path = os.path.join(i18n.PO_DIR, code + ".po")
        if os.path.exists(path):
            for entry in i18n.read_po(path):
                if entry["msgid"] == msgid and entry["msgstr"] and not entry["fuzzy"]:
                    return entry["msgstr"]
    return None


def archive_members():
    members = [(name, name) for name in TOP_LEVEL_FILES]
    for base, dirs, files in os.walk(os.path.join(REPO_ROOT, TRANSLATION_FILES)):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith(".mo"):
                path = os.path.relpath(os.path.join(base, fname), REPO_ROOT)
                members.append((path, path))
    for package in PACKAGE_DIRS:
        for root, dirs, files in os.walk(os.path.join(REPO_ROOT, package)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for fname in sorted(files):
                if fname.endswith(PACKAGE_EXTENSIONS):
                    path = os.path.relpath(os.path.join(root, fname), REPO_ROOT)
                    members.append((path, path))
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gramps-version", default="6.0",
                        help="Gramps major.minor the package targets (default: 6.0)")
    args = parser.parse_args()

    major, minor = args.gramps_version.split(".")[:2]
    out_dir = os.path.join(REPO_ROOT, "addons", "gramps%s%s" % (major, minor))
    download_dir = os.path.join(out_dir, "download")
    listings_dir = os.path.join(out_dir, "listings")
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(listings_dir, exist_ok=True)

    i18n.cmd_compile()
    meta = read_gpr_metadata()
    tgz_name = "%s.addon.tgz" % ADDON_DIR

    def reset_owner(info):
        info.uname = info.gname = "gramps"
        info.uid = info.gid = 0
        info.mtime = 0
        return info

    with tarfile.open(os.path.join(download_dir, tgz_name), "w:gz") as tar:
        for src_path, arc_path in archive_members():
            tar.add(os.path.join(REPO_ROOT, src_path),
                    arcname=os.path.join(ADDON_DIR, arc_path), filter=reset_owner)

    def listing_for(lang):
        return [{
            # Gramps' PTYPE integer for a tool (gramps.gen.plug.TOOL == 2): the
            # Addon Manager indexes PTYPE_STR with this value, so a string such
            # as "Tool" raises KeyError when the addon list is displayed.
            "t": TOOL_PTYPE,
            "i": meta["id"],
            # Name and description are shown by the Addon Manager before the
            # addon is installed, so they are translated in the listing too.
            "n": translated(lang, meta["name"]) or meta["name"],
            "v": meta["version"],
            "g": args.gramps_version,
            "d": translated(lang, meta["description"]) or meta["description"],
            "z": tgz_name,
            "s": STATUS_STABLE,
            "a": AUDIENCE_EVERYONE,
        }]
    for lang in LANGUAGES:
        with open(os.path.join(listings_dir, "addons-%s.json" % lang), "w", encoding="utf-8") as f:
            json.dump(listing_for(lang), f, indent=2, ensure_ascii=False)
            f.write("\n")

    print("Built %s and the listings in %s" % (tgz_name, out_dir))


if __name__ == "__main__":
    main()
