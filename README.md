# GeneanetForGramps

A [Gramps](https://gramps-project.org) tool that imports persons, families and
their ascendants / descendants / spouses from [Geneanet](https://www.geneanet.org)
into your family tree. It merges with what is already in your tree instead of
blindly duplicating it, and it can also be used as a standalone command-line script.

## Requirements

- **Gramps 6.0** (the packaged addon below targets 6.0).
- **Python 3 with the `venv` module**. On Debian/Ubuntu: `sudo apt install python3-venv`.
- **Chromium or Chrome**, installed at `/usr/bin/chromium-browser`.
- Network access on first run (to download Selenium and lxml).

You do **not** need to install Selenium or lxml in Gramps' own Python
environment: the addon creates and manages its own private environment (see
[How it works](#how-it-works)).

> **Snap-packaged Gramps is not supported**: the snap is strictly sandboxed, so it
> can neither build the addon's Python environment nor start your system's
> browser. Install Gramps with `apt` or `pip`/`pipx` instead.
>
> Flatpak-packaged Gramps is not supported out of the box: it cannot spawn the
> external Python environment and the browser the addon relies on. Use a
> native install, or grant the Flatpak the needed permissions (e.g. with Flatseal).

## Installation

### From Gramps' Addon Manager (recommended)

The addon is served from this repository as a third-party addon project.

1. In Gramps, open **Help ▸ Addon Manager**.
2. Open the **Projects** tab and click the **+** button.
3. Enter a name (e.g. `GeneanetForGramps`) and this URL:

   ```
   https://raw.githubusercontent.com/PaulCreusy/GeneanetForGramps/master/addons/gramps60
   ```

4. Go back to the **Addons** tab, select **All projects** (or the project you
   just added), pick **Import Geneanet data for Gramps** and click **Install**.
5. Restart Gramps. The tool then appears in the **Tools ▸ Family Tree Processing**
   menu.

Updates are offered by the Addon Manager when a newer version is published here.

### Manual installation

Copy this repository's contents into a `GeneanetForGramps` folder inside Gramps'
user plugins directory (e.g. `~/.gramps/gramps60/plugins/GeneanetForGramps/`),
then restart Gramps.

## First run

The first import creates a private Python environment in
`~/.local/share/geneanetforgramps/venv` and downloads Selenium and lxml into it
(a minute or so). This happens once, and again only if the addon's dependency
list changes.

## Usage (in Gramps)

Open **Tools ▸ Family Tree Processing ▸ Import Geneanet data for Gramps**.

| Option | Meaning |
| --- | --- |
| Center Person | The Gramps person the import starts from. |
| Geneanet URL for the selected person | The Geneanet page of that same person, e.g. `https://gw.geneanet.org/agnesy?lang=fr&n=queffelec&oc=17&p=marie+anne`. |
| Import ascendants / descendants / spouses | What to follow from the starting person. |
| Import media | Download the photos and documents attached to each person (see below). Off by default. |
| Level of Import | How many generations to follow. Keep it small. |
| Force Import | Overwrite existing data instead of stopping on a conflict. |
| Verbosity | 0 (quiet) to 3 (very verbose), logged to the terminal Gramps was started from. |
| Geneanet username / password | Optional, see below. |

The occupation shown on the Geneanet page, when there is one, is stored as an
**Occupation** event of the person (*Profession* in a French Gramps), whose description
is the text of Geneanet, for example `Cultivateur, garçon brasseur`. Geneanet gives no
date and no place for it, so the event has none. In a GEDCOM export it becomes an
`OCCU` line. An existing Occupation event is updated rather than duplicated, and its
text is only replaced when **Force Import** is enabled. (Versions 1.2 to 1.6 stored the
occupation in an *Occupation attribute* instead: those attributes are left as they are
in your tree and can be deleted by hand.)

**Import media** downloads the photos and documents listed in the "Photos et documents
d'archives" block of each person's page. The files are saved in a `Geneanet` folder inside
the *Base media path* of the tree (*Edit > Preferences > Family Tree*, or your Pictures
folder when there is none), named `<Geneanet id>_<title>.<extension>`, and
added to the person as media objects with the title and date of Geneanet; the default
photo of Geneanet comes first, which makes it the portrait. A file that is already there
is not downloaded again, and importing twice does not attach anything twice. The files are
fetched through the browser window, so this works behind Cloudflare and the login, but it can
make an import much longer. A file that cannot be downloaded is listed in the final summary.

A progress window is shown during the import. Its bar is an **estimate**: the size
of a Geneanet tree is unknown until it has been walked, so the total is projected
from the links found so far and the depth you chose, capped by the number of persons
of the whole tree (read once from the tree's home page when the import starts), and it is
refined after every
page (the bar never goes backwards, and stays under 100% until the end). Under the
bar you see the page count (`Page 12 of about 40`), the person being handled, what the
import is waiting for (for example the Cloudflare checkbox), the elapsed time and an
estimate of the remaining time. The window stays responsive while a page loads, and
its **Cancel** button stops the import right away, closing the browser.

When the import ends - finished, cancelled or stopped by an error - a summary window
lists what was done: pages processed and time taken, persons and families created
or already in the tree, the profiles skipped because Geneanet gives no link to them
(private profiles), the persons left untouched because of a conflict with your tree,
and the pages that could not be read. On the command line the same summary is
printed.

Persons already in your tree are detected by their Geneanet URL, then by name and
dates. If the same person differs between Gramps and Geneanet (name, birth or
death date), the import stops with an explanation unless **Force Import** is
enabled.

### Cloudflare check

Geneanet sits behind Cloudflare. A Chromium window opens during the import:
if a verification checkbox appears, tick it by hand in that window. The
import waits and resumes by itself. The window is closed when the import ends.

### Geneanet login

Some pages require a Geneanet account. Fill in **Geneanet username (email)**
and **Geneanet password** in the options: they are saved to
`~/.config/geneanetforgramps/credentials.ini` (owner read/write only, stored in
plain text) and used to log in automatically when Geneanet asks for it. Leaving
the password empty keeps the saved one. A CAPTCHA on the login page still has
to be solved by hand.

## Command line

The tool also runs outside the Gramps GUI against a database:

```
python3 GeneanetForGramps.py -g <family tree> -i <gramps id digits, e.g. 0001 for I0001> [-a] [-d] [-s] [-m] [-l LEVEL] [-f] [-v ...] <geneanet url>
```

`-a`/`-d`/`-s` include ascendants/descendants/spouses, `-m` downloads the media, `-l` is the depth,
`-f` forces overwrites, `-e` stops at the first error, and each `-v` raises the
verbosity. Credentials for the command line are read from the same
`credentials.ini` file (create it by hand):

```ini
[geneanet]
username = you@example.com
password = yourpassword
```

## How it works

Gramps loads addons into its own Python process, whose environment the addon
does not control. To avoid requiring Selenium inside it (and to keep a browser
crash away from Gramps), the work is split in two:

- **Inside Gramps** (`src/`): the merge logic, comparison with your tree and
  all database writes.
- **A worker process** (`worker/`): runs in the private virtual environment,
  drives the browser, parses Geneanet pages and sends the results back to
  Gramps as JSON. If it ever stops responding, it is terminated after a
  timeout instead of freezing Gramps.

## Translations

The interface is translated; Gramps picks the language of its own interface. French is
included, and any string without a translation is shown in English. The translations are
shipped in `locale/<lang>/LC_MESSAGES/addon.mo`, built from `po/<lang>.po`.

To fix or add a language (no gettext tools needed):

```
python3 scripts/i18n.py extract   # refresh po/template.pot from the source code
python3 scripts/i18n.py update    # add the new strings to every po/<lang>.po
# edit po/<lang>.po (to add a language: copy po/template.pot to po/<lang>.po first)
python3 scripts/i18n.py check     # untranslated strings, mismatched %s / %d placeholders
python3 scripts/i18n.py compile   # write locale/<lang>/LC_MESSAGES/addon.mo
```

Messages written for developers (`LOG.debug`) are not translated. Keep the placeholders
(`%s`, `%d`, `%(name)s`) of the English text in your translation; `check` reports any
difference. Run `python3 scripts/build_addon.py` afterwards to rebuild the package, which
also publishes the translated name and description to the Addon Manager.

## Troubleshooting

- **"ensurepip is not available"**: install the venv package, e.g.
  `sudo apt install python3-venv`.
- **The browser does not open**: check that Chromium is installed at
  `/usr/bin/chromium-browser`.
- **Geneanet import stopped, login required**: fill in the Geneanet login
  fields in the options (see above).
- For anything else, set **Verbosity** to 3 and read the terminal output.

## Development

```
python3 scripts/test_worker.py [URL]   # smoke-test the worker without Gramps
python3 scripts/build_addon.py         # compile translations, rebuild addons/gramps60 (package + per-language listings)
```

Rebuild and commit `addons/` whenever the code changes and a new version is
meant to be installable from the Addon Manager (and bump `version` in
`GeneanetForGramps.gpr.py` so Gramps offers it as an update).

## License

GNU General Public License v3 or later, see [LICENSE](LICENSE).
Originally written by Bruno Cornec.
