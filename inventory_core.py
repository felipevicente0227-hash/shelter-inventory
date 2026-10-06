"""
inventory_core.py - everything in Shelter Inventory Manager that is NOT the window.

If you are reading the code for the first time, start here. This file holds:

  1. WHERE DATA LIVES   - one fixed, visible folder per computer (see data_folder)
  2. THE STORE          - loading, saving, backups, undo, and every change to an item
  3. THE ALGORITHMS     - status (urgent / low / ok), percent, sorting, filtering
  4. EXPORTS            - a CSV of everything, and the "What we need" list for donors
  5. IMPORTS            - reading a charity's existing spreadsheet (CSV or Excel)
  6. USE-BY DATES       - which items are expired or expiring soon
  7. BACKUPS            - one file with everything, and restoring it (also moves a
                          list between the desktop app and the browser version)
  8. THE BRIDGE         - StoreApi: what the window (desktop or browser) may ask for

Nothing in here opens a window, so all of it can be tested without a screen
(see tests.py). The window lives in shelter_inventory.py and only calls
functions from this file.

--------------------------------------------------------------------------
WHY THIS FILE EXISTS (the bug it fixes)
--------------------------------------------------------------------------
Version 0.1 saved to the file name "inventory_data.json" with no folder in
front of it. That means "save into whatever folder the app happened to be
started from". Start it from PowerShell, from VS Code, or by double-clicking,
and it looks in three different folders - so your changes seemed to vanish.
They were never deleted; they were just in a folder you were not looking in.

Now every copy of the app on a given computer uses ONE folder:

    Windows   C:\\Users\\<you>\\Documents\\ShelterInventory\\
    Mac       /Users/<you>/Documents/ShelterInventory/
    Linux     /home/<you>/Documents/ShelterInventory/

It is a normal, visible folder, so a charity can find it, copy it, and back it
up like any other document. Everything inside it is plain text (JSON / CSV).
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import re
import shutil
import sys
import traceback
from pathlib import Path

APP_NAME = "Shelter Inventory Manager"
APP_VERSION = "0.7.0"
APP_FOLDER_NAME = "ShelterInventory"

# Where people can download the app. Shown at the bottom of the
# "What we need" list so that one charity can pass the tool to another.
APP_URL = "https://github.com/felipevicente0227-hash/shelter-inventory"
# The browser version: the same page and this same file, run by Pyodide.
BROWSER_URL = "https://felipevicente0227-hash.github.io/shelter-inventory/"
# Where a charity can report a problem. Shown in Help; opens their own mail program.
SUPPORT_EMAIL = "felipe.vicente0227@gmail.com"

DATA_FILENAME = "inventory_data.json"
SETTINGS_FILENAME = "settings.json"
LOG_FILENAME = "log.txt"
BACKUP_FOLDER_NAME = "backups"
BACKUPS_TO_KEEP = 30           # one per day; older ones are deleted
UNDO_DEPTH = 50                # how many changes "Undo" can step back through

DEFAULT_CATEGORIES = ["Food", "Clothing", "Bedding", "Hygiene", "Cleaning", "Other"]

DEFAULT_SETTINGS = {
    "charity_name": "",
    "categories": list(DEFAULT_CATEGORIES),
    # An item is URGENT below this percent of its target, LOW below the
    # second number, and OK from there up.
    "urgent_below_percent": 50,
    "low_below_percent": 80,
    # Set to True the first time the window has finished its welcome step.
    "setup_done": False,
    # Which skin the window uses: native, paper, clinic, bigprint or slate.
    "theme": "native",
    # An item with a use-by date this many days away (or closer) is "expiring soon".
    "expiry_warn_days": 30,
}

SAMPLE_ITEMS = [
    {"name": "Tinned soup",     "category": "Food",     "current_qty": 12, "target_qty": 50, "expires": ""},
    {"name": "Rice (1kg bags)", "category": "Food",     "current_qty": 5,  "target_qty": 40, "expires": ""},
    {"name": "UHT milk",        "category": "Food",     "current_qty": 18, "target_qty": 30, "expires": "SOON"},
    {"name": "Blankets",        "category": "Bedding",  "current_qty": 30, "target_qty": 35},
    {"name": "Toothbrushes",    "category": "Hygiene",  "current_qty": 8,  "target_qty": 60},
    {"name": "Winter coats",    "category": "Clothing", "current_qty": 3,  "target_qty": 20},
    {"name": "Shampoo",         "category": "Hygiene",  "current_qty": 40, "target_qty": 50},
    {"name": "Washing powder",  "category": "Cleaning", "current_qty": 2,  "target_qty": 15},
    {"name": "Socks",           "category": "Clothing", "current_qty": 25, "target_qty": 80},
]


class StoreError(Exception):
    """Raised when data could not be read or written. The window shows the
    message in a red box; it is never swallowed silently."""


# ==========================================================================
# 1. WHERE DATA LIVES
# ==========================================================================

def app_folder() -> Path:
    """The folder the program itself is running from.

    When packaged with PyInstaller the .exe unpacks itself into a temporary
    folder, so __file__ would point somewhere that disappears on exit. The
    real location of the .exe is sys.executable in that case.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def documents_folder() -> Path:
    """The user's Documents folder, found the way the operating system does.

    On Windows we ask the shell rather than guessing "~/Documents", because
    OneDrive often moves Documents to C:\\Users\\<you>\\OneDrive\\Documents and
    a guessed path would silently create a second, un-synced folder.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            import ctypes.wintypes

            CSIDL_PERSONAL = 5          # "My Documents"
            SHGFP_TYPE_CURRENT = 0
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
            )
            if buf.value:
                return Path(buf.value)
        except Exception:                        # pragma: no cover - Windows only
            pass
    home = Path.home()
    docs = home / "Documents"
    return docs if docs.is_dir() else home


def data_folder() -> Path:
    """The one folder this computer's inventory lives in.

    Three ways to choose it, checked in this order:
      1. SHELTER_INVENTORY_DATA environment variable  (for tests and experts)
      2. a folder called "data" sitting next to the program
         (portable mode - keep app + data together on a USB stick)
      3. Documents/ShelterInventory                    (the normal case)
    """
    override = os.environ.get("SHELTER_INVENTORY_DATA")
    if override:
        return Path(override)
    portable = app_folder() / "data"
    if portable.is_dir():
        return portable
    return documents_folder() / APP_FOLDER_NAME


def find_legacy_files() -> list[Path]:
    """Old version-0.1 save files that may be sitting in the wrong place.

    Version 0.1 wrote inventory_data.json into the folder it was started from.
    We look in the likely spots so the window can offer to import them.
    """
    candidates = []
    for folder in (Path.cwd(), app_folder(), Path.home(), Path.home() / "Desktop"):
        try:
            candidate = (folder / DATA_FILENAME).resolve()
        except OSError:
            continue
        if candidate.is_file() and candidate not in candidates:
            candidates.append(candidate)
    # Never offer our own live file as a "legacy" file.
    own = (data_folder() / DATA_FILENAME)
    try:
        own = own.resolve()
    except OSError:
        pass
    return [c for c in candidates if c != own]


# ==========================================================================
# 3. THE ALGORITHMS  (pure functions - no files, no windows)
# ==========================================================================

def get_status(curr: int, tgt: int, urgent_below: int = 50, low_below: int = 80) -> str:
    """Compare current stock to the target and return 'urgent', 'low' or 'ok'."""
    if tgt <= 0:
        return "ok"
    pct = (curr / tgt) * 100
    if pct < urgent_below:
        return "urgent"
    if pct < low_below:
        return "low"
    return "ok"


def get_pct(curr: int, tgt: int) -> int:
    """Percent of target in stock, as a whole number, capped at 100."""
    if tgt <= 0:
        return 100
    return min(100, round((curr / tgt) * 100))


STATUS_ORDER = {"urgent": 0, "low": 1, "ok": 2}


def sort_items(item_list, mode, urgent_below=50, low_below=80):
    """
    'urgent' = most-needed first (worst status tier, then lowest percent)
    'qty'    = lowest current quantity first
    'name'   = alphabetical A-Z (the default)
    """
    if mode == "urgent":
        return sorted(
            item_list,
            key=lambda i: (
                STATUS_ORDER[get_status(i["current_qty"], i["target_qty"], urgent_below, low_below)],
                get_pct(i["current_qty"], i["target_qty"]),
                i["name"].lower(),
            ),
        )
    if mode == "qty":
        return sorted(item_list, key=lambda i: (i["current_qty"], i["name"].lower()))
    return sorted(item_list, key=lambda i: i["name"].lower())


def filter_items(item_list, mode, urgent_below=50, low_below=80):
    """
    'all'         = everything
    'urgent-only' = only items whose status is urgent
    'needs'       = urgent + low (everything that belongs on a needs list)
    anything else = treated as a category name
    """
    if mode == "all":
        return list(item_list)
    if mode == "urgent-only":
        return [i for i in item_list
                if get_status(i["current_qty"], i["target_qty"], urgent_below, low_below) == "urgent"]
    if mode == "needs":
        return [i for i in item_list
                if get_status(i["current_qty"], i["target_qty"], urgent_below, low_below) != "ok"]
    return [i for i in item_list if i["category"] == mode]


# --- validation: each returns (True, "") or (False, "message for the person") ---

def validate_name(name: str):
    if not name or not name.strip():
        return False, "Please enter an item name."
    if len(name.strip()) > 80:
        return False, "Item name is too long (80 characters max)."
    return True, ""


def validate_quantity(qty_str):
    try:
        val = int(str(qty_str).strip())
    except (ValueError, TypeError):
        return False, "Quantity must be a whole number."
    if val < 0:
        return False, "Quantity must be 0 or more."
    return True, ""


def validate_target(tgt_str):
    try:
        val = int(str(tgt_str).strip())
    except (ValueError, TypeError):
        return False, "Target must be a whole number."
    if val < 1:
        return False, "Target quantity must be at least 1."
    return True, ""


# --- use-by dates -----------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
                 "%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y", "%m/%Y", "%Y-%m")


def parse_date(text) -> _dt.date | None:
    """Turn what a person typed into a date, or None if it is not one.

    Accepts the formats people actually write on tins and spreadsheets:
    2026-03-31, 31/03/2026, 31.3.2026, 31 Mar 2026, Mar 2026 (= last day of
    that month), and an Excel serial number such as 46112.
    """
    if text is None:
        return None
    if isinstance(text, _dt.datetime):
        return text.date()
    if isinstance(text, _dt.date):
        return text
    raw = str(text).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{4,6}(\.0+)?", raw):           # Excel serial date
        try:
            return _dt.date(1899, 12, 30) + _dt.timedelta(days=int(float(raw)))
        except (ValueError, OverflowError):
            return None
    for fmt in _DATE_FORMATS:
        try:
            parsed = _dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
        if "%d" not in fmt:                             # month only -> end of month
            nxt = (parsed.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
            parsed = nxt - _dt.timedelta(days=1)
        return parsed
    return None


def validate_expiry(text):
    """Empty is fine (most items have no use-by date). Otherwise it must be a date."""
    if text is None or not str(text).strip():
        return True, ""
    if parse_date(text) is None:
        return False, "Use-by date not understood. Try 2026-03-31 or 31/03/2026, or leave it blank."
    return True, ""


def normalize_expiry(text) -> str:
    """The stored form is always YYYY-MM-DD or ''."""
    d = parse_date(text)
    return d.isoformat() if d else ""


def expiry_status(expires: str, today: _dt.date | None = None, warn_days: int = 30) -> str:
    """'expired', 'soon' or '' (no date, or comfortably in the future)."""
    d = parse_date(expires)
    if d is None:
        return ""
    today = today or _dt.date.today()
    if d < today:
        return "expired"
    if (d - today).days <= warn_days:
        return "soon"
    return ""


# ==========================================================================
# 2. THE STORE
# ==========================================================================

def _now():
    return _dt.datetime.now()


class Store:
    """Owns the items, the settings, the files, and the undo history.

    Every method that changes data ends by calling save(). If the save fails
    the change is kept in memory and a StoreError is raised so the window can
    tell the person - the one thing version 0.1 never did.
    """

    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder else data_folder()
        self.data_file = self.folder / DATA_FILENAME
        self.settings_file = self.folder / SETTINGS_FILENAME
        self.log_file = self.folder / LOG_FILENAME
        self.backup_folder = self.folder / BACKUP_FOLDER_NAME

        self.items: list[dict] = []
        self.next_id = 1
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))   # deep copy

        self.last_saved: _dt.datetime | None = None
        self.last_error: str | None = None
        self.recovered_from_backup = False
        self._undo: list[tuple[str, list[dict], int]] = []

    # ---------------------------------------------------------------- logging

    def log(self, message: str) -> None:
        """Append one line to log.txt. Never raises - logging must not be
        another way to lose a save."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{_now():%Y-%m-%d %H:%M:%S}  {message}\n")
        except OSError:
            pass

    def log_exception(self, context: str) -> None:
        self.log(f"{context}\n{traceback.format_exc()}")

    # ---------------------------------------------------------------- loading

    def load(self) -> None:
        """Read settings and items from disk. A corrupt data file falls back to
        the .bak copy; if that is also unreadable, a StoreError is raised and
        NOTHING is overwritten - the person decides what to do."""
        self._load_settings()

        if not self.data_file.exists():
            self.items, self.next_id = [], 1
            return

        try:
            payload = self._read_json(self.data_file)
        except (json.JSONDecodeError, OSError, ValueError) as err:
            self.log(f"data file unreadable ({err}); trying backup")
            bak = self.data_file.with_suffix(".bak")
            try:
                payload = self._read_json(bak)
            except (json.JSONDecodeError, OSError, ValueError) as err2:
                raise StoreError(
                    f"The inventory file could not be read:\n{self.data_file}\n\n"
                    f"({err})\n\nThe backup copy could not be read either ({err2}).\n"
                    f"Nothing has been changed. Dated copies are in:\n{self.backup_folder}"
                ) from err2
            # Keep the broken file for inspection instead of destroying it.
            broken = self.data_file.with_name(
                f"inventory_data.corrupt-{_now():%Y%m%d-%H%M%S}.json")
            try:
                self.data_file.replace(broken)
            except OSError:
                pass
            self.recovered_from_backup = True
            self.log(f"recovered from backup; broken file kept as {broken.name}")

        self.items = self._clean_items(payload.get("items", []))
        highest = max((i["id"] for i in self.items), default=0)
        self.next_id = max(int(payload.get("next_id", 1) or 1), highest + 1)

    def _load_settings(self) -> None:
        saved = {}
        if self.settings_file.exists():
            try:
                saved = self._read_json(self.settings_file)
            except (json.JSONDecodeError, OSError, ValueError) as err:
                self.log(f"settings unreadable ({err}); using defaults")
        self.settings = self.clean_settings(saved)

    @classmethod
    def clean_settings(cls, saved: dict) -> dict:
        """Defaults, overlaid with whatever known keys `saved` has, within limits."""
        base = json.loads(json.dumps(DEFAULT_SETTINGS))
        for key in base:
            if key in saved:
                base[key] = saved[key]
        _clamp = cls._clamp
        # Sanity limits so a hand-edited file cannot break the colour logic.
        base["categories"] = cls._clean_categories(base.get("categories"))
        base["urgent_below_percent"] = _clamp(base.get("urgent_below_percent"), 1, 99, 50)
        base["low_below_percent"] = _clamp(base.get("low_below_percent"), 1, 100, 80)
        if base["low_below_percent"] <= base["urgent_below_percent"]:
            base["low_below_percent"] = min(100, base["urgent_below_percent"] + 1)
        base["charity_name"] = str(base.get("charity_name") or "").strip()[:80]
        base["setup_done"] = bool(base.get("setup_done"))
        base["theme"] = str(base.get("theme") or "native").strip()[:20]
        base["expiry_warn_days"] = _clamp(base.get("expiry_warn_days"), 0, 365, 30)
        return base

    @staticmethod
    def _read_json(path: Path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        return data

    @staticmethod
    def _clamp(value, low, high, default):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    @staticmethod
    def _clean_categories(cats) -> list[str]:
        out = []
        for c in (cats or []):
            c = str(c).strip()[:40]
            if c and c not in out:
                out.append(c)
        return out or list(DEFAULT_CATEGORIES)

    @staticmethod
    def _clean_items(raw) -> list[dict]:
        """Accept only well-formed items; skip anything else rather than crash."""
        items, seen_ids = [], set()
        for entry in raw or []:
            try:
                item = {
                    "id": int(entry["id"]),
                    "name": str(entry["name"]).strip()[:80],
                    "category": str(entry.get("category") or "Other").strip()[:40] or "Other",
                    "current_qty": max(0, int(entry["current_qty"])),
                    "target_qty": max(1, int(entry["target_qty"])),
                    "expires": normalize_expiry(entry.get("expires", "")),
                }
            except (KeyError, TypeError, ValueError):
                continue
            if not item["name"] or item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            items.append(item)
        return items

    # ----------------------------------------------------------------- saving

    def save(self) -> None:
        """Write items to disk safely.

        The recipe, in order:
          1. write everything to inventory_data.json.tmp
          2. copy the current inventory_data.json to inventory_data.bak
          3. once a day, also copy it to backups/inventory_data-YYYY-MM-DD.json
          4. swap the .tmp into place in one step (os.replace)

        Step 4 is atomic on every OS we support, so a crash or power cut at any
        moment leaves either the old complete file or the new complete file -
        never half of one.
        """
        payload = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "saved_at": _now().isoformat(timespec="seconds"),
            "items": self.items,
            "next_id": self.next_id,
        }
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._daily_backup()
            self._atomic_write_json(self.data_file, payload, keep_bak=True)
        except OSError as err:
            self.last_error = f"Could not save to {self.data_file}: {err}"
            self.log_exception("save failed")
            raise StoreError(
                "YOUR LAST CHANGE WAS NOT SAVED.\n\n"
                f"Could not write to:\n{self.data_file}\n\n"
                f"Reason: {err}\n\n"
                "Check that the folder exists and you are allowed to write to it, "
                "then try again. Use Export CSV to keep a copy in the meantime."
            ) from err
        self.last_saved = _now()
        self.last_error = None

    def save_settings(self) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._atomic_write_json(self.settings_file, self.settings, keep_bak=False)
        except OSError as err:
            self.log_exception("settings save failed")
            raise StoreError(f"Could not save settings to {self.settings_file}: {err}") from err

    @staticmethod
    def _atomic_write_json(path: Path, payload, keep_bak: bool) -> None:
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        if keep_bak and path.exists():
            shutil.copy2(path, path.with_suffix(".bak"))
        os.replace(tmp, path)

    def _daily_backup(self) -> None:
        """First save of each day copies yesterday's file into backups/."""
        if not self.data_file.exists():
            return
        self.backup_folder.mkdir(parents=True, exist_ok=True)
        today = self.backup_folder / f"inventory_data-{_now():%Y-%m-%d}.json"
        if today.exists():
            return
        shutil.copy2(self.data_file, today)
        backups = sorted(self.backup_folder.glob("inventory_data-*.json"))
        for old in backups[:-BACKUPS_TO_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------- undo

    def _snapshot(self, label: str) -> None:
        self._undo.append((label, json.loads(json.dumps(self.items)), self.next_id))
        del self._undo[:-UNDO_DEPTH]

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1][0] if self._undo else None

    def undo(self) -> str | None:
        """Step back one change. Returns what was undone, or None."""
        if not self._undo:
            return None
        label, items, next_id = self._undo.pop()
        self.items, self.next_id = items, next_id
        self.save()
        return label

    # ------------------------------------------------------------ item changes

    def find(self, item_id: int) -> dict | None:
        for item in self.items:
            if item["id"] == item_id:
                return item
        return None

    def name_taken(self, name: str, except_id: int | None = None) -> bool:
        lowered = name.strip().lower()
        return any(i["name"].lower() == lowered and i["id"] != except_id for i in self.items)

    def add_item(self, name: str, category: str, current_qty, target_qty, expires="") -> dict:
        for ok, msg in (validate_name(name), validate_quantity(current_qty),
                        validate_target(target_qty), validate_expiry(expires)):
            if not ok:
                raise ValueError(msg)
        if self.name_taken(name):
            raise ValueError("An item with that name already exists.")
        category = (category or "Other").strip() or "Other"
        self._snapshot(f"add '{name.strip()}'")
        item = {
            "id": self.next_id,
            "name": name.strip(),
            "category": category,
            "current_qty": int(current_qty),
            "target_qty": int(target_qty),
            "expires": normalize_expiry(expires),
        }
        self.items.append(item)
        self.next_id += 1
        self.save()
        return item

    def set_quantity(self, item_id: int, qty) -> dict:
        ok, msg = validate_quantity(qty)
        if not ok:
            raise ValueError(msg)
        item = self.find(item_id)
        if item is None:
            raise ValueError("That item no longer exists.")
        if item["current_qty"] == int(qty):
            return item
        self._snapshot(f"change '{item['name']}' quantity {item['current_qty']} -> {int(qty)}")
        item["current_qty"] = int(qty)
        self.save()
        return item

    def update_item(self, item_id: int, name: str, category: str, current_qty, target_qty, expires=None) -> dict:
        """expires=None means "leave the use-by date as it is" (the classic window
        does not know about dates); '' clears it; a date string sets it."""
        for ok, msg in (validate_name(name), validate_quantity(current_qty), validate_target(target_qty)):
            if not ok:
                raise ValueError(msg)
        if expires is not None:
            ok, msg = validate_expiry(expires)
            if not ok:
                raise ValueError(msg)
        item = self.find(item_id)
        if item is None:
            raise ValueError("That item no longer exists.")
        if self.name_taken(name, except_id=item_id):
            raise ValueError("Another item already has that name.")
        self._snapshot(f"edit '{item['name']}'")
        item["name"] = name.strip()
        item["category"] = (category or "Other").strip() or "Other"
        item["current_qty"] = int(current_qty)
        item["target_qty"] = int(target_qty)
        if expires is not None:
            item["expires"] = normalize_expiry(expires)
        self.save()
        return item

    def delete_item(self, item_id: int) -> dict:
        item = self.find(item_id)
        if item is None:
            raise ValueError("That item no longer exists.")
        self._snapshot(f"delete '{item['name']}'")
        self.items = [i for i in self.items if i["id"] != item_id]
        self.save()
        return item

    def load_sample_items(self) -> int:
        """Add the example items (skipping names already present)."""
        self._snapshot("add example items")
        added = 0
        for sample in SAMPLE_ITEMS:
            if self.name_taken(sample["name"]):
                continue
            item = {"id": self.next_id, "expires": "", **sample}
            if item.get("expires") == "SOON":       # a live example of a use-by warning
                item["expires"] = (_dt.date.today() + _dt.timedelta(days=10)).isoformat()
            self.items.append(item)
            self.next_id += 1
            added += 1
        self.save()
        return added

    def import_legacy_file(self, path: Path) -> int:
        """Bring items in from a version-0.1 save file. Existing names win."""
        payload = self._read_json(Path(path))
        incoming = self._clean_items(payload.get("items", []))
        self._snapshot(f"import from {Path(path).name}")
        added = 0
        for item in incoming:
            if self.name_taken(item["name"]):
                continue
            self.items.append({**item, "id": self.next_id})
            self.next_id += 1
            added += 1
        self.save()
        return added

    def restore_backup(self, backup: dict) -> Path | None:
        """Replace everything with a backup read by read_backup().

        What is here now is first written to backups/before-restore-<time>.json
        (and Undo can bring the items back), so a restore never loses a list.
        Returns that file, or None if there was nothing to keep.
        """
        kept = None
        if self.items:
            self.backup_folder.mkdir(parents=True, exist_ok=True)
            kept = self.backup_folder / f"before-restore-{_now():%Y%m%d-%H%M%S}.json"
            try:
                write_text_file(kept, backup_text(self))
            except OSError as err:
                raise StoreError(f"Nothing was restored: could not keep a copy of the "
                                 f"current list first ({err}).") from err
        self._snapshot("restore from backup")
        self.items = json.loads(json.dumps(backup["items"]))
        self.next_id = max(int(backup["next_id"]), max((i["id"] for i in self.items), default=0) + 1)
        if backup.get("settings"):
            self.settings = self.clean_settings(backup["settings"])
        self.settings["setup_done"] = True
        self.save()
        self.save_settings()
        self.log(f"restored {len(self.items)} items from a {backup['kind']} file"
                 + (f"; previous list kept as {kept.name}" if kept else ""))
        return kept

    # ------------------------------------------------------------- read-only

    @property
    def thresholds(self) -> tuple[int, int]:
        return self.settings["urgent_below_percent"], self.settings["low_below_percent"]

    def status_of(self, item: dict) -> str:
        u, l = self.thresholds
        return get_status(item["current_qty"], item["target_qty"], u, l)

    def counts(self) -> dict:
        out = {"total": len(self.items), "urgent": 0, "low": 0, "ok": 0, "expired": 0, "soon": 0}
        for item in self.items:
            out[self.status_of(item)] += 1
            ex = self.expiry_of(item)
            if ex:
                out[ex] += 1
        return out

    def expiry_of(self, item: dict, today: _dt.date | None = None) -> str:
        return expiry_status(item.get("expires", ""), today, self.settings.get("expiry_warn_days", 30))

    # ------------------------------------------------------------------ import

    def import_rows(self, rows: list[dict], on_duplicate: str = "skip") -> dict:
        """Add items read from a spreadsheet (see parse_import_table).

        on_duplicate: 'skip'   - an item whose name already exists is left alone
                      'update' - its quantities (and use-by date, if given) are
                                 replaced by the spreadsheet's numbers
        Returns {"added": n, "updated": n, "skipped": n}. One undo step.
        """
        if on_duplicate not in ("skip", "update"):
            raise ValueError("on_duplicate must be 'skip' or 'update'")
        self._snapshot("import from spreadsheet")
        result = {"added": 0, "updated": 0, "skipped": 0}
        for row in rows:
            name = row["name"]
            existing = next((i for i in self.items if i["name"].lower() == name.lower()), None)
            if existing is not None:
                if on_duplicate == "skip":
                    result["skipped"] += 1
                    continue
                existing["current_qty"] = row["current_qty"]
                existing["target_qty"] = row["target_qty"]
                if row.get("category"):
                    existing["category"] = row["category"]
                if row.get("expires"):
                    existing["expires"] = row["expires"]
                result["updated"] += 1
                continue
            self.items.append({
                "id": self.next_id,
                "name": name,
                "category": row.get("category") or "Other",
                "current_qty": row["current_qty"],
                "target_qty": row["target_qty"],
                "expires": row.get("expires", ""),
            })
            self.next_id += 1
            result["added"] += 1
        self.save()
        return result

    def categories_in_use(self) -> list[str]:
        """Settings categories first, then any category an item still uses."""
        cats = list(self.settings["categories"])
        for item in self.items:
            if item["category"] not in cats:
                cats.append(item["category"])
        return cats

    def visible(self, sort_mode: str, filter_mode: str) -> list[dict]:
        u, l = self.thresholds
        return sort_items(filter_items(self.items, filter_mode, u, l), sort_mode, u, l)


