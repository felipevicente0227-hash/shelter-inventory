"""
tests.py - proves the data layer does what README.md promises.

Run with:   python tests.py

No window is opened and nothing outside a temporary folder is touched.
Every test gets its own empty folder, so they cannot see each other's files.
"""

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import inventory_core as core
from inventory_core import Store, StoreError


class TempFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shelter-test-"))
        self.folder = self.tmp / "ShelterInventory"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def store(self):
        s = Store(self.folder)
        s.load()
        return s


def tiny_xlsx(path, rows):
    """Write a minimal .xlsx by hand (inline strings + numbers) - no library.
    This is what a charity's Excel file looks like inside the zip."""
    import zipfile
    def col(n):
        out = ""
        while n >= 0:
            out = chr(65 + n % 26) + out
            n = n // 26 - 1
        return out
    cells = []
    for r, row in enumerate(rows, start=1):
        parts = []
        for c, val in enumerate(row):
            ref = f"{col(c)}{r}"
            if isinstance(val, (int, float)):
                parts.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif val is None or val == "":
                continue
            else:
                parts.append(f'<c r="{ref}" t="inlineStr"><is><t>{val}</t></is></c>')
        cells.append(f'<row r="{r}">{"".join(parts)}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(cells)}</sheetData></worksheet>')
    wb = ('<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Stock" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)


# ---------------------------------------------------------------- algorithms

class AlgorithmTests(unittest.TestCase):
    def test_status_tiers(self):
        self.assertEqual(core.get_status(0, 10), "urgent")
        self.assertEqual(core.get_status(4, 10), "urgent")     # 40%
        self.assertEqual(core.get_status(5, 10), "low")        # 50% is not below 50
        self.assertEqual(core.get_status(7, 10), "low")        # 70%
        self.assertEqual(core.get_status(8, 10), "ok")         # 80% is not below 80
        self.assertEqual(core.get_status(50, 10), "ok")

    def test_status_custom_thresholds(self):
        self.assertEqual(core.get_status(3, 10, urgent_below=25, low_below=60), "low")
        self.assertEqual(core.get_status(2, 10, urgent_below=25, low_below=60), "urgent")
        self.assertEqual(core.get_status(6, 10, urgent_below=25, low_below=60), "ok")

    def test_status_zero_target_is_ok_not_crash(self):
        self.assertEqual(core.get_status(0, 0), "ok")
        self.assertEqual(core.get_pct(0, 0), 100)

    def test_pct_rounds_and_caps(self):
        self.assertEqual(core.get_pct(1, 3), 33)
        self.assertEqual(core.get_pct(2, 3), 67)
        self.assertEqual(core.get_pct(99, 10), 100)

    def _items(self):
        return [
            {"id": 1, "name": "Zed",   "category": "Food",     "current_qty": 9, "target_qty": 10},   # ok
            {"id": 2, "name": "alpha", "category": "Hygiene",  "current_qty": 1, "target_qty": 10},   # urgent 10%
            {"id": 3, "name": "Mid",   "category": "Food",     "current_qty": 6, "target_qty": 10},   # low
            {"id": 4, "name": "Beta",  "category": "Clothing", "current_qty": 3, "target_qty": 10},   # urgent 30%
        ]

    def test_sort_by_need_puts_worst_first(self):
        names = [i["name"] for i in core.sort_items(self._items(), "urgent")]
        self.assertEqual(names, ["alpha", "Beta", "Mid", "Zed"])

    def test_sort_by_name_ignores_case(self):
        names = [i["name"] for i in core.sort_items(self._items(), "name")]
        self.assertEqual(names, ["alpha", "Beta", "Mid", "Zed"])

    def test_sort_by_qty(self):
        names = [i["name"] for i in core.sort_items(self._items(), "qty")]
        self.assertEqual(names, ["alpha", "Beta", "Mid", "Zed"])

    def test_filters(self):
        items = self._items()
        self.assertEqual(len(core.filter_items(items, "all")), 4)
        self.assertEqual({i["name"] for i in core.filter_items(items, "urgent-only")}, {"alpha", "Beta"})
        self.assertEqual({i["name"] for i in core.filter_items(items, "needs")}, {"alpha", "Beta", "Mid"})
        self.assertEqual({i["name"] for i in core.filter_items(items, "Food")}, {"Zed", "Mid"})
        self.assertEqual(core.filter_items(items, "Nonexistent"), [])

    def test_validation_messages(self):
        self.assertFalse(core.validate_name("   ")[0])
        self.assertFalse(core.validate_quantity("abc")[0])
        self.assertFalse(core.validate_quantity("-1")[0])
        self.assertTrue(core.validate_quantity(" 0 ")[0])
        self.assertFalse(core.validate_target("0")[0])
        self.assertTrue(core.validate_target("1")[0])


# ------------------------------------------------------------- persistence

class ExpiryTests(TempFolderTest):
    def test_parse_date_accepts_what_people_write(self):
        d = dt.date(2026, 3, 31)
        for text in ("2026-03-31", "31/03/2026", "31-03-2026", "31.3.2026", "31 Mar 2026", "31 March 2026", " 2026/03/31 "):
            self.assertEqual(core.parse_date(text), d, text)
        self.assertEqual(core.parse_date("Mar 2026"), d)             # month only -> last day
        self.assertEqual(core.parse_date("46112"), d)                # Excel serial number
        self.assertEqual(core.parse_date(d), d)
        for bad in ("", None, "soon", "31/13/2026", "12"):
            self.assertIsNone(core.parse_date(bad), bad)

    def test_validate_expiry_blank_is_fine_nonsense_is_not(self):
        self.assertEqual(core.validate_expiry(""), (True, ""))
        self.assertEqual(core.validate_expiry(None), (True, ""))
        self.assertTrue(core.validate_expiry("2027-01-01")[0])
        ok, msg = core.validate_expiry("next week")
        self.assertFalse(ok)
        self.assertIn("2026-03-31", msg)

    def test_expiry_status_tiers(self):
        today = dt.date(2026, 6, 1)
        self.assertEqual(core.expiry_status("", today), "")
        self.assertEqual(core.expiry_status("2026-05-31", today), "expired")
        self.assertEqual(core.expiry_status("2026-06-01", today), "soon")       # today counts as soon
        self.assertEqual(core.expiry_status("2026-07-01", today, 30), "soon")
        self.assertEqual(core.expiry_status("2026-07-02", today, 30), "")
        self.assertEqual(core.expiry_status("2026-07-02", today, 60), "soon")

    def test_expiry_is_saved_normalised_and_survives_reopen(self):
        s = self.store()
        s.add_item("UHT milk", "Food", 5, 10, "31/12/2027")
        s.add_item("Socks", "Clothing", 5, 10)
        again = self.store()
        milk = next(i for i in again.items if i["name"] == "UHT milk")
        socks = next(i for i in again.items if i["name"] == "Socks")
        self.assertEqual(milk["expires"], "2027-12-31")
        self.assertEqual(socks["expires"], "")

    def test_add_with_bad_date_is_refused(self):
        s = self.store()
        with self.assertRaises(ValueError):
            s.add_item("Milk", "Food", 1, 2, "someday")
        self.assertEqual(s.items, [])

    def test_update_none_keeps_date_and_blank_clears_it(self):
        s = self.store()
        item = s.add_item("Milk", "Food", 1, 2, "2027-01-01")
        s.update_item(item["id"], "Milk", "Food", 3, 4)                # classic window: no date arg
        self.assertEqual(s.find(item["id"])["expires"], "2027-01-01")
        s.update_item(item["id"], "Milk", "Food", 3, 4, "")
        self.assertEqual(s.find(item["id"])["expires"], "")
        s.update_item(item["id"], "Milk", "Food", 3, 4, "1 Jan 2028")
        self.assertEqual(s.find(item["id"])["expires"], "2028-01-01")

    def test_counts_include_expiry_and_settings_control_the_window(self):
        s = self.store()
        soon = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        far = (dt.date.today() + dt.timedelta(days=100)).isoformat()
        s.add_item("A", "Food", 1, 1, "2000-01-01")
        s.add_item("B", "Food", 1, 1, soon)
        s.add_item("C", "Food", 1, 1, far)
        s.add_item("D", "Food", 1, 1)
        c = s.counts()
        self.assertEqual((c["expired"], c["soon"]), (1, 1))
        s.settings["expiry_warn_days"] = 120
        self.assertEqual(s.counts()["soon"], 2)

    def test_old_files_without_expires_still_load(self):
        s = self.store()
        s.add_item("Socks", "Clothing", 1, 2)
        payload = json.loads(s.data_file.read_text(encoding="utf-8"))
        for item in payload["items"]:
            del item["expires"]
        s.data_file.write_text(json.dumps(payload), encoding="utf-8")
        again = self.store()
        self.assertEqual(again.items[0]["expires"], "")

    def test_sample_items_include_one_live_use_by_example(self):
        s = self.store()
        s.load_sample_items()
        dated = [i for i in s.items if i["expires"]]
        self.assertEqual(len(dated), 1)
        self.assertEqual(s.expiry_of(dated[0]), "soon")

    def test_csv_export_has_expires_column(self):
        s = self.store()
        s.add_item("Milk", "Food", 1, 2, "2027-01-01")
        text = core.inventory_csv(s)
        self.assertIn("expires", text.splitlines()[0])
        self.assertIn("2027-01-01", text)


class CountSheetAndHelpTests(TempFolderTest):
    def test_count_sheet_groups_by_category_then_name_with_a_box_per_item(self):
        s = self.store()
        s.settings["charity_name"] = "Hope House"
        s.add_item("Tinned soup", "Food", 12, 50)
        s.add_item("Blankets", "Bedding", 30, 35, "2027-01-01")
        s.add_item("Rice", "Food", 5, 40)
        rows = core.count_sheet_rows(s)
        self.assertEqual([r["name"] for r in rows], ["Blankets", "Rice", "Tinned soup"])
        text = core.count_sheet_text(s, dt.date(2026, 10, 1))
        self.assertIn("Hope House - Stock count - 01 October 2026", text)
        self.assertIn("Counted by:", text)
        self.assertLess(text.index("BEDDING"), text.index("FOOD"))
        self.assertEqual(text.count("[______]"), 3)
        self.assertIn("use by 2027-01-01", text)
        self.assertIn(core.APP_URL, text)

    def test_count_sheet_when_empty(self):
        self.assertIn("No items yet", core.count_sheet_text(self.store()))

    def test_support_mail_link_carries_the_version(self):
        link = core.support_mail_link(detail="it broke")
        self.assertTrue(link.startswith("mailto:" + core.SUPPORT_EMAIL + "?"))
        self.assertIn(core.APP_VERSION.replace(".", "."), link)
        self.assertIn("it%20broke", link)
        self.assertNotIn(" ", link)


class ImportTests(TempFolderTest):
    def test_guess_columns_from_friendly_headers(self):
        m = core.guess_columns(["Item", "Type", "Qty", "Target", "Best before"])
        self.assertEqual(m, {"name": 0, "category": 1, "current_qty": 2, "target_qty": 3, "expires": 4})
        m = core.guess_columns(["Description", "In stock", "Par level"])
        self.assertEqual(m, {"name": 0, "current_qty": 1, "target_qty": 2})
        self.assertEqual(core.guess_columns(["Foo", "Bar"]), {})

    def test_parse_table_with_headers_and_problems(self):
        table = [["Item", "Category", "Have", "Need", "Use by"],
                 ["Beans", "Food", "12", "40", "31/03/2027"],
                 ["Soap", "Hygiene", "x", "", ""],
                 ["Beans", "Food", "1", "1", ""],
                 ["", "", "", "", ""],
                 ["Tea", "Food", "1,200", "2000", "when?"]]
        r = core.parse_import_table(table)
        names = [x["name"] for x in r["rows"]]
        self.assertEqual(names, ["Beans", "Soap", "Tea"])
        self.assertEqual(r["rows"][0]["expires"], "2027-03-31")
        self.assertEqual((r["rows"][1]["current_qty"], r["rows"][1]["target_qty"]), (0, 1))
        self.assertEqual(r["rows"][2]["current_qty"], 1200)
        self.assertEqual(r["rows"][2]["expires"], "")
        self.assertEqual(len(r["problems"]), 3)
        self.assertTrue(any("appears twice" in p for p in r["problems"]))
        self.assertTrue(any("use-by date" in p for p in r["problems"]))

    def test_parse_table_without_headers_assumes_name_have_need(self):
        r = core.parse_import_table([["Beans", "12", "40"], ["Rice", "3", "20"]])
        self.assertEqual(r["rows"][1], {"name": "Rice", "category": "Other", "current_qty": 3, "target_qty": 20, "expires": ""})
        r = core.parse_import_table([["Beans", "Food", "12", "40"]])
        self.assertEqual(r["rows"][0]["category"], "Food")

    def test_parse_table_refuses_when_no_name_column(self):
        r = core.parse_import_table([["Colour", "Size"], ["red", "L"]])
        self.assertEqual(r["rows"], [])
        self.assertIn("item-name column", r["problems"][0])
        self.assertEqual(core.parse_import_table([])["problems"], ["The file is empty."])

    def test_csv_semicolons_tabs_and_bom(self):
        self.assertEqual(core.read_csv_table("\ufeffname;qty;target\nBeans;1;2\n"), [["name", "qty", "target"], ["Beans", "1", "2"]])
        self.assertEqual(core.read_csv_table("name\tqty\nBeans\t1\n"), [["name", "qty"], ["Beans", "1"]])
        self.assertEqual(core.read_csv_table('name,qty\n"Beans, baked",1\n'), [["name", "qty"], ["Beans, baked", "1"]])

    def test_read_table_file_handles_windows_encoding_and_xlsx(self):
        csv_path = self.tmp / "list.csv"
        csv_path.write_bytes("Item,Have,Need\nCaf\xe9 pods,2,10\n".encode("cp1252"))
        self.assertEqual(core.read_table_file(csv_path)[1][0], "Café pods")
        xlsx = self.tmp / "stock.xlsx"
        tiny_xlsx(xlsx, [["Item", "Type", "Quantity", "Target", "Best before"],
                         ["Tinned beans", "Food", 12, 40, 46357],
                         ["Soap", "Hygiene", 3, 20, None]])
        table = core.read_table_file(xlsx)
        r = core.parse_import_table(table)
        self.assertEqual(r["rows"][0]["expires"], "2026-12-01")
        self.assertEqual(r["rows"][1], {"name": "Soap", "category": "Hygiene", "current_qty": 3, "target_qty": 20, "expires": ""})
        with self.assertRaises(ValueError):
            core.read_table_file(self.tmp / "old.xls")

    def test_import_rows_skip_update_and_undo(self):
        s = self.store()
        s.add_item("Beans", "Food", 1, 5)
        rows = core.parse_import_table([["Item", "Have", "Need"], ["Beans", "9", "50"], ["Rice", "2", "20"]])["rows"]
        summary = s.import_rows(rows, "skip")
        self.assertEqual(summary, {"added": 1, "updated": 0, "skipped": 1})
        self.assertEqual(s.find(1)["current_qty"], 1)
        summary = s.import_rows(rows, "update")          # Rice is there now too
        self.assertEqual(summary, {"added": 0, "updated": 2, "skipped": 0})
        self.assertEqual((s.find(1)["current_qty"], s.find(1)["target_qty"]), (9, 50))
        self.assertEqual(s.undo(), "import from spreadsheet")
        self.assertEqual(s.find(1)["current_qty"], 1)
        self.assertTrue(s.name_taken("Rice"))
        with self.assertRaises(ValueError):
            s.import_rows(rows, "merge")
        again = self.store()
        self.assertEqual(len(again.items), 2)


class PersistenceTests(TempFolderTest):
    def test_fresh_folder_starts_empty_and_creates_file_on_first_save(self):
        s = self.store()
        self.assertEqual(s.items, [])
        self.assertFalse(s.data_file.exists())
        s.add_item("Soup", "Food", 5, 10)
        self.assertTrue(s.data_file.exists())
        self.assertIsNotNone(s.last_saved)

    def test_changes_survive_close_and_reopen(self):
        """The bug in v0.1, stated as a test: add, 'close', reopen, still there."""
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        s.add_item("Socks", "Clothing", 2, 20)
        s.set_quantity(1, 7)
        del s

        again = self.store()
        self.assertEqual([(i["name"], i["current_qty"]) for i in again.items],
                         [("Soup", 7), ("Socks", 2)])
        self.assertEqual(again.next_id, 3)

    def test_store_uses_the_same_folder_regardless_of_cwd(self):
        """Working directory must not matter - that is the whole fix."""
        old_cwd = os.getcwd()
        try:
            os.environ["SHELTER_INVENTORY_DATA"] = str(self.folder)
            os.chdir(self.tmp)
            a = Store(); a.load(); a.add_item("Soup", "Food", 1, 10)
            other = self.tmp / "elsewhere"; other.mkdir()
            os.chdir(other)
            b = Store(); b.load()
            self.assertEqual([i["name"] for i in b.items], ["Soup"])
            self.assertEqual(a.folder, b.folder)
        finally:
            os.chdir(old_cwd)
            os.environ.pop("SHELTER_INVENTORY_DATA", None)

    def test_save_is_atomic_no_tmp_left_behind(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        leftovers = [p.name for p in self.folder.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        payload = json.loads(s.data_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["items"][0]["name"], "Soup")
        self.assertIn("saved_at", payload)

    def test_bak_holds_previous_version(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        s.set_quantity(1, 9)
        bak = json.loads(s.data_file.with_suffix(".bak").read_text(encoding="utf-8"))
        live = json.loads(s.data_file.read_text(encoding="utf-8"))
        self.assertEqual(bak["items"][0]["current_qty"], 5)
        self.assertEqual(live["items"][0]["current_qty"], 9)

    def test_corrupt_file_recovers_from_bak_and_keeps_evidence(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        s.set_quantity(1, 9)
        s.data_file.write_text("{ this is not json", encoding="utf-8")
        again = self.store()
        self.assertTrue(again.recovered_from_backup)
        self.assertEqual(again.items[0]["current_qty"], 5)     # the .bak version
        corrupt = list(self.folder.glob("inventory_data.corrupt-*.json"))
        self.assertEqual(len(corrupt), 1)

    def test_corrupt_file_and_corrupt_bak_raise_instead_of_wiping(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        s.data_file.write_text("nope", encoding="utf-8")
        s.data_file.with_suffix(".bak").write_text("also nope", encoding="utf-8")
        with self.assertRaises(StoreError):
            self.store()
        # Nothing was overwritten.
        self.assertEqual(s.data_file.read_text(encoding="utf-8"), "nope")

    def test_daily_backup_written_once_per_day_and_pruned(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)          # creates the file; no backup yet
        s.set_quantity(1, 6)                       # first save with an existing file -> backup
        s.set_quantity(1, 7)                       # same day -> no second backup
        backups = list(s.backup_folder.glob("inventory_data-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].name, f"inventory_data-{dt.date.today():%Y-%m-%d}.json")

        # Pretend there are many old backups; only the newest BACKUPS_TO_KEEP survive.
        for n in range(core.BACKUPS_TO_KEEP + 5):
            (s.backup_folder / f"inventory_data-2000-01-{n + 1:02d}.json").write_text("{}")
        (s.backup_folder / backups[0].name).unlink()
        s.set_quantity(1, 8)
        remaining = sorted(s.backup_folder.glob("inventory_data-*.json"))
        self.assertEqual(len(remaining), core.BACKUPS_TO_KEEP)
        self.assertEqual(remaining[-1].name, f"inventory_data-{dt.date.today():%Y-%m-%d}.json")

    def test_save_failure_raises_and_keeps_change_in_memory(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        # Make the data file path unwritable by putting a directory in its place.
        s.data_file.unlink()
        s.data_file.mkdir()
        with self.assertRaises(StoreError) as ctx:
            s.set_quantity(1, 9)
        self.assertIn("NOT SAVED", str(ctx.exception))
        self.assertEqual(s.find(1)["current_qty"], 9)          # still in memory
        self.assertIsNotNone(s.last_error)
        self.assertTrue(s.log_file.exists())                    # and written to log.txt

    def test_garbage_items_are_skipped_not_fatal(self):
        self.folder.mkdir(parents=True)
        (self.folder / core.DATA_FILENAME).write_text(json.dumps({
            "items": [
                {"id": 1, "name": "Good", "category": "Food", "current_qty": 1, "target_qty": 2},
                {"id": "x", "name": "Bad id"},
                {"id": 3, "name": "", "category": "Food", "current_qty": 1, "target_qty": 2},
                {"id": 1, "name": "Duplicate id", "category": "Food", "current_qty": 1, "target_qty": 2},
                {"id": 4, "name": "Negative", "category": "Food", "current_qty": -5, "target_qty": 0},
            ],
            "next_id": 2,
        }))
        s = self.store()
        self.assertEqual([i["name"] for i in s.items], ["Good", "Negative"])
        self.assertEqual(s.find(4)["current_qty"], 0)
        self.assertEqual(s.find(4)["target_qty"], 1)
        self.assertEqual(s.next_id, 5)      # never lower than the highest id + 1


# ---------------------------------------------------------------- settings

class SettingsTests(TempFolderTest):
    def test_defaults_then_saved_settings(self):
        s = self.store()
        self.assertEqual(s.settings["categories"], core.DEFAULT_CATEGORIES)
        self.assertFalse(s.settings["setup_done"])
        s.settings["charity_name"] = "Hope House"
        s.settings["categories"] = ["Pet food", "Litter"]
        s.settings["setup_done"] = True
        s.save_settings()
        again = self.store()
        self.assertEqual(again.settings["charity_name"], "Hope House")
        self.assertEqual(again.settings["categories"], ["Pet food", "Litter"])
        self.assertTrue(again.settings["setup_done"])

    def test_bad_thresholds_are_repaired(self):
        self.folder.mkdir(parents=True)
        (self.folder / core.SETTINGS_FILENAME).write_text(json.dumps({
            "urgent_below_percent": "ninety", "low_below_percent": 10, "categories": [],
        }))
        s = self.store()
        self.assertEqual(s.settings["urgent_below_percent"], 50)   # default after garbage
        self.assertEqual(s.settings["low_below_percent"], 51)      # forced above urgent
        self.assertEqual(s.settings["categories"], core.DEFAULT_CATEGORIES)

    def test_thresholds_change_status(self):
        s = self.store()
        s.add_item("Soup", "Food", 6, 10)                  # 60%
        self.assertEqual(s.status_of(s.find(1)), "low")
        s.settings["urgent_below_percent"] = 70
        s.settings["low_below_percent"] = 90
        self.assertEqual(s.status_of(s.find(1)), "urgent")

    def test_categories_in_use_keeps_orphans_visible(self):
        s = self.store()
        s.add_item("Kibble", "Pet food", 1, 10)
        s.settings["categories"] = ["Food"]
        self.assertEqual(s.categories_in_use(), ["Food", "Pet food"])


# -------------------------------------------------------------- item changes

class ItemChangeTests(TempFolderTest):
    def test_duplicate_names_refused_case_insensitively(self):
        s = self.store()
        s.add_item("Soup", "Food", 1, 10)
        with self.assertRaises(ValueError):
            s.add_item("soup", "Food", 1, 10)

    def test_edit_rename_and_retarget(self):
        s = self.store()
        s.add_item("Soup", "Food", 1, 10)
        s.update_item(1, "Tinned soup", "Food", 4, 40)
        item = self.store().find(1)
        self.assertEqual((item["name"], item["current_qty"], item["target_qty"]), ("Tinned soup", 4, 40))

    def test_edit_cannot_steal_another_items_name(self):
        s = self.store()
        s.add_item("Soup", "Food", 1, 10)
        s.add_item("Rice", "Food", 1, 10)
        with self.assertRaises(ValueError):
            s.update_item(2, "SOUP", "Food", 1, 10)

    def test_delete_then_undo_brings_it_back(self):
        s = self.store()
        s.add_item("Soup", "Food", 1, 10)
        s.add_item("Rice", "Food", 1, 10)
        s.delete_item(1)
        self.assertEqual([i["name"] for i in s.items], ["Rice"])
        self.assertEqual(s.undo_label, "delete 'Soup'")
        self.assertEqual(s.undo(), "delete 'Soup'")
        self.assertEqual([i["name"] for i in self.store().items], ["Soup", "Rice"])

    def test_undo_walks_back_several_steps_and_is_saved(self):
        s = self.store()
        s.add_item("Soup", "Food", 1, 10)
        s.set_quantity(1, 5)
        s.set_quantity(1, 9)
        self.assertEqual(s.undo(), "change 'Soup' quantity 5 -> 9")
        self.assertEqual(s.undo(), "change 'Soup' quantity 1 -> 5")
        self.assertEqual(self.store().find(1)["current_qty"], 1)
        self.assertEqual(s.undo(), "add 'Soup'")
        self.assertEqual(self.store().items, [])
        self.assertIsNone(s.undo())

    def test_unchanged_quantity_is_not_an_undo_step(self):
        s = self.store()
        s.add_item("Soup", "Food", 5, 10)
        s.set_quantity(1, 5)
        self.assertEqual(s.undo_label, "add 'Soup'")

    def test_sample_items_and_legacy_import_skip_duplicates(self):
        s = self.store()
        s.add_item("Socks", "Clothing", 1, 5)
        added = s.load_sample_items()
        self.assertEqual(added, len(core.SAMPLE_ITEMS) - 1)
        self.assertEqual(s.find(1)["target_qty"], 5)          # the existing one was kept

        legacy = self.tmp / "inventory_data.json"
        legacy.write_text(json.dumps({"items": [
            {"id": 9, "name": "pillow", "category": "Food", "current_qty": 40, "target_qty": 40},
            {"id": 1, "name": "Socks", "category": "Clothing", "current_qty": 99, "target_qty": 99},
        ], "next_id": 10}))
        self.assertEqual(s.import_legacy_file(legacy), 1)
        self.assertTrue(s.name_taken("pillow"))
        self.assertEqual(s.find(1)["current_qty"], 1)

    def test_find_legacy_files_ignores_own_file(self):
        os.environ["SHELTER_INVENTORY_DATA"] = str(self.folder)
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmp)
            s = self.store()
            s.add_item("Soup", "Food", 1, 10)
            self.assertEqual(core.find_legacy_files(), [])
            (self.tmp / core.DATA_FILENAME).write_text("{}")
            self.assertEqual(core.find_legacy_files(), [(self.tmp / core.DATA_FILENAME).resolve()])
        finally:
            os.chdir(old_cwd)
            os.environ.pop("SHELTER_INVENTORY_DATA", None)


# ------------------------------------------------------------------ exports

class ExportTests(TempFolderTest):
    def seeded(self):
        s = self.store()
        s.settings["charity_name"] = "Hope House"
        s.add_item("Blankets", "Bedding", 30, 35)        # ok
        s.add_item("Winter coats", "Clothing", 3, 20)    # urgent
        s.add_item("Shampoo", "Hygiene", 40, 50)         # ok (80%)
        s.add_item("Socks", "Clothing", 25, 80)          # urgent (31%)
        s.add_item("Soap", "Hygiene", 7, 10)             # low
        return s

    def test_csv_has_every_item_worst_first(self):
        text = core.inventory_csv(self.seeded())
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], ",".join(core.CSV_COLUMNS))
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[1].startswith("Winter coats,Clothing,3,20,15,urgent,17"))
        self.assertTrue(lines[2].startswith("Socks,Clothing,25,80,31,urgent,55"))

    def test_needs_list_lists_only_needs_most_urgent_first(self):
        text = core.needs_list_text(self.seeded(), today=dt.date(2026, 9, 2))
        self.assertTrue(text.startswith("Hope House - What we need - 02 September 2026"))
        self.assertIn("MOST URGENT", text)
        self.assertIn("RUNNING LOW", text)
        self.assertLess(text.index("Winter coats"), text.index("Socks"))
        self.assertLess(text.index("Socks"), text.index("Soap"))
        self.assertNotIn("Blankets", text)
        self.assertNotIn("Shampoo", text)
        self.assertIn("need 17 more (we have 3 of 20)", text)
        self.assertIn(core.APP_URL, text)

    def test_needs_list_when_fully_stocked(self):
        s = self.store()
        s.add_item("Blankets", "Bedding", 35, 35)
        text = core.needs_list_text(s)
        self.assertIn("well stocked", text)
        self.assertTrue(text.startswith("Our shelter - What we need"))

    def test_write_text_file_creates_folders(self):
        target = self.tmp / "deep" / "er" / "needs.txt"
        core.write_text_file(target, "hello\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")


# ------------------------------------------------------------------ the api

class ApiTests(TempFolderTest):
    """The bridge the web page talks to. No window is opened."""

    def api(self):
        import shelter_inventory
        return shelter_inventory.Api(self.store())

    def test_state_shape(self):
        st = self.api().get_state()
        for key in ("items", "settings", "undo_label", "last_saved", "data_file", "folder", "version"):
            self.assertIn(key, st)
        self.assertTrue(st["ok"])

    def test_add_edit_delete_undo_round_trip(self):
        a = self.api()
        st = a.add_item("Soup", "Food", "5", "10")
        self.assertTrue(st["ok"]); self.assertEqual(st["items"][0]["name"], "Soup")
        self.assertEqual(a.set_quantity(1, "7")["items"][0]["current_qty"], 7)
        self.assertEqual(a.update_item("1", "Tinned soup", "Food", "7", "40")["items"][0]["target_qty"], 40)
        self.assertEqual(a.delete_item(1)["items"], [])
        self.assertEqual(a.undo()["items"][0]["name"], "Tinned soup")
        again = self.store()
        self.assertEqual(again.find(1)["name"], "Tinned soup")

    def test_errors_come_back_as_sentences(self):
        a = self.api()
        self.assertEqual(a.add_item("", "Food", "1", "1"), {"ok": False, "error": "Please enter an item name."})
        a.add_item("Soup", "Food", "1", "1")
        self.assertFalse(a.add_item("soup", "Food", "1", "1")["ok"])
        self.assertFalse(a.set_quantity(1, "-3")["ok"])

    def test_settings_validation_and_save(self):
        a = self.api()
        self.assertFalse(a.save_settings({"categories": []})["ok"])
        self.assertFalse(a.save_settings({"urgent_below_percent": 90, "low_below_percent": 10})["ok"])
        st = a.save_settings({"charity_name": " Hope House ", "categories": ["Pet food", "Pet food", "Litter"],
                              "urgent_below_percent": 30, "low_below_percent": 60, "setup_done": True})
        self.assertTrue(st["ok"])
        s = self.store().settings
        self.assertEqual((s["charity_name"], s["categories"], s["urgent_below_percent"], s["setup_done"]),
                         ("Hope House", ["Pet food", "Litter"], 30, True))

    def test_import_preview_and_commit_through_the_api(self):
        api = self.api()
        path = self.tmp / "stock.csv"
        path.write_text("Item,Category,Have,Need,Use by\nBeans,Food,12,40,31/03/2027\nSoap,Hygiene,3,20,\n", encoding="utf-8")
        api.store.add_item("Soap", "Hygiene", 1, 1)
        prev = api.preview_import(str(path))
        self.assertTrue(prev["ok"])
        self.assertEqual(prev["total"], 2)
        self.assertEqual(prev["duplicates"], 1)
        self.assertEqual(prev["mapping"]["current_qty"], "Have")
        self.assertEqual(prev["sample"][0]["expires"], "2027-03-31")
        self.assertEqual(len(api.store.items), 1, "preview must not change anything")
        res = api.import_file(str(path), "skip")
        self.assertTrue(res["ok"])
        self.assertEqual(res["import"], {"added": 1, "updated": 0, "skipped": 1})
        self.assertEqual(len(res["items"]), 2)
        bad = api.preview_import(str(self.tmp / "missing.csv"))
        self.assertFalse(bad["ok"])
        self.assertIn("Could not read", bad["error"])
        self.assertEqual(api.pick_import_file(), {"ok": False}, "no window -> no dialog, no crash")

    def test_expiry_through_the_api(self):
        api = self.api()
        res = api.add_item("Milk", "Food", 1, 2, "1/1/2028")
        self.assertEqual(res["items"][0]["expires"], "2028-01-01")
        self.assertIn("today", res)
        res = api.add_item("Bread", "Food", 1, 2, "soonish")
        self.assertFalse(res["ok"])
        self.assertIn("Use-by date", res["error"])
        res = api.save_settings({"expiry_warn_days": 400})
        self.assertFalse(res["ok"])
        res = api.save_settings({"expiry_warn_days": 14})
        self.assertEqual(res["settings"]["expiry_warn_days"], 14)

    def test_count_sheet_help_and_links_through_the_api(self):
        api = self.api()
        api.add_item("Socks", "Clothing", 1, 2)
        sheet = api.count_sheet()
        self.assertTrue(sheet["ok"])
        self.assertEqual(sheet["rows"][0]["name"], "Socks")
        self.assertIn("[______]", sheet["text"])
        self.assertEqual(api.save_count_sheet(), {"ok": False}, "no window -> no dialog")
        info = api.help_info()
        self.assertEqual(info["version"], core.APP_VERSION)
        self.assertEqual(info["support_email"], core.SUPPORT_EMAIL)
        self.assertFalse(api.open_link("nonsense")["ok"])
        opened = []
        import webbrowser
        real = webbrowser.open
        webbrowser.open = lambda url: opened.append(url) or True
        try:
            self.assertTrue(api.open_link("report")["ok"])
            self.assertTrue(api.open_link("site")["ok"])
        finally:
            webbrowser.open = real
        self.assertTrue(opened[0].startswith("mailto:"))
        self.assertEqual(opened[1], core.APP_URL)

    def test_needs_list_and_no_dialog_without_window(self):
        a = self.api()
        a.add_item("Soup", "Food", "1", "10")
        self.assertIn("Soup", a.needs_list())
        self.assertEqual(a.export_csv(), {"ok": False})     # no window -> no dialog -> nothing written


if __name__ == "__main__":
    unittest.main(verbosity=1)
