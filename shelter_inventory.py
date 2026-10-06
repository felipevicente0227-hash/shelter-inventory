"""
shelter_inventory.py - the window (v0.4: a web page inside a desktop window).

Run it:            python shelter_inventory.py
Run the tests:     python tests.py

How it works, in one paragraph: the whole interface is webui/index.html - one
file with its styles and scripts inside it, no internet needed. pywebview
opens it in a window using the web engine already on the computer (Edge's
WebView2 on Windows, Safari's WebKit on a Mac). The page calls the small
`Api` class below for every change; `Api` calls inventory_core, which does
the saving. (The browser version uses the same page with webui/browser_api.py
in place of this file.) Nothing in this file decides what "urgent" means or where data
lives - inventory_core.py does, and tests.py checks it.

The previous, plainer window is kept as shelter_inventory_classic.py and
still works. If the web engine is missing on an old machine, this file
falls back to it automatically.
"""

import datetime as _dt
import sys
from pathlib import Path

import inventory_core as core
from inventory_core import Store, StoreError


def resource_path(name: str) -> Path:
    """Files bundled into the .exe are unpacked to sys._MEIPASS at run time."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


class Api(core.StoreApi):
    """What the page is allowed to ask Python to do. One method per action.

    Everything that does not need a window - state, changes, settings,
    import, restore, needs list, count sheet, help - is core.StoreApi, which
    the browser version (webui/browser_api.py) shares. This class adds the
    parts that open a file dialog or another program on this computer.
    """

    def __init__(self, store: Store, window=None):
        super().__init__(store)
        self.window = window

    # ---- import from a spreadsheet ----------------------------------------
    def _open_dialog(self, kinds):
        if self.window is None:
            return None
        import webview
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG, directory=str(Path.home()), allow_multiple=False, file_types=kinds)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def pick_import_file(self):
        """Let the person choose a CSV/Excel file and show what we understood
        BEFORE importing anything. Nothing is changed by this call."""
        path = self._open_dialog(("Spreadsheets (*.csv;*.xlsx;*.txt)", "All files (*.*)"))
        if not path:
            return {"ok": False}
        return self.preview_import(path)

    # ---- backups ------------------------------------------------------------
    def pick_restore_file(self):
        """Choose a backup (or an inventory_data.json) and show what it would
        replace. Nothing is changed until restore_file is called."""
        path = self._open_dialog(("Backups (*.json)", "All files (*.*)"))
        if not path:
            return {"ok": False}
        return self.preview_restore(path)

    def save_backup(self):
        path = self._save_dialog(core.backup_filename(), ("Backup (*.json)",))
        if not path:
            return {"ok": False}
        try:
            core.write_text_file(Path(path), core.backup_text(self.store))
        except OSError as err:
            return {"ok": False, "error": f"Save failed: {err}"}
        return {"ok": True, "path": str(path)}

    # ---- count sheet + help -----------------------------------------------
    def save_count_sheet(self):
        path = self._save_dialog(f"stock-count-{_dt.date.today():%Y-%m-%d}.txt", ("Text file (*.txt)",))
        if not path:
            return {"ok": False}
        try:
            core.write_text_file(Path(path), core.count_sheet_text(self.store))
        except OSError as err:
            return {"ok": False, "error": f"Save failed: {err}"}
        return {"ok": True, "path": str(path)}

    def open_link(self, kind):
        """Open the download page or a pre-filled bug-report email in the
        person's own browser / mail program. The app itself stays offline."""
        import webbrowser
        if kind == "site":
            target = core.APP_URL
        elif kind == "report":
            target = core.support_mail_link(detail=self.store.last_error or "")
        else:
            return {"ok": False, "error": "Unknown link."}
        try:
            webbrowser.open(target)
            return {"ok": True}
        except Exception as err:
            return {"ok": False, "error": f"Could not open it: {err}"}

    def _save_dialog(self, filename, kinds):
        if self.window is None:
            return None
        import webview
        result = self.window.create_file_dialog(
            webview.SAVE_DIALOG, directory=str(self.store.folder),
            save_filename=filename, file_types=kinds)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def export_csv(self):
        path = self._save_dialog(f"inventory-{_dt.date.today():%Y-%m-%d}.csv",
                                 ("CSV (opens in Excel) (*.csv)",))
        if not path:
            return {"ok": False}
        try:
            core.write_text_file(Path(path), core.inventory_csv(self.store))
        except OSError as err:
            return {"ok": False, "error": f"Export failed: {err}"}
        return {"ok": True, "path": str(path)}

    def save_needs(self):
        path = self._save_dialog(f"what-we-need-{_dt.date.today():%Y-%m-%d}.txt", ("Text file (*.txt)",))
        if not path:
            return {"ok": False}
        try:
            core.write_text_file(Path(path), core.needs_list_text(self.store))
        except OSError as err:
            return {"ok": False, "error": f"Save failed: {err}"}
        return {"ok": True, "path": str(path)}

    def copied(self, text):
        """Clipboard fallback for engines that refuse navigator.clipboard."""
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            r.clipboard_clear(); r.clipboard_append(text); r.update()
            r.destroy()
            return {"ok": True}
        except Exception as err:
            return {"ok": False, "error": str(err)}

    def open_folder(self):
        try:
            from shelter_inventory_classic import open_folder
            open_folder(self.store.folder)
            return {"ok": True}
        except Exception as err:
            return {"ok": False, "error": f"Could not open {self.store.folder}: {err}"}


def web_engine_available() -> bool:
    """Windows needs the WebView2 runtime (ships with Edge on Windows 10/11).
    Without it pywebview would fall back to the old Internet Explorer engine,
    which cannot draw this page - so use the classic window instead."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except ImportError:                              # pragma: no cover
        return True
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    ]
    for root, path in keys:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def main():
    store = Store()
    try:
        store.load()
    except StoreError as err:
        print(err)
        try:
            import tkinter.messagebox as mb
            mb.showerror("Could not read your inventory", str(err))
        except Exception:
            pass
        return

    try:
        import webview
    except ImportError:
        webview = None

    if webview is None or not web_engine_available():
        # No web engine: the classic window still does everything.
        import shelter_inventory_classic
        shelter_inventory_classic.main()
        return

    api = Api(store)
    html = resource_path("webui/index.html").read_text(encoding="utf-8")
    # Tell the page it is inside the desktop app: it then waits for
    # pywebview and never starts the browser version (webui/browser_api.py).
    html = html.replace('<html lang="en">', '<html lang="en" data-app="desktop">', 1)
    window = webview.create_window(
        f"{store.settings.get('charity_name') or 'Shelter Inventory'} - {core.APP_NAME}",
        html=html, js_api=api, width=1240, height=800, min_size=(960, 620))
    api.window = window
    icon = resource_path("icon.ico")
    gui = "edgechromium" if sys.platform == "win32" else None
    try:
        webview.start(gui=gui, icon=str(icon) if icon.exists() else None)
    except TypeError:                              # older pywebview without icon=
        webview.start(gui=gui)


if __name__ == "__main__":
    main()