# ==========================================================================
# 4. EXPORTS
# ==========================================================================

CSV_COLUMNS = ["name", "category", "current_qty", "target_qty", "percent", "status", "need", "expires"]


def inventory_rows(store: Store) -> list[dict]:
    rows = []
    for item in sort_items(store.items, "urgent", *store.thresholds):
        rows.append({
            "name": item["name"],
            "category": item["category"],
            "current_qty": item["current_qty"],
            "target_qty": item["target_qty"],
            "percent": get_pct(item["current_qty"], item["target_qty"]),
            "status": store.status_of(item),
            "need": max(0, item["target_qty"] - item["current_qty"]),
            "expires": item.get("expires", ""),
        })
    return rows


def inventory_csv(store: Store) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in inventory_rows(store):
        writer.writerow(row)
    return buf.getvalue()


def needs_list_text(store: Store, today: _dt.date | None = None) -> str:
    """The one-page 'What we need' list a charity can print, post, or email.

    Only urgent and low items appear, most-needed first. Plain text on purpose:
    it pastes cleanly into an email, a Facebook post, or a printed sheet.
    """
    today = today or _dt.date.today()
    name = store.settings.get("charity_name") or "Our shelter"
    lines = [f"{name} - What we need - {today:%d %B %Y}", ""]

    needs = [r for r in inventory_rows(store) if r["status"] != "ok"]
    if not needs:
        lines.append("We are well stocked on everything right now - thank you!")
    else:
        urgent = [r for r in needs if r["status"] == "urgent"]
        low = [r for r in needs if r["status"] == "low"]
        if urgent:
            lines.append("MOST URGENT")
            for r in urgent:
                lines.append(f"  - {r['name']}: need {r['need']} more "
                             f"(we have {r['current_qty']} of {r['target_qty']})")
            lines.append("")
        if low:
            lines.append("RUNNING LOW")
            for r in low:
                lines.append(f"  - {r['name']}: need {r['need']} more "
                             f"(we have {r['current_qty']} of {r['target_qty']})")
            lines.append("")
        lines.append("Thank you for helping us keep the shelves full.")

    lines += ["", f"Made with {APP_NAME}, a free tool for shelters: {APP_URL}"]
    return "\n".join(lines) + "\n"


