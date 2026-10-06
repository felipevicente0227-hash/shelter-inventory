# Shelter Inventory Manager

A free, simple program for shelters, food banks and small charities that keep
track of donated goods on paper or in their heads. It shows what you have, what
you are running out of, and gives you a ready-to-share **"What we need"** list
for donors. Everything stays on your own computer.

**[Try it in your browser](https://felipevicente0227-hash.github.io/shelter-inventory/)** - no download, nothing to install.
Works on Windows, Mac, Chromebooks, tablets and phones.

Or **[download the app for Windows or Mac](https://github.com/felipevicente0227-hash/shelter-inventory/releases/latest)** - free, no account, no internet.

![dashboard](docs/screenshot-main.png)

Import the list you already keep:

![import](docs/screenshot-import.png)

Print a count sheet for stock-taking:

![count sheet](docs/screenshot-count-sheet.png)

---

## Browser or download?

| | Browser version | Downloaded app |
|---|---|---|
| Getting started | Open [the link](https://felipevicente0227-hash.github.io/shelter-inventory/) - nothing to install | Download, then click past the "unknown program" warning once |
| Works on | Any up-to-date browser: Windows, Mac, Chromebook, tablet, phone | Windows and Mac |
| Where your list is kept | In that browser, on that device only | In a normal folder on the computer (`Documents/ShelterInventory`) |
| Internet | Needed for the first visit only | Never |
| Keep a backup? | **Yes** - clearing your browsing data deletes the list. Use **Settings → Download a backup** now and then (the app reminds you) | Copy the folder now and then |

Both are the same program and do the same things. Either way nothing is
uploaded anywhere: there is no server, no account and no tracking. A backup
from one can be restored in the other (**Settings → Restore from a backup**),
so you can move your list between them - the browser version also accepts the
desktop app's `inventory_data.json` directly.

## For charities: get it running in 2 minutes

**In the browser (any device)**

Open **https://felipevicente0227-hash.github.io/shelter-inventory/**, type your charity's name, and start. Bookmark the page (or
"Add to Home Screen" on a phone or tablet). Remember to download a backup now
and then.

**Windows**

1. Go to the [Releases page](https://github.com/felipevicente0227-hash/shelter-inventory/releases/latest)
   and download `ShelterInventory.exe`.
2. Double-click it. The first time, Windows may show a blue box saying
   *"Windows protected your PC"*. Click **More info**, then **Run anyway**.
   (That warning appears for any small free program that has not paid for a
   code-signing certificate. The program is open source - anyone can read
   exactly what it does in this repository.)
3. Type your charity's name when asked. Then either start with a few example
   items, start empty, or **Import my existing list** if you already keep one
   in Excel or a CSV. That is it.

**Mac**

1. Download `ShelterInventory-mac.zip` from the same page and unzip it.
2. Right-click `ShelterInventory` → **Open** → **Open** (only needed the first time).

**No download at all (any computer with Python)**

Download this repository, then double-click `RUN APP (double-click me).cmd`
on Windows, or run `python3 shelter_inventory.py` on Mac/Linux.

### Using it

![inventory](docs/screenshot-inventory.png)

- **Dashboard**: how stocked you are overall, what needs attention, and each
  category at a glance.
- **Import your existing list**: **Import spreadsheet** (dashboard, or under
  Settings) opens your Excel (.xlsx) or CSV file. The app works out which
  column is the item name, which is what you have, which is the target and
  which is the use-by date, shows you what it understood, and only then
  imports. Items already in your inventory are left alone unless you choose
  **Add & update existing**. Undo brings back the state before the import.
- **Add an item**: **+ New item** — name, category, what you *have* and what
  you *need* (the target), and an optional **use-by** date.
- **Use-by dates**: items that are expired, or expire within the next 30 days
  (change the number under Settings), get a purple **Use-by** count on the
  dashboard, appear at the top of *Needs attention*, and show a badge in the
  Inventory table. Sort by *Use-by date* or filter *Use-by soon or expired*
  to see them together.
- **Update stock**: on the Inventory page, type the new count in the row and
  press Enter or **Save**.
- **Edit / rename / delete**: **Edit** on the row. Delete asks first, and
  **Undo** (Ctrl+Z) brings back anything you change by mistake.
- **Find things**: the search box filters as you type; the category, show and
  sort boxes narrow the list.
- **Colours**: red is **Urgent** (below 50% of target), amber is **Low**
  (below 80%), green is **Fine**. Change the two numbers under Settings.
- **What we need**: a plain-text list of everything urgent or low, most-needed
  first. Copy it into an email, a Facebook post, or print it for a donation drive.
- **Count sheet**: a printable list of every item with a blank box next to
  it. Print it, walk the shelves with a clipboard, then type the counts in.
  **Save as text file** if you have no printer handy.
- **Help**: a one-page reminder of how everything works, where your data is,
  and an **Email about a problem** button that opens a message to the author
  with the version number already filled in.
- **Settings**: charity name, your own categories (one per line), the two
  thresholds, how many days ahead to warn about use-by dates, and buttons to
  import a spreadsheet or load the example items. **Data folder** opens the
  folder where everything is saved (desktop app).
- **Backups**: **Download a backup** (Settings) saves one file,
  `shelter-inventory-backup-YYYY-MM-DD.json`, with your whole list and
  settings. **Restore from a backup** shows what it will replace and asks
  first; your current list is kept as an automatic backup before anything is
  replaced, and **Undo** brings your items back.

The app draws its screen with the web engine already on your computer (Edge
on Windows, Safari on a Mac) — it still needs no internet. On a very old
Windows machine without that engine, the same app opens in a plainer window
instead, with every feature.

### Where your data lives (please read this once)

Your inventory is saved automatically after every change, to a normal folder
you can see and back up:

| Computer | Folder |
|---|---|
| Windows | `C:\Users\<you>\Documents\ShelterInventory\` |
| Mac | `/Users/<you>/Documents/ShelterInventory/` |
| Linux | `~/Documents/ShelterInventory/` |

The **Open data folder** button in the app takes you straight there. Inside:

| File | What it is |
|---|---|
| `inventory_data.json` | your items - plain text, readable by any program |
| `inventory_data.bak` | the version before your last change |
| `backups/inventory_data-YYYY-MM-DD.json` | one copy per day, the last 30 days |
| `settings.json` | your charity name, categories and thresholds |
| `log.txt` | anything that went wrong, for troubleshooting |

**Your data is yours.** It is never uploaded anywhere, there is no account,
and the program does not use the internet. If this project disappeared
tomorrow, your `inventory_data.json` would still open in Notepad.

**To back up**: copy the `ShelterInventory` folder to a USB stick or cloud
drive. To move to a new computer, copy it into the new computer's Documents.

**Portable mode**: create a folder called `data` next to `ShelterInventory.exe`
(for example on a USB stick) and the app will keep everything in there instead.

### If something goes wrong

- **"Windows protected your PC"** - click *More info* → *Run anyway*. See above.
- **"YOUR LAST CHANGE WAS NOT SAVED"** - the program could not write to the
  data folder (usually a permissions problem, a full disk, or a cloud-drive
  folder that is locked). Your change is still on screen; use *Export CSV* to
  keep a copy, then check the folder shown in the message.
- **"Recovered from backup"** - the data file was damaged (power cut mid-save,
  disk error) and the previous good copy was loaded. The damaged file is kept
  in the data folder with `corrupt` in its name, in case anything is missing.
- **Items from an older version are missing** - the very first version saved
  its file wherever it was started from. On first run the new version looks
  for that file and offers to import it. If it did not find it, search your
  computer for `inventory_data.json`, copy that file into the data folder
  (replacing the one there), and restart the app.

Questions or ideas: open an issue on this repository, or use the
**Email about a problem** button on the app's **Help** page.

---

## For developers

Python 3 plus one package, `pywebview` (the window). The data layer is standard library only.

```
pip install pywebview
python tests.py            # 78 tests, no window, nothing outside a temp folder
python shelter_inventory.py
```

Open `webui/index.html` in any browser to work on the design with sample data
(no Python needed — it runs in demo mode; on a web address add `?demo`).

The browser version is the same page. Served over http(s) it loads a pinned
[Pyodide](https://pyodide.org) from cdn.jsdelivr.net, copies `inventory_core.py`
and `webui/browser_api.py` into it, and keeps `/data` in the browser's
IndexedDB. `py dev/smoke_browser.py` checks it end to end in headless
Chromium (needs Playwright).

| File | What it does |
|---|---|
| `inventory_core.py` | Data folder, safe saving, backups, undo, the urgent/low/ok logic, use-by dates, CSV/Excel import (standard library only), CSV and needs-list exports. No GUI code. |
| `shelter_inventory.py` | The window: opens `webui/index.html` with pywebview and exposes `Api` to it. |
| `webui/index.html` | The whole interface — styles, scripts, icons — in one file. Used by the desktop app (no internet) and by the browser version. |
| `webui/browser_api.py` | The browser version's bridge: same methods as `Api`, built on `inventory_core.StoreApi`; files are downloads instead of save dialogs. |
| `webui/sw.js` | Service worker: caches the page, the two Python files and the pinned Pyodide so the browser version opens offline. Bump `CACHE` each release. |
| `shelter_inventory_classic.py` | The plain tkinter window, used automatically when no web engine is available. |
| `tests.py` | Tests for the core (including import and use-by dates) and the `Api` bridge. |
| `dev/smoke_gui.py` | Drives the real window under `xvfb` for a screenshot and a crash check. |
| `dev/smoke_browser.py` | Builds `_site/` and checks the browser version in headless Chromium: real backend, reload, import, backup and restore. |
| `docs/examples/` | Sample spreadsheets for trying Import. |
| `CHANGELOG.md` | What changed in each version, in plain English. It becomes the release notes. |
| `BUILD EXE (double-click me).cmd` | Runs the tests, then builds `dist\ShelterInventory.exe` with PyInstaller. |
| `.github/workflows/build.yml` | Builds Windows and Mac downloads on GitHub and attaches them to a Release when you push a tag like `v0.2.1`. |
| `.github/workflows/pages.yml` | On every push to main: runs the tests and publishes the browser version to GitHub Pages. |

### How saving works (the bug v0.1 had)

v0.1 used `DATA_FILE = "inventory_data.json"` - a bare file name, which means
*"the folder the program was started from"*. Start it from PowerShell, from
VS Code, or by double-clicking and you get three different folders, so edits
seemed to vanish. Errors inside button handlers were printed to a console
nobody could see.

v0.2:

1. `inventory_core.data_folder()` picks one fixed folder per computer
   (Documents/ShelterInventory, found via the Windows shell so OneDrive
   redirection is respected).
2. `Store.save()` writes to a `.tmp` file, copies the current file to `.bak`,
   takes a dated backup once a day, then swaps the `.tmp` into place with
   `os.replace()` - one atomic step, so a crash leaves a complete file either way.
3. A failed save raises `StoreError`; the window shows it in the status bar
   **and** a message box, and writes the traceback to `log.txt`.
4. A corrupt file falls back to `.bak`; if both are unreadable the app refuses
   to start rather than overwrite anything.

See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

### Releasing a new version

1. Bump `APP_VERSION` in `inventory_core.py` and `CACHE` in `webui/sw.js`
   (a test checks they match).
2. Add a section to `CHANGELOG.md` first - it becomes the release notes.
3. `git tag v0.6.2 && git push --tags`
4. GitHub builds the `.exe` and the Mac zip and attaches them to the Release.

### Design rules

- One charity, one computer, one folder (or one browser). No server, no accounts, no tracking.
- Never lose data silently. Every failure is visible; every change is undoable.
- Plain text formats only (JSON, CSV, TXT) so the data outlives the program.

License: MIT - free for anyone, forever.
