"""
dev/smoke_gui.py - drives the real window without a person, for a screenshot
and a sanity check that nothing crashes. Run on Linux under xvfb:

    SHELTER_INVENTORY_DATA=/tmp/shelter-smoke xvfb-run -a python3 dev/smoke_gui.py

Writes shot-main.png and shot-needs.png next to this script.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

tmp = Path(tempfile.mkdtemp(prefix="shelter-smoke-"))
os.environ["SHELTER_INVENTORY_DATA"] = str(tmp)

import tkinter as tk  # noqa: E402

import inventory_core as core  # noqa: E402
import shelter_inventory as gui  # noqa: E402


def shot(name):
    if shutil.which("import"):
        subprocess.run(["import", "-window", "root", str(HERE / name)], check=False)


store = core.Store()
store.load()
store.settings["charity_name"] = "Hope House"
store.settings["setup_done"] = True
store.save_settings()
store.load_sample_items()

root = tk.Tk()
app = gui.App(root, store)
root.update()

# --- exercise the main actions -------------------------------------------
app.entry_name.insert(0, "Nappies (size 4)")
app.combo_cat.set("Hygiene")
app.entry_curr.insert(0, "4")
app.entry_tgt.insert(0, "30")
app.add_item()
assert store.name_taken("Nappies (size 4)"), "add_item did not add"

app.entry_name.insert(0, "Nappies (size 4)")            # duplicate -> inline error
app.entry_curr.insert(0, "1"); app.entry_tgt.insert(0, "1")
app.add_item()
assert "already exists" in app.lbl_error.cget("text")
for e in (app.entry_name, app.entry_curr, app.entry_tgt):
    e.delete(0, tk.END)

item = next(i for i in store.items if i["name"] == "Socks")
app.save_quantity(item["id"], "70")
assert store.find(item["id"])["current_qty"] == 70
app.undo()
assert store.find(item["id"])["current_qty"] == 25

app.sort_var.set("urgent"); app.filter_var.set("all"); app.render()
root.update()
shot("shot-main.png")

dlg = gui.NeedsListDialog(app)
root.update()
shot("shot-needs.png")
dlg.destroy()

sd = gui.SettingsDialog(app)
sd.t_cats.insert(tk.END, "\nPet food")
sd.save()
assert "Pet food" in store.settings["categories"]
root.update()

ed = gui.EditItemDialog(app, store.find(item["id"]))
ed.e_name.delete(0, tk.END); ed.e_name.insert(0, "Warm socks")
ed.e_tgt.delete(0, tk.END); ed.e_tgt.insert(0, "90")
ed.save()
assert store.find(item["id"])["name"] == "Warm socks"
assert store.find(item["id"])["target_qty"] == 90
root.update()

# Reopen from disk: everything must still be there.
again = core.Store(); again.load()
assert again.settings["charity_name"] == "Hope House"
assert again.find(item["id"])["name"] == "Warm socks"
assert again.name_taken("Nappies (size 4)")
print("smoke OK -", len(again.items), "items persisted in", tmp)
root.destroy()
