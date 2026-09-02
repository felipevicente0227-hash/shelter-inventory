"""
shelter_inventory.py - the window.

Run it:            python shelter_inventory.py
Run the tests:     python tests.py

This file only draws things and reacts to clicks. Every decision about data -
where it is saved, what "urgent" means, what goes on the needs list - lives in
inventory_core.py, so the two can be read (and tested) separately.

============================================================
WHAT CHANGED SINCE v0.1  (read this if you knew the old file)
============================================================
  * Data is saved to Documents\\ShelterInventory\\ on every computer, no matter
    how the app was started. v0.1 saved "wherever you launched it from", which
    is why edits seemed to disappear.
  * Every save is announced in the status bar; a failed save shows a red
    message box instead of failing silently.
  * Items can now be edited, renamed, re-targeted and deleted (with a
    confirmation), and there is an Undo button.
  * First run asks for the charity's name. Categories are editable in Settings.
  * Export CSV, and a one-click "What we need" list for donors.
"""

import ctypes
import datetime as _dt
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import inventory_core as core
from inventory_core import Store, StoreError

# ============================================================
# STEP 1: LOOK AND FEEL - colours and fonts in one place
# ============================================================
COL_BG        = "#EEEDE8"
COL_CARD      = "#F5F5F3"
COL_WHITE     = "#FFFFFF"
COL_LINE      = "#DDDDDD"
COL_TEXT      = "#1A1A18"
COL_MUTED     = "#6B6B67"
COL_NAVY      = "#0D3B66"
COL_BLUE      = "#185FA5"
COL_HEADER    = "#E8E8E5"

STATUS_FG = {"urgent": "#A32D2D", "low": "#854F0B", "ok": "#3B6D11"}
STATUS_BG = {"urgent": "#FCEBEB", "low": "#FAEEDA", "ok": "#EAF3DE"}
STATUS_LABEL = {"urgent": "URGENT", "low": "LOW", "ok": "OK"}

FONT_TITLE  = ("Arial", 18, "bold")
FONT_HEAD   = ("Arial", 12, "bold")
FONT_BODY   = ("Arial", 11)
FONT_SMALL  = ("Arial", 9)
FONT_TINY_B = ("Arial", 9, "bold")
FONT_STAT_N = ("Arial", 22, "bold")
FONT_STAT_L = ("Arial", 10)

SORT_OPTIONS = [("By need", "urgent"), ("A-Z", "name"), ("By qty", "qty")]


def button(parent, text, command, primary=False, danger=False, **kw):
    """One helper so every button looks the same."""
    bg = COL_BLUE if primary else ("#A32D2D" if danger else "#E4E4E0")
    fg = "white" if (primary or danger) else COL_TEXT
    options = dict(font=FONT_SMALL, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                   relief="flat", padx=10, pady=4, cursor="hand2")
    options.update(kw)
    return tk.Button(parent, text=text, command=command, **options)