# ==========================================================================
# 5. IMPORTS - a charity's existing spreadsheet
# ==========================================================================
#
# Most charities already have SOME list - an Excel sheet, a Google Sheet
# exported as CSV, a table typed up by a volunteer. Retyping 80 items is the
# moment people give up on a new tool, so we read theirs instead.
#
# We do not insist on our column names. We look at the header row and guess:
#   name      <- item, name, product, description, goods
#   category  <- category, type, group, section
#   have      <- have, current, qty, quantity, stock, in stock, count
#   need      <- need, target, want, required, par, min
#   expires   <- expires, expiry, use by, best before, bbe, date
# The guess is shown to the person before anything is imported.

IMPORT_FIELDS = ["name", "category", "current_qty", "target_qty", "expires"]

_HEADER_HINTS = {
    "name": ["item name", "item", "name", "product", "description", "goods", "article", "articulo", "artículo", "nombre", "produit", "nom"],
    "category": ["category", "type", "group", "section", "categoria", "categoría", "catégorie", "tipo"],
    "current_qty": ["have now", "have", "current", "in stock", "stock", "on hand", "qty", "quantity", "count", "amount", "cantidad", "quantité", "existencias"],
    "target_qty": ["need (target)", "target", "need", "needed", "want", "required", "par", "par level", "minimum", "min", "goal", "objetivo", "meta", "cible", "besoin"],
    "expires": ["expires", "expiry", "expiry date", "use by", "use-by", "best before", "bbe", "bb date", "exp", "date", "caducidad", "caduca", "péremption", "dlc"],
}


