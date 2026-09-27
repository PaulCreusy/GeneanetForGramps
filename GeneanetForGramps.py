#!/usr/bin/python3
#
# GeneanetForGramps
#
# Copyright (C) 2020-2021  Bruno Cornec
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the Affero GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

# $Id: $

"""
Geneanet Import Tool
Import into Gramps persons from Geneanet
"""
import os
import argparse
import sys
import time
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import src.state as state
from src.state import _
from src.importer import g2gaction

# Gramps plugin discovery requires these classes to be importable from this module
# (see GeneanetForGramps.gpr.py: toolclass/optionclass)
from src.gui import GeneanetForGramps, GeneanetForGrampsOptions  # noqa: F401

from gramps.gen.dbstate import DbState
from gramps.cli.grampscli import CLIManager



def main():

    parser = argparse.ArgumentParser(description=_(
        "Import Geneanet subtrees into Gramps"))
    parser.add_argument("-v", "--verbosity", action="count",
                        default=0, help=_("Increase verbosity"))
    parser.add_argument("-a", "--ascendants", default=False,
                        action='store_true', help=_("Includes ascendants (off by default)"))
    parser.add_argument("-d", "--descendants", default=False,
                        action='store_true', help=_("Includes descendants (off by default)"))
    parser.add_argument("-s", "--spouses", default=False, action='store_true',
                        help=_("Includes all spouses (off by default)"))
    parser.add_argument("-l", "--level", default=2, type=int,
                        help=_("Number of level to explore (2 by default)"))
    parser.add_argument("-g", "--grampsfile", type=str, help=_(
        "Full path of the Gramps database (under $HOME/.gramps/grampsdb)"))
    parser.add_argument("-i", "--id", type=str,
                        help=_("ID of the person to start from in Gramps"))
    parser.add_argument("-f", "--force", default=False,
                        action='store_true', help=_("Force processing"))
    parser.add_argument("-e", "--stop-on-error", default=False,
                        action='store_true', help=_("Stop at the first error instead of skipping it"))
    parser.add_argument("searchedperson", type=str, nargs='?', help=_(
        "Url of the person to search in Geneanet"))
    args = parser.parse_args()

    if args.searchedperson is None:
        print(_("Please provide a person to search for"))
        sys.exit(-1)
    purl = args.searchedperson

    state.gname = args.grampsfile
    state.verbosity = args.verbosity
    state.force = args.force
    state.stop_on_error = args.stop_on_error
    state.ascendants = args.ascendants
    state.descendants = args.descendants
    state.spouses = args.spouses
    state.LEVEL = args.level
    state.configure_logging()

    # TODO: do a backup before opening and remove fixed path
    if state.gname is None:
        print(_("Please provide a grampsfile to search into"))
        sys.exit(-1)
    try:
        dbstate = DbState()
        climanager = CLIManager(dbstate, True, None)
        climanager.open_activate(state.gname)
        state.db = dbstate.db
    except Exception as e:
        print(_("Opening the '%s' database failed: %s") % (state.gname, e))
        print(_("Perhaps it needs updating."))
        sys.exit(-1)

    gid = args.id
    if gid is None:
        gid = "0000"
    gid = "I" + gid

    ids = state.db.get_person_gramps_ids()
    for i in ids:
        state.LOG.debug(_("existing gramps id:") + i)

    if state.force:
        state.LOG.warning(_("Force mode activated"))
        time.sleep(state.TIMEOUT)

    g2gaction(gid, purl)

    state.db.close()
    sys.exit(0)


if __name__ == '__main__':
    main()
