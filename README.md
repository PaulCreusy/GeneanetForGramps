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
| Level of Import | How many generations to follow. Keep it small. |
| Force Import | Overwrite existing data instead of stopping on a conflict. |
| Verbosity | 0 (quiet) to 3 (very verbose), logged to the terminal Gramps was started from. |
| Geneanet username / password | Optional, see below. |

A progress window with a **Stop** button is shown during the import. Persons
already in your tree are detected by their Geneanet URL, then by name and
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
python3 GeneanetForGramps.py -g <family tree> -i <gramps id digits, e.g. 0001 for I0001> [-a] [-d] [-s] [-l LEVEL] [-f] [-v ...] <geneanet url>
```

`-a`/`-d`/`-s` include ascendants/descendants/spouses, `-l` is the depth,
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
python3 scripts/build_addon.py         # rebuild addons/gramps60 (package + per-language listings)
```

Rebuild and commit `addons/` whenever the code changes and a new version is
meant to be installable from the Addon Manager (and bump `version` in
`GeneanetForGramps.gpr.py` so Gramps offers it as an update).

## License

GNU General Public License v3 or later, see [LICENSE](LICENSE).
Originally written by Bruno Cornec.