def guess_columns(headers: list[str]) -> dict:
    """Map our field names to header positions. Missing fields are absent."""
    cleaned = [str(h or "").strip().lower() for h in headers]
    mapping = {}
    taken = set()
    for field in IMPORT_FIELDS:                       # exact matches first
        for hint in _HEADER_HINTS[field]:
            if hint in cleaned and cleaned.index(hint) not in taken:
                mapping[field] = cleaned.index(hint)
                taken.add(mapping[field])
                break
    for field in IMPORT_FIELDS:                       # then "contains"
        if field in mapping:
            continue
        for idx, head in enumerate(cleaned):
            if idx in taken or not head:
                continue
            if any(hint in head for hint in _HEADER_HINTS[field]):
                mapping[field] = idx
                taken.add(idx)
                break
    return mapping


def _looks_like_header(row: list) -> bool:
    """A header row has words in it and no bare numbers."""
    cells = [str(c or "").strip() for c in row]
    if not any(cells):
        return False
    numeric = sum(1 for c in cells if re.fullmatch(r"-?\d+(\.\d+)?", c))
    return numeric == 0 and len(guess_columns(cells)) >= 1


def read_csv_table(text: str) -> list[list[str]]:
    """Rows of a CSV whatever the delimiter (comma, semicolon, tab)."""
    text = text.lstrip("\ufeff")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def read_xlsx_table(path: Path) -> list[list]:
    """First sheet of an .xlsx as rows of values - standard library only.

    An .xlsx is a zip of XML files. We read the shared-strings table and the
    first worksheet; that covers every spreadsheet a charity is likely to
    have. Formulas come back as their last calculated value.
    """
    import zipfile
    import xml.etree.ElementTree as ET

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        # which file is the first sheet?
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map = {r.get("Id"): r.get("Target") for r in rels}
        first = wb.find("m:sheets/m:sheet", ns)
        target = rel_map.get(first.get(f"{{{ns['r']}}}id"), "worksheets/sheet1.xml") if first is not None else "worksheets/sheet1.xml"
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        sheet = ET.fromstring(z.read(target))

    def col_index(ref: str) -> int:
        letters = "".join(ch for ch in ref if ch.isalpha())
        n = 0
        for ch in letters:
            n = n * 26 + (ord(ch.upper()) - 64)
        return n - 1

    rows = []
    for row in sheet.iter(f"{{{ns['m']}}}row"):
        values = {}
        for c in row.findall("m:c", ns):
            idx = col_index(c.get("r", "A"))
            kind = c.get("t")
            v = c.find("m:v", ns)
            if kind == "s" and v is not None:
                val = shared[int(v.text)] if v.text and v.text.isdigit() and int(v.text) < len(shared) else ""
            elif kind == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            elif v is not None:
                val = v.text or ""
                if re.fullmatch(r"-?\d+\.0+", val):
                    val = val.split(".")[0]
            else:
                val = ""
            values[idx] = val
        if values:
            width = max(values) + 1
            rows.append([values.get(i, "") for i in range(width)])
    return rows


