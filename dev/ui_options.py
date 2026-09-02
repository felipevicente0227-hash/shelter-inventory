"""
dev/ui_options.py - photograph every skin with the same sample data.

    xvfb-run -a -s "-screen 0 1100x760x24" python3 dev/ui_options.py

Writes dev/ui-<theme>.png for each theme and dev/ui-all.png stacked.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

tmp = Path(tempfile.mkdtemp(prefix="shelter-ui-"))
os.environ["SHELTER_INVENTORY_DATA"] = str(tmp)

import tkinter as tk  # noqa: E402

import inventory_core as core  # noqa: E402

store = core.Store()
store.load()
store.settings["charity_name"] = "Hope House"
store.settings["setup_done"] = True
store.save_settings()
store.load_sample_items()
store.add_item("Nappies (size 4)", "Hygiene", 4, 30)

shots = []
for theme in ["native", "paper", "clinic", "bigprint", "slate"]:
    os.environ["SHELTER_INVENTORY_THEME"] = theme
    import importlib
    import shelter_inventory_classic as gui
    importlib.reload(gui)
    root = tk.Tk()
    root.geometry(("1240x760" if theme == "bigprint" else "1040x680") + "+0+0")
    app = gui.App(root, store)
    socks = next(i for i in store.items if i["name"] == "Socks")
    root.update()
    app.tree.selection_set(str(socks["id"]))
    app.on_select()
    root.update()
    out = HERE / f"ui-{theme}.png"
    crop = "1240x800+0+0" if theme == "bigprint" else "1040x720+0+0"
    subprocess.run(["import", "-window", "root", "-crop", crop, str(out)], check=False)
    shots.append(out)
    root.destroy()
    print("shot", theme)

import subprocess as _sp
_sp.run([sys.executable.replace("python3.12","python3"), str(HERE / "ui_sheet.py")], check=False)
raise SystemExit(0)
from PIL import Image, ImageDraw  # noqa: E402

ims = [Image.open(p).convert("RGB") for p in shots]
labels = ["1  native", "2  paper", "3  clinic", "4  bigprint", "5  slate"]
w = 1040
gap = 40
h = sum(i.height for i in ims) + gap * len(ims)
sheet = Image.new("RGB", (w, h), "#808080")
y = 0
d = ImageDraw.Draw(sheet)
for im, label in zip(ims, labels):
    d.text((14, y + 12), label, fill="white")
    y += gap
    sheet.paste(im, (0, y))
    y += im.height
sheet.save(HERE / "ui-all.png")
print("sheet ->", HERE / "ui-all.png")
