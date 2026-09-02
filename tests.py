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


if __name__ == "__main__":
    unittest.main(verbosity=1)