def read_table_file(path: Path) -> list[list]:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return read_xlsx_table(path)
    if path.suffix.lower() == ".xls":
        raise ValueError("Old .xls files are not supported. In Excel choose File > Save As "
                         "and pick 'Excel Workbook (.xlsx)' or 'CSV', then try again.")
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return read_csv_table(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not read that file as text.")


def parse_import_table(table: list[list], mapping: dict | None = None) -> dict:
    """Turn raw rows into clean items plus a list of problems.

    Returns {"headers", "mapping", "rows", "problems", "total"} where rows are
    ready for Store.import_rows and problems are sentences like
    "Row 7: 'Beans' has no quantity - used 0". Nothing is guessed silently.
    """
    table = [list(r) for r in table if any(str(c or "").strip() for c in r)]
    if not table:
        return {"headers": [], "mapping": {}, "rows": [], "problems": ["The file is empty."], "total": 0}

    if _looks_like_header(table[0]):
        headers, body = [str(c or "").strip() for c in table[0]], table[1:]
    else:
        headers, body = [], table
    mapping = dict(mapping) if mapping else guess_columns(headers)
    if not headers and "name" not in mapping:
        # No header row: assume name, have, need (the way people jot a list) -
        # but only if the second column really does hold numbers.
        def is_num(v):
            return re.fullmatch(r"-?\d+(\.\d+)?", str(v or "").strip().replace(",", "")) is not None
        if any(len(r) > 1 and is_num(r[1]) for r in body):
            mapping = {"name": 0, "current_qty": 1, "target_qty": 2}
        elif any(len(r) > 2 and is_num(r[2]) for r in body):
            mapping = {"name": 0, "category": 1, "current_qty": 2, "target_qty": 3}

    problems = []
    if "name" not in mapping:
        problems.append("Could not find an item-name column. The first row should have a heading like 'Item' or 'Name'.")
        return {"headers": headers, "mapping": mapping, "rows": [], "problems": problems, "total": len(body)}

    def cell(row, field):
        idx = mapping.get(field)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx] if row[idx] is not None else "").strip()

    def to_int(text):
        text = text.replace(",", "").strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    rows, seen = [], set()
    for n, raw in enumerate(body, start=2 if headers else 1):
        name = cell(raw, "name")[:80]
        if not name:
            continue
        if name.lower() in seen:
            problems.append(f"Row {n}: '{name}' appears twice in the file - the first one was kept.")
            continue
        seen.add(name.lower())
        have = to_int(cell(raw, "current_qty"))
        need = to_int(cell(raw, "target_qty"))
        if have is None:
            if "current_qty" in mapping and cell(raw, "current_qty"):
                problems.append(f"Row {n}: '{name}' has a quantity that is not a number ('{cell(raw, 'current_qty')}') - used 0.")
            have = 0
        if have < 0:
            have = 0
        if need is None or need < 1:
            if "target_qty" in mapping and cell(raw, "target_qty"):
                problems.append(f"Row {n}: '{name}' has a target that is not a positive number - used what you have, or 1.")
            need = max(1, have)
        expires_raw = cell(raw, "expires")
        expires = normalize_expiry(expires_raw) if expires_raw else ""
        if expires_raw and not expires:
            problems.append(f"Row {n}: '{name}' has a use-by date I could not read ('{expires_raw}') - left blank.")
        rows.append({
            "name": name,
            "category": cell(raw, "category")[:40] or "Other",
            "current_qty": have,
            "target_qty": need,
            "expires": expires,
        })
    return {"headers": headers, "mapping": mapping, "rows": rows, "problems": problems, "total": len(rows)}


