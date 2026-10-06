"""
browser_api.py - the browser version's stand-in for shelter_inventory.Api.

The browser version is the same webui/index.html, served from GitHub Pages.
Instead of pywebview it loads Pyodide (Python compiled for the browser), puts
inventory_core.py and this file into Pyodide's file system, and calls
BrowserApi by the same method names the desktop window uses.

Everything shared lives in inventory_core.StoreApi. The only differences:

  * The data folder is /data, which the page mounts on the browser's own
    storage (IndexedDB) and syncs after every change. It never leaves the
    device: there is no server.
  * Where the desktop opens a save dialog, these methods return the file's
    content and the page hands it to the person as a download.
  * Where the desktop opens an open dialog, the page reads the chosen file and
    passes its bytes to stage_file(); the usual preview -> confirm steps
    then run on that copy.

It has no Pyodide-only code, so tests.py runs it on a normal computer.
"""

import datetime as _dt
import re
import tempfile
from pathlib import Path

import inventory_core as core
from inventory_core import Store, StoreError

WHERE = "this browser, on this device only"


class BrowserApi(core.StoreApi):
    def __init__(self, folder, staging=None):
        store = Store(Path(folder))
        try:
            store.load()
        except StoreError as err:
            # Keep going with an empty list rather than a blank page; nothing
            # on disk is touched, and the message shows in the sidebar.
            store.last_error = str(err)
        super().__init__(store)
        self.staging = Path(staging) if staging else Path(tempfile.gettempdir()) / "shelter-inventory-files"

    # ---- state ------------------------------------------------------------
    def get_state(self):
        state = super().get_state()
        state.update(browser=True, folder=WHERE, data_file=f"In {WHERE}.")
        return state

    def help_info(self):
        info = super().help_info()
        info.update(browser=True, folder=WHERE, browser_url=core.BROWSER_URL)
        return info

    # ---- files coming in (import, restore) ----------------------------------
    def stage_file(self, name, data):
        """Keep a copy of a file the person picked, so preview_import /
        import_file / preview_restore / restore_file can read it by path."""
        if hasattr(data, "to_bytes"):          # a JavaScript Uint8Array, from Pyodide
            data = data.to_bytes()
        safe = re.sub(r"[^\w.() -]", "_", Path(str(name)).name).strip() or "file"
        try:
            self.staging.mkdir(parents=True, exist_ok=True)
            for old in self.staging.iterdir():
                old.unlink()
            path = self.staging / safe
            path.write_bytes(bytes(data))
        except OSError as err:
            return {"ok": False, "error": f"Could not read that file: {err}"}
        return {"ok": True, "path": str(path)}

    def pick_import_file(self):
        return {"ok": False}                   # the page uses <input type="file">

    def pick_restore_file(self):
        return {"ok": False}

    # ---- files going out (the page turns these into downloads) -------------
    @staticmethod
    def _file(filename, content, mime):
        return {"ok": True, "filename": filename, "content": content, "mime": mime}

    def export_csv(self):
        return self._file(f"inventory-{_dt.date.today():%Y-%m-%d}.csv",
                          core.inventory_csv(self.store), "text/csv")

    def save_needs(self):
        return self._file(f"what-we-need-{_dt.date.today():%Y-%m-%d}.txt",
                          core.needs_list_text(self.store), "text/plain")

    def save_count_sheet(self):
        return self._file(f"stock-count-{_dt.date.today():%Y-%m-%d}.txt",
                          core.count_sheet_text(self.store), "text/plain")

    def save_backup(self):
        return self._file(core.backup_filename(), core.backup_text(self.store), "application/json")

    # ---- things only the desktop can do --------------------------------------
    def open_link(self, kind):
        """The page opens the link itself (a new tab, or the mail program)."""
        if kind == "site":
            return {"ok": True, "url": core.APP_URL}
        if kind == "report":
            return {"ok": True, "url": core.support_mail_link(
                detail="(browser version)\n" + (self.store.last_error or ""))}
        return {"ok": False, "error": "Unknown link."}

    def copied(self, text):
        return {"ok": False, "error": "Could not copy - select the text and copy it instead."}

    def open_folder(self):
        return {"ok": False, "error": "The browser version has no data folder - use Download a backup."}
