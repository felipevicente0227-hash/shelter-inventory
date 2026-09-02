"""
shelter_inventory.py - the window (v0.4: a web page inside a desktop window).

Run it:            python shelter_inventory.py
Run the tests:     python tests.py

How it works, in one paragraph: the whole interface is webui/index.html - one
file with its styles and scripts inside it, no internet needed. pywebview
opens it in a window using the web engine already on the computer (Edge's
WebView2 on Windows, Safari's WebKit on a Mac). The page calls the small
`Api` class below for every change; `Api` calls inventory_core, which does
the saving. Nothing in this file decides what "urgent" means or where data
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


class Api:
    """What the page is allowed to ask Python to do. One method per action.

    Every mutating method returns the full state (or {"ok": False, "error"})
    so the page never has to guess what changed. Errors from the store are
    turned into plain sentences; nothing raises across the bridge.
    """

    def __init__(self, store: Store, window=None):
        self.store = store
        self.window = window

    # ---- state ------------------------------------------------------------
    def get_state(self):
        s = self.store
        return {
            "ok": True,
            "items": s.items,
            "settings": s.settings,
            "next_id": s.next_id,
            "undo_label": s.undo_label,
            "last_saved": s.last_saved.strftime("%H:%M:%S") if s.last_saved else None,
            "last_error": s.last_error,
            "data_file": str(s.data_file),
            "folder": str(s.folder),
            "recovered": s.recovered_from_backup,
            "version": core.APP_VERSION,
        }

    def _do(self, action, *args):
        try:
            action(*args)
        except ValueError as err:
            return {"ok": False, "error": str(err)}
        except StoreError as err:
            return {"ok": False, "error": str(err)}
        return self.get_state()

    # ---- changes ----------------------------------------------------------
    def add_item(self, name, category, current_qty, target_qty):
        return self._do(self.store.add_item, name, category, current_qty, target_qty)

    def set_quantity(self, item_id, qty):
        return self._do(self.store.set_quantity, int(item_id), qty)

    def update_item(self, item_id, name, category, current_qty, target_qty):
        return self._do(self.store.update_item, int(item_id), name, category, current_qty, target_qty)

    def delete_item(self, item_id):
        return self._do(self.store.delete_item, int(item_id))

    def undo(self):
        return self._do(self.store.undo)

    def load_samples(self):
        return self._do(self.store.load_sample_items)

    def save_settings(self, changes):
        s = self.store.settings
        if "charity_name" in changes:
            s["charity_name"] = str(changes["charity_name"] or "").strip()[:80]
        if "categories" in changes:
            cats = [str(c).strip()[:40] for c in changes["categories"] if str(c).strip()]
            if not cats:
                return {"ok": False, "error": "Keep at least one category."}
            s["categories"] = list(dict.fromkeys(cats))
        try:
            urgent = int(changes.get("urgent_below_percent", s["urgent_below_percent"]))
            low = int(changes.get("low_below_percent", s["low_below_percent"]))
        except (TypeError, ValueError):
            return {"ok": False, "error": "The two percentages must be whole numbers."}
        if not (1 <= urgent < low <= 100):
            return {"ok": False, "error": "Urgent must be below Low, both between 1 and 100."}
        s["urgent_below_percent"], s["low_below_percent"] = urgent, low
        if "setup_done" in changes:
            s["setup_done"] = bool(changes["setup_done"])
        return self._do(self.store.save_settings)

    # ---- exports ----------------------------------------------------------
    def needs_list(self):
        return core.needs_list_text(self.store)

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