def count_sheet_rows(store: Store) -> list[dict]:
    """Every item, grouped by category then A-Z: the order a person walks the shelves."""
    rows = []
    for item in sorted(store.items, key=lambda i: (i["category"].lower(), i["name"].lower())):
        rows.append({
            "category": item["category"],
            "name": item["name"],
            "current_qty": item["current_qty"],
            "target_qty": item["target_qty"],
            "expires": item.get("expires", ""),
        })
    return rows


def count_sheet_text(store: Store, today: _dt.date | None = None) -> str:
    """A stock-count sheet for a clipboard: every item with a blank box to
    write today's count in. Plain text so it prints from anything."""
    today = today or _dt.date.today()
    name = store.settings.get("charity_name") or "Our shelter"
    lines = [f"{name} - Stock count - {today:%d %B %Y}",
             "Counted by: ______________________   Date: ____________", ""]
    current = None
    for r in count_sheet_rows(store):
        if r["category"] != current:
            current = r["category"]
            lines += ["", current.upper(), "-" * len(current)]
        note = f"  use by {r['expires']}" if r["expires"] else ""
        lines.append(f"  [______]  {r['name']}   (last count {r['current_qty']}, target {r['target_qty']}){note}")
    if not store.items:
        lines.append("No items yet.")
    lines += ["", "Type the new counts into the Inventory page when you are back at the computer.",
              f"Made with {APP_NAME}: {APP_URL}"]
    return "\n".join(lines) + "\n"