def open_folder(path: Path) -> None:
    """Show a folder in Explorer / Finder / the file manager."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))                       # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ============================================================
# STEP 2: THE MAIN WINDOW
# ============================================================
class App:
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        self.sort_var = tk.StringVar(value="urgent")
        self.filter_var = tk.StringVar(value="all")

        root.title(self.window_title())
        root.geometry("980x740")
        root.minsize(840, 560)
        root.configure(bg=COL_BG)
        root.report_callback_exception = self.on_unexpected_error

        self.build_layout()
        self.render()

    # ------------------------------------------------------------ titles

    def window_title(self) -> str:
        name = self.store.settings.get("charity_name")
        return f"{name} - {core.APP_NAME}" if name else core.APP_NAME

    # ------------------------------------------------------------ layout

    def build_layout(self):
        # The status bar is packed FIRST so it always gets its strip at the
        # bottom - Tk hands out space in packing order, and on a small screen
        # whatever is packed last is what gets squeezed out.
        status = tk.Frame(self.root, bg=COL_HEADER, padx=12, pady=4)
        status.pack(fill="x", side="bottom")
        self.lbl_status = tk.Label(status, text="", font=FONT_SMALL, bg=COL_HEADER, fg=COL_MUTED, anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True)
        tk.Label(status, text=f"v{core.APP_VERSION}", font=FONT_SMALL, bg=COL_HEADER, fg=COL_MUTED).pack(side="right")

        main = tk.Frame(self.root, bg=COL_BG)
        main.pack(fill="both", expand=True, padx=20, pady=(16, 8))

        # -- Header -------------------------------------------------------
        hdr = tk.Frame(main, bg=COL_BG)
        hdr.pack(fill="x", pady=(0, 12))
        left = tk.Frame(hdr, bg=COL_BG)
        left.pack(side="left", fill="x", expand=True)
        self.lbl_title = tk.Label(left, text="", font=FONT_TITLE, bg=COL_BG, fg=COL_NAVY, anchor="w")
        self.lbl_title.pack(anchor="w")
        tk.Label(left, text="Track donated goods, compare stock to targets, and share what you need.",
                 font=FONT_SMALL, bg=COL_BG, fg=COL_MUTED).pack(anchor="w")
        right = tk.Frame(hdr, bg=COL_BG)
        right.pack(side="right")
        button(right, "Settings", self.open_settings).pack(side="right", padx=(6, 0))
        button(right, "Open data folder", self.open_data_folder).pack(side="right", padx=(6, 0))

        # -- Stats bar ----------------------------------------------------
        stats = tk.Frame(main, bg=COL_BG)
        stats.pack(fill="x", pady=(0, 12))
        stats.columnconfigure((0, 1, 2, 3), weight=1)
        self.lbl_total = self.stat_card(stats, 0, "Total items", COL_TEXT)
        self.lbl_urgent = self.stat_card(stats, 1, "Urgent", STATUS_FG["urgent"])
        self.lbl_low = self.stat_card(stats, 2, "Low", STATUS_FG["low"])
        self.lbl_ok = self.stat_card(stats, 3, "Well stocked", STATUS_FG["ok"])

        # -- Add item form -----------------------------------------------
        form = tk.Frame(main, bg=COL_WHITE, padx=14, pady=12,
                        highlightbackground=COL_LINE, highlightthickness=1)
        form.pack(fill="x", pady=(0, 10))
        tk.Label(form, text="ADD NEW ITEM", font=FONT_TINY_B, bg=COL_WHITE,
                 fg=COL_MUTED).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        for col, lbl in enumerate(["Item name", "Category", "Current qty", "Target qty", ""]):
            tk.Label(form, text=lbl, font=FONT_SMALL, bg=COL_WHITE,
                     fg=COL_MUTED).grid(row=1, column=col, sticky="w", padx=(0, 8))

        self.entry_name = tk.Entry(form, font=FONT_BODY, width=24, relief="solid", bd=1)
        self.entry_name.grid(row=2, column=0, padx=(0, 8), ipady=4)
        self.combo_cat = ttk.Combobox(form, values=[], state="readonly", font=FONT_BODY, width=16)
        self.combo_cat.grid(row=2, column=1, padx=(0, 8), ipady=4)
        self.entry_curr = tk.Entry(form, font=FONT_BODY, width=10, relief="solid", bd=1, justify="center")
        self.entry_curr.grid(row=2, column=2, padx=(0, 8), ipady=4)
        self.entry_tgt = tk.Entry(form, font=FONT_BODY, width=10, relief="solid", bd=1, justify="center")
        self.entry_tgt.grid(row=2, column=3, padx=(0, 8), ipady=4)
        button(form, "Add item", self.add_item, primary=True).grid(row=2, column=4, padx=(0, 4))
        self.lbl_error = tk.Label(form, text="", font=FONT_SMALL, bg=COL_WHITE, fg=STATUS_FG["urgent"])
        self.lbl_error.grid(row=3, column=0, columnspan=5, sticky="w", pady=(4, 0))
        for entry in (self.entry_name, self.entry_curr, self.entry_tgt):
            entry.bind("<Return>", lambda e: self.add_item())

        # -- Inventory section --------------------------------------------
        inv = tk.Frame(main, bg=COL_WHITE, padx=14, pady=12,
                       highlightbackground=COL_LINE, highlightthickness=1)
        inv.pack(fill="both", expand=True)

        top = tk.Frame(inv, bg=COL_WHITE)
        top.pack(fill="x", pady=(0, 6))
        tk.Label(top, text="INVENTORY", font=FONT_TINY_B, bg=COL_WHITE, fg=COL_MUTED).pack(side="left")
        actions = tk.Frame(top, bg=COL_WHITE)
        actions.pack(side="right")
        button(actions, "What we need", self.show_needs_list, primary=True).pack(side="right", padx=(6, 0))
        button(actions, "Export CSV", self.export_csv).pack(side="right", padx=(6, 0))
        self.btn_undo = button(actions, "Undo", self.undo)
        self.btn_undo.pack(side="right", padx=(6, 0))

        sort_row = tk.Frame(inv, bg=COL_WHITE)
        sort_row.pack(fill="x")
        tk.Label(sort_row, text="Sort: ", font=FONT_SMALL, bg=COL_WHITE, fg=COL_MUTED).pack(side="left")
        for label, val in SORT_OPTIONS:
            tk.Radiobutton(sort_row, text=label, variable=self.sort_var, value=val,
                           font=FONT_SMALL, bg=COL_WHITE, fg=COL_BLUE, activebackground=COL_WHITE,
                           selectcolor=COL_WHITE, cursor="hand2", command=self.render).pack(side="left", padx=4)

        self.filter_row = tk.Frame(inv, bg=COL_WHITE)
        self.filter_row.pack(fill="x", pady=(0, 8))

        hdr_row = tk.Frame(inv, bg=COL_HEADER)
        hdr_row.pack(fill="x")
        self.configure_columns(hdr_row)
        for col, heading in enumerate(["Item / Category", "Status", "Current", "Target", "%", "Update qty", ""]):
            tk.Label(hdr_row, text=heading, font=FONT_TINY_B, bg=COL_HEADER, fg=COL_MUTED,
                     padx=8, pady=4, anchor="w").grid(row=0, column=col, sticky="ew", padx=1)

        scroll_box = tk.Frame(inv, bg=COL_CARD)
        scroll_box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll_box, bg=COL_CARD, highlightthickness=0, height=160)
        scrollbar = tk.Scrollbar(scroll_box, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows = tk.Frame(self.canvas, bg=COL_CARD)
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.configure_columns(self.rows)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.rows_window, width=e.width))
        # Mouse wheel: Windows/Mac send <MouseWheel>, Linux sends Button-4/5.
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel)

    @staticmethod
    def configure_columns(frame):
        for col, weight in enumerate([3, 1, 1, 1, 1, 2, 1]):
            frame.columnconfigure(col, weight=weight)

    def stat_card(self, parent, col, label, colour):
        card = tk.Frame(parent, bg=COL_CARD, padx=14, pady=10)
        card.grid(row=0, column=col, sticky="ew", padx=(0, 8))
        tk.Label(card, text=label, font=FONT_STAT_L, bg=COL_CARD, fg=COL_MUTED).pack(anchor="w")
        value = tk.Label(card, text="0", font=FONT_STAT_N, bg=COL_CARD, fg=colour)
        value.pack(anchor="w")
        return value

    def on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(1, "units")
        elif event.delta:
            step = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(step, "units")

    # ============================================================
    # STEP 3: RENDER - redraw everything from the store
    # ============================================================
    def render(self):
        store = self.store
        self.lbl_title.config(text=self.window_title())
        self.root.title(self.window_title())

        # Category choices may have changed in Settings.
        cats = store.categories_in_use()
        current = self.combo_cat.get()
        self.combo_cat.config(values=cats)
        if current in cats:
            self.combo_cat.set(current)
        elif cats:
            self.combo_cat.current(0)
        self.rebuild_filter_row(cats)

        # Rows.
        for widget in self.rows.winfo_children():
            widget.destroy()
        visible = store.visible(self.sort_var.get(), self.filter_var.get())
        if not visible:
            hint = ("No items yet. Add your first item above, or open Settings to load example items."
                    if not store.items else "No items match this filter.")
            tk.Label(self.rows, text=hint, font=FONT_BODY, fg=COL_MUTED, bg=COL_CARD,
                     pady=20).grid(row=0, column=0, columnspan=7, sticky="ew")
        else:
            for idx, item in enumerate(visible):
                self.render_row(idx, item)

        # Stats and buttons.
        counts = store.counts()
        self.lbl_total.config(text=str(counts["total"]))
        self.lbl_urgent.config(text=str(counts["urgent"]))
        self.lbl_low.config(text=str(counts["low"]))
        self.lbl_ok.config(text=str(counts["ok"]))
        label = store.undo_label
        self.btn_undo.config(text=f"Undo {label}" if label else "Undo",
                             state="normal" if label else "disabled")
        self.refresh_status()

        self.rows.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def rebuild_filter_row(self, cats):
        for widget in self.filter_row.winfo_children():
            widget.destroy()
        tk.Label(self.filter_row, text="Show: ", font=FONT_SMALL, bg=COL_WHITE, fg=COL_MUTED).pack(side="left")
        options = [("All", "all")] + [(c, c) for c in cats] + [("Needs only", "needs"), ("Urgent only", "urgent-only")]
        valid = {v for _, v in options}
        if self.filter_var.get() not in valid:
            self.filter_var.set("all")
        for label, val in options:
            tk.Radiobutton(self.filter_row, text=label, variable=self.filter_var, value=val,
                           font=FONT_SMALL, bg=COL_WHITE, fg=COL_BLUE, activebackground=COL_WHITE,
                           selectcolor=COL_WHITE, cursor="hand2", command=self.render).pack(side="left", padx=3)

    def render_row(self, idx, item):
        curr, tgt = item["current_qty"], item["target_qty"]
        st = self.store.status_of(item)
        pct = core.get_pct(curr, tgt)
        fg, tint = STATUS_FG[st], STATUS_BG[st]
        row_bg = tint if idx % 2 == 0 else COL_WHITE

        cell = tk.Frame(self.rows, bg=row_bg, padx=8, pady=6)
        cell.grid(row=idx, column=0, sticky="ew", padx=(0, 1), pady=1)
        tk.Label(cell, text=item["name"], font=("Arial", 11, "bold"), bg=row_bg, fg=COL_TEXT, anchor="w").pack(anchor="w")
        tk.Label(cell, text=item["category"], font=FONT_SMALL, bg=row_bg, fg=COL_MUTED, anchor="w").pack(anchor="w")

        tk.Label(self.rows, text=STATUS_LABEL[st], font=FONT_TINY_B, bg=tint, fg=fg, width=8,
                 padx=4, pady=6).grid(row=idx, column=1, padx=1, pady=1, sticky="ew")
        tk.Label(self.rows, text=str(curr), font=FONT_BODY, bg=row_bg, fg=COL_TEXT, width=7,
                 pady=6).grid(row=idx, column=2, padx=1, pady=1)
        tk.Label(self.rows, text=str(tgt), font=FONT_BODY, bg=row_bg, fg=COL_MUTED, width=7,
                 pady=6).grid(row=idx, column=3, padx=1, pady=1)
        tk.Label(self.rows, text=f"{pct}%", font=FONT_BODY, bg=row_bg, fg=fg, width=6,
                 pady=6).grid(row=idx, column=4, padx=1, pady=1)

        ctrl = tk.Frame(self.rows, bg=row_bg, padx=4, pady=4)
        ctrl.grid(row=idx, column=5, padx=1, pady=1, sticky="ew")
        qty_var = tk.StringVar(value=str(curr))
        entry = tk.Entry(ctrl, textvariable=qty_var, width=6, font=("Arial", 10), justify="center")
        entry.pack(side="left", padx=(0, 4))
        iid = item["id"]
        entry.bind("<Return>", lambda e, v=qty_var, i=iid: self.save_quantity(i, v.get()))
        button(ctrl, "Save", lambda v=qty_var, i=iid: self.save_quantity(i, v.get()),
               primary=True, padx=6, pady=2).pack(side="left")

        edit_cell = tk.Frame(self.rows, bg=row_bg, padx=4, pady=4)
        edit_cell.grid(row=idx, column=6, padx=1, pady=1, sticky="ew")
        button(edit_cell, "Edit", lambda i=iid: self.edit_item(i), padx=6, pady=2).pack()

    def refresh_status(self, message=None, error=False):
        if message is None:
            if self.store.last_error:
                message, error = f"NOT SAVED - {self.store.last_error}", True
            elif self.store.last_saved:
                message = f"Saved {self.store.last_saved:%H:%M:%S}  ->  {self.store.data_file}"
            else:
                message = f"Your data will be saved to  {self.store.data_file}"
        self.lbl_status.config(text=message, fg=STATUS_FG["urgent"] if error else STATUS_FG["ok"] if "Saved " in message else COL_MUTED)

    # ============================================================
    # STEP 4: ACTIONS - every button ends up here
    # ============================================================
    def guarded(self, action, *args):
        """Run a store action and turn its errors into things a person can see.

        ValueError  -> the person typed something invalid: show it inline.
        StoreError  -> the disk said no: red status bar AND a message box,
                       because a silent failure is how v0.1 lost data.
        """
        try:
            result = action(*args)
        except ValueError as err:
            self.lbl_error.config(text=str(err))
            return None
        except StoreError as err:
            self.refresh_status(str(err).splitlines()[0], error=True)
            messagebox.showerror("Could not save", str(err), parent=self.root)
            self.render()
            return None
        self.lbl_error.config(text="")
        self.render()
        return result

    def add_item(self):
        name = self.entry_name.get()
        result = self.guarded(self.store.add_item, name, self.combo_cat.get(),
                              self.entry_curr.get(), self.entry_tgt.get())
        if result is not None:
            for entry in (self.entry_name, self.entry_curr, self.entry_tgt):
                entry.delete(0, tk.END)
            self.entry_name.focus_set()

    def save_quantity(self, item_id, qty_str):
        try:
            self.store.set_quantity(item_id, qty_str)
        except ValueError as err:
            messagebox.showerror("Invalid quantity", str(err), parent=self.root)
            return
        except StoreError as err:
            self.refresh_status(str(err).splitlines()[0], error=True)
            messagebox.showerror("Could not save", str(err), parent=self.root)
        self.render()

    def undo(self):
        label = self.guarded(self.store.undo)
        if label:
            self.refresh_status(f"Undid: {label}   (saved {self.store.last_saved:%H:%M:%S})")

    def edit_item(self, item_id):
        item = self.store.find(item_id)
        if item is None:
            self.render()
            return
        EditItemDialog(self, item)

    def open_settings(self):
        SettingsDialog(self)

    def open_data_folder(self):
        try:
            open_folder(self.store.folder)
        except OSError as err:
            messagebox.showerror("Could not open folder",
                                 f"{self.store.folder}\n\n{err}", parent=self.root)

    def export_csv(self):
        default = f"inventory-{_dt.date.today():%Y-%m-%d}.csv"
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export inventory as CSV",
            initialdir=str(self.store.folder), initialfile=default,
            defaultextension=".csv", filetypes=[("CSV (opens in Excel)", "*.csv")])
        if not path:
            return
        try:
            core.write_text_file(Path(path), core.inventory_csv(self.store))
        except OSError as err:
            messagebox.showerror("Export failed", str(err), parent=self.root)
            return
        self.refresh_status(f"Exported CSV  ->  {path}")

    def show_needs_list(self):
        NeedsListDialog(self)

    # ============================================================
    # STEP 5: FIRST RUN - what happens the very first time
    # ============================================================
    def first_run(self):
        """Ask the two questions a new charity needs to answer, then never again."""
        store = self.store
        legacy = core.find_legacy_files()
        if legacy and not store.items:
            path = legacy[0]
            if messagebox.askyesno(
                    "Older save file found",
                    f"An inventory file from an earlier version was found here:\n\n{path}\n\n"
                    f"Import those items into your new data folder?\n\n{store.folder}",
                    parent=self.root):
                try:
                    added = store.import_legacy_file(path)
                    messagebox.showinfo("Imported", f"Imported {added} item(s).", parent=self.root)
                except (StoreError, OSError, ValueError) as err:
                    messagebox.showerror("Import failed", str(err), parent=self.root)

        name = simpledialog.askstring(
            "Welcome", "What is the name of your charity or shelter?\n(You can change this later in Settings.)",
            parent=self.root)
        if name and name.strip():
            store.settings["charity_name"] = name.strip()[:80]

        if not store.items and messagebox.askyesno(
                "Example items",
                "Start with a few example items so you can see how it works?\n\n"
                "(Choose No to start with an empty list.)", parent=self.root):
            try:
                store.load_sample_items()
            except StoreError as err:
                messagebox.showerror("Could not save", str(err), parent=self.root)

        store.settings["setup_done"] = True
        try:
            store.save_settings()
        except StoreError as err:
            messagebox.showerror("Could not save settings", str(err), parent=self.root)
        self.render()

    # ------------------------------------------------------------ safety net

    def on_unexpected_error(self, exc_type, exc, tb):
        """Any bug we did not foresee gets written to log.txt and shown,
        rather than printed to a console nobody can see."""
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        self.store.log("unexpected error\n" + text)
        messagebox.showerror(
            "Something went wrong",
            f"{exc_type.__name__}: {exc}\n\nDetails were written to:\n{self.store.log_file}",
            parent=self.root)


# ============================================================
# STEP 6: DIALOGS
# ============================================================
class Dialog(tk.Toplevel):
    """Small base class: centred over the main window, modal, Escape closes."""

    def __init__(self, app: App, title: str, width=440):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.configure(bg=COL_WHITE, padx=18, pady=14)
        self.resizable(False, False)
        self.transient(app.root)
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - width) // 2
        y = app.root.winfo_rooty() + 120
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def labelled_entry(self, row, label, value="", width=28, justify="left"):
        tk.Label(self, text=label, font=FONT_SMALL, bg=COL_WHITE, fg=COL_MUTED).grid(
            row=row, column=0, sticky="w", pady=(6, 0))
        entry = tk.Entry(self, font=FONT_BODY, width=width, relief="solid", bd=1, justify=justify)
        entry.insert(0, str(value))
        entry.grid(row=row, column=1, sticky="w", pady=(6, 0), ipady=3)
        return entry


class EditItemDialog(Dialog):
    def __init__(self, app: App, item: dict):
        super().__init__(app, f"Edit: {item['name']}")
        self.item = item
        self.e_name = self.labelled_entry(0, "Item name", item["name"])
        tk.Label(self, text="Category", font=FONT_SMALL, bg=COL_WHITE, fg=COL_MUTED).grid(row=1, column=0, sticky="w", pady=(6, 0))
        cats = app.store.categories_in_use()
        self.c_cat = ttk.Combobox(self, values=cats, state="readonly", font=FONT_BODY, width=26)
        self.c_cat.set(item["category"] if item["category"] in cats else cats[0])
        self.c_cat.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.e_curr = self.labelled_entry(2, "Current qty", item["current_qty"], width=10, justify="center")
        self.e_tgt = self.labelled_entry(3, "Target qty", item["target_qty"], width=10, justify="center")
        self.lbl_err = tk.Label(self, text="", font=FONT_SMALL, bg=COL_WHITE, fg=STATUS_FG["urgent"])
        self.lbl_err.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = tk.Frame(self, bg=COL_WHITE)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        button(btns, "Delete item", self.delete, danger=True).pack(side="left")
        button(btns, "Save changes", self.save, primary=True).pack(side="right")
        button(btns, "Cancel", self.destroy).pack(side="right", padx=(0, 6))
        self.e_name.focus_set()
        self.bind("<Return>", lambda e: self.save())

    def save(self):
        try:
            self.app.store.update_item(self.item["id"], self.e_name.get(), self.c_cat.get(),
                                       self.e_curr.get(), self.e_tgt.get())
        except ValueError as err:
            self.lbl_err.config(text=str(err))
            return
        except StoreError as err:
            messagebox.showerror("Could not save", str(err), parent=self)
            self.app.refresh_status(str(err).splitlines()[0], error=True)
        self.destroy()
        self.app.render()

    def delete(self):
        if not messagebox.askyesno(
                "Delete item",
                f"Delete '{self.item['name']}' from the inventory?\n\n"
                "You can bring it back with the Undo button.", parent=self):
            return
        try:
            self.app.store.delete_item(self.item["id"])
        except (ValueError, StoreError) as err:
            messagebox.showerror("Could not delete", str(err), parent=self)
        self.destroy()
        self.app.render()


class SettingsDialog(Dialog):
    def __init__(self, app: App):
        super().__init__(app, "Settings", width=520)
        s = app.store.settings
        self.e_name = self.labelled_entry(0, "Charity / shelter name", s["charity_name"], width=36)

        tk.Label(self, text="Categories (one per line)", font=FONT_SMALL, bg=COL_WHITE,
                 fg=COL_MUTED).grid(row=1, column=0, sticky="nw", pady=(10, 0))
        self.t_cats = tk.Text(self, font=FONT_BODY, width=34, height=7, relief="solid", bd=1)
        self.t_cats.insert("1.0", "\n".join(s["categories"]))
        self.t_cats.grid(row=1, column=1, sticky="w", pady=(10, 0))

        self.e_urgent = self.labelled_entry(2, "URGENT when below (% of target)", s["urgent_below_percent"], width=6, justify="center")
        self.e_low = self.labelled_entry(3, "LOW when below (% of target)", s["low_below_percent"], width=6, justify="center")

        tk.Label(self, text=f"Your data folder:\n{app.store.folder}", font=FONT_SMALL, bg=COL_WHITE,
                 fg=COL_MUTED, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.lbl_err = tk.Label(self, text="", font=FONT_SMALL, bg=COL_WHITE, fg=STATUS_FG["urgent"])
        self.lbl_err.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = tk.Frame(self, bg=COL_WHITE)
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        button(btns, "Load example items", self.load_examples).pack(side="left")
        button(btns, "Save", self.save, primary=True).pack(side="right")
        button(btns, "Cancel", self.destroy).pack(side="right", padx=(0, 6))

    def load_examples(self):
        try:
            added = self.app.store.load_sample_items()
        except StoreError as err:
            messagebox.showerror("Could not save", str(err), parent=self)
            return
        messagebox.showinfo("Example items", f"Added {added} example item(s).", parent=self)
        self.app.render()

    def save(self):
        cats = [line.strip() for line in self.t_cats.get("1.0", tk.END).splitlines() if line.strip()]
        if not cats:
            self.lbl_err.config(text="Please keep at least one category.")
            return
        try:
            urgent = int(self.e_urgent.get().strip())
            low = int(self.e_low.get().strip())
        except ValueError:
            self.lbl_err.config(text="The two percentages must be whole numbers.")
            return
        if not (1 <= urgent < low <= 100):
            self.lbl_err.config(text="URGENT must be below LOW, and both between 1 and 100.")
            return
        s = self.app.store.settings
        s["charity_name"] = self.e_name.get().strip()[:80]
        s["categories"] = cats
        s["urgent_below_percent"] = urgent
        s["low_below_percent"] = low
        try:
            self.app.store.save_settings()
        except StoreError as err:
            messagebox.showerror("Could not save settings", str(err), parent=self)
            return
        self.destroy()
        self.app.render()


class NeedsListDialog(Dialog):
    """Shows the 'What we need' list with Copy and Save buttons."""

    def __init__(self, app: App):
        super().__init__(app, "What we need", width=620)
        self.text_value = core.needs_list_text(app.store)
        tk.Label(self, text="Paste this into an email, a Facebook post, or print it for a donation drive.",
                 font=FONT_SMALL, bg=COL_WHITE, fg=COL_MUTED).grid(row=0, column=0, sticky="w")
        box = tk.Text(self, font=("Consolas", 10) if sys.platform == "win32" else ("Courier", 11),
                      width=72, height=18, relief="solid", bd=1, wrap="word")
        box.insert("1.0", self.text_value)
        box.config(state="disabled")
        box.grid(row=1, column=0, pady=(6, 0))
        btns = tk.Frame(self, bg=COL_WHITE)
        btns.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        button(btns, "Copy to clipboard", self.copy, primary=True).pack(side="left")
        button(btns, "Save as text file", self.save).pack(side="left", padx=(6, 0))
        button(btns, "Close", self.destroy).pack(side="right")

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text_value)
        self.app.refresh_status("Needs list copied to the clipboard - paste it anywhere.")

    def save(self):
        default = f"what-we-need-{_dt.date.today():%Y-%m-%d}.txt"
        path = filedialog.asksaveasfilename(
            parent=self, title="Save needs list", initialdir=str(self.app.store.folder),
            initialfile=default, defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not path:
            return
        try:
            core.write_text_file(Path(path), self.text_value)
        except OSError as err:
            messagebox.showerror("Save failed", str(err), parent=self)
            return
        self.app.refresh_status(f"Needs list saved  ->  {path}")


# ============================================================
# STEP 7: START UP
# ============================================================
def resource_path(name: str) -> Path:
    """Files bundled into the .exe are unpacked to sys._MEIPASS at run time."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def main():
    if sys.platform == "win32":
        try:                                   # crisp text on high-DPI screens
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()                            # hidden until data is loaded
    icon = resource_path("icon.ico")
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:                    # not Windows, or no .ico support
            pass
    store = Store()
    try:
        store.load()
    except StoreError as err:
        messagebox.showerror("Could not read your inventory", str(err))
        root.destroy()
        return

    app = App(root, store)
    root.deiconify()
    if store.recovered_from_backup:
        messagebox.showinfo(
            "Recovered from backup",
            "The inventory file was damaged, so the previous good copy was loaded instead.\n\n"
            f"The damaged file was kept in:\n{store.folder}", parent=root)
    if not store.settings.get("setup_done"):
        app.first_run()
    root.mainloop()


if __name__ == "__main__":
    main()