def support_mail_link(subject_prefix: str = "Problem with", detail: str = "") -> str:
    """A mailto: link with the version already filled in, so a bug report
    arrives with the one fact that is always needed."""
    from urllib.parse import quote
    subject = f"{subject_prefix} {APP_NAME} {APP_VERSION}"
    body = (f"Version: {APP_VERSION}\nComputer: {sys.platform}\n\n"
            f"What I was doing:\n\n\nWhat happened instead:\n\n{detail}")
    return f"mailto:{SUPPORT_EMAIL}?subject={quote(subject)}&body={quote(body)}"


def write_text_file(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


# ==========================================================================
# 7. BACKUPS - one file with everything
# ==========================================================================
#
# A backup is an inventory_data.json with the settings added to it, so:
#   * the desktop app and the browser version can both restore it, and
#   * restoring also accepts a plain inventory_data.json from the desktop
#     app's data folder - that is how a list moves into the browser.

BACKUP_FORMAT = "shelter-inventory-backup"
_NOT_A_BACKUP = ("That file is not a Shelter Inventory backup. Pick a file called "
                 "shelter-inventory-backup-....json, or inventory_data.json from the desktop app.")


def backup_filename(today: _dt.date | None = None) -> str:
    return f"shelter-inventory-backup-{(today or _dt.date.today()):%Y-%m-%d}.json"


def backup_text(store: Store) -> str:
    payload = {
        "format": BACKUP_FORMAT,
        "app": APP_NAME,
        "version": APP_VERSION,
        "saved_at": _now().isoformat(timespec="seconds"),
        "items": store.items,
        "next_id": store.next_id,
        "settings": store.settings,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def read_backup(raw) -> dict:
    """Understand a backup file, or the desktop app's inventory_data.json.

    Returns {"kind": "backup" | "desktop", "items", "next_id", "settings"
    (None for a desktop data file), "saved_at", "charity_name"}.
    Raises ValueError with a sentence for the person if it is neither.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError(_NOT_A_BACKUP) from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError(_NOT_A_BACKUP) from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(_NOT_A_BACKUP)
    items = Store._clean_items(data["items"])
    if data["items"] and not items:
        raise ValueError("None of the items in that file could be read, so nothing was changed.")
    try:
        next_id = int(data.get("next_id") or 1)
    except (TypeError, ValueError):
        next_id = 1
    next_id = max(next_id, max((i["id"] for i in items), default=0) + 1)
    settings = Store.clean_settings(data["settings"]) if isinstance(data.get("settings"), dict) else None
    return {
        "kind": "backup" if data.get("format") == BACKUP_FORMAT else "desktop",
        "items": items,
        "next_id": next_id,
        "settings": settings,
        "saved_at": str(data.get("saved_at") or "")[:19],
        "charity_name": settings["charity_name"] if settings else "",
    }


# ==========================================================================
# 8. THE BRIDGE - what the window may ask for
# ==========================================================================
#
# The page (webui/index.html) calls these methods by name. The desktop app
# (shelter_inventory.Api) and the browser version (webui/browser_api.py) both
# start from StoreApi, so they behave the same; they differ only where the
# desktop opens a file dialog and the browser hands a file to the person.

class StoreApi:
    """Every mutating method returns the full state (or {"ok": False, "error"})
    so the page never has to guess what changed. Errors from the store are
    turned into plain sentences; nothing raises across the bridge."""

    def __init__(self, store: Store):
        self.store = store

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
            "version": APP_VERSION,
            "today": _dt.date.today().isoformat(),
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
    def add_item(self, name, category, current_qty, target_qty, expires=""):
        return self._do(self.store.add_item, name, category, current_qty, target_qty, expires)

    def set_quantity(self, item_id, qty):
        return self._do(self.store.set_quantity, int(item_id), qty)

    def update_item(self, item_id, name, category, current_qty, target_qty, expires=""):
        return self._do(self.store.update_item, int(item_id), name, category, current_qty, target_qty, expires)

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
        if "expiry_warn_days" in changes:
            try:
                days = int(changes["expiry_warn_days"])
            except (TypeError, ValueError):
                return {"ok": False, "error": "Use-by warning must be a whole number of days."}
            if not (0 <= days <= 365):
                return {"ok": False, "error": "Use-by warning must be between 0 and 365 days."}
            s["expiry_warn_days"] = days
        if "setup_done" in changes:
            s["setup_done"] = bool(changes["setup_done"])
        return self._do(self.store.save_settings)

    # ---- import from a spreadsheet ----------------------------------------
    def preview_import(self, path):
        """Show what we understood BEFORE importing anything. Changes nothing."""
        try:
            table = read_table_file(Path(path))
            parsed = parse_import_table(table)
        except (OSError, ValueError) as err:
            return {"ok": False, "error": f"Could not read that file: {err}"}
        except Exception as err:                       # a broken zip, odd XML...
            return {"ok": False, "error": f"That file could not be understood ({type(err).__name__}: {err})."}
        existing = {i["name"].lower() for i in self.store.items}
        dupes = sum(1 for r in parsed["rows"] if r["name"].lower() in existing)
        return {
            "ok": True,
            "path": str(path),
            "filename": Path(path).name,
            "headers": parsed["headers"],
            "mapping": {k: (parsed["headers"][v] if v < len(parsed["headers"]) else f"column {v + 1}")
                        for k, v in parsed["mapping"].items()},
            "sample": parsed["rows"][:6],
            "total": parsed["total"],
            "duplicates": dupes,
            "problems": parsed["problems"][:12],
            "more_problems": max(0, len(parsed["problems"]) - 12),
        }

    def import_file(self, path, on_duplicate="skip"):
        try:
            table = read_table_file(Path(path))
            parsed = parse_import_table(table)
            if not parsed["rows"]:
                return {"ok": False, "error": parsed["problems"][0] if parsed["problems"] else "No items found in that file."}
            summary = self.store.import_rows(parsed["rows"], on_duplicate)
        except (OSError, ValueError) as err:
            return {"ok": False, "error": str(err)}
        except StoreError as err:
            return {"ok": False, "error": str(err)}
        state = self.get_state()
        state["import"] = summary
        return state

    # ---- backups ------------------------------------------------------------
    def preview_restore(self, path):
        """What a restore would replace, for the person to confirm. Changes nothing."""
        try:
            backup = read_backup(Path(path).read_bytes())
        except (OSError, ValueError) as err:
            return {"ok": False, "error": str(err)}
        return {
            "ok": True,
            "path": str(path),
            "filename": Path(path).name,
            "kind": backup["kind"],
            "items": len(backup["items"]),
            "charity_name": backup["charity_name"],
            "saved_at": backup["saved_at"],
            "current_items": len(self.store.items),
            "current_charity_name": self.store.settings.get("charity_name") or "",
        }

    def restore_file(self, path):
        try:
            backup = read_backup(Path(path).read_bytes())
            self.store.restore_backup(backup)
        except (OSError, ValueError) as err:
            return {"ok": False, "error": str(err)}
        except StoreError as err:
            return {"ok": False, "error": str(err)}
        return self.get_state()

    # ---- exports, count sheet, help ---------------------------------------
    def needs_list(self):
        return needs_list_text(self.store)

    def count_sheet(self):
        return {"ok": True, "rows": count_sheet_rows(self.store),
                "text": count_sheet_text(self.store),
                "charity_name": self.store.settings.get("charity_name") or "Our shelter",
                "date": _dt.date.today().strftime("%d %B %Y")}

    def help_info(self):
        return {"ok": True, "version": APP_VERSION, "app_url": APP_URL,
                "support_email": SUPPORT_EMAIL, "folder": str(self.store.folder),
                "last_error": self.store.last_error}
