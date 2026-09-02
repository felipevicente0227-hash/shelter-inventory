"""
shelter_inventory.py - the window.

Run it:            python shelter_inventory.py
Run the tests:     python tests.py

This file only draws things and reacts to clicks. Every decision about data -
where it is saved, what "urgent" means, what goes on the needs list - lives in
inventory_core.py, so the two can be read (and tested) separately.

============================================================
HOW THE WINDOW IS BUILT  (v0.3 - a plain, native-looking desktop app)
============================================================
  * The system's own font and widget style (ttk) - so it looks like the other
    programs on the volunteer's computer, not like a web page pretending.
  * One table (a ttk Treeview) for the whole inventory: sortable columns,
    keyboard navigation, hundreds of rows without slowing down.
  * A detail panel on the right for the selected item: change the quantity,
    edit, delete. An "Add item" bar along the bottom. A menu bar for the rest.
  * Colour is used only to mean something: a red dot means urgent, an amber
    dot means low, a green dot means fine. Nothing is decorated.
"""

import ctypes
import datetime as _dt
import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import inventory_core as core
from inventory_core import Store, StoreError

# ============================================================
# STEP 1: LOOK AND FEEL - five skins, one layout
# ============================================================
# A skin is a dictionary of colours and fonts. The layout never changes; only
# what it is painted with. Pick one in settings.json ("theme": "paper") or with
# the environment variable SHELTER_INVENTORY_THEME for a quick look.
#
#   native   - whatever Windows / macOS draws by default. Blends in.
#   paper    - warm off-white, serif headings, thin rules. A printed ledger.
#   clinic   - white, one deep green, generous spacing. Calm and modern.
#   bigprint - larger type, high contrast, wide rows. For tired eyes and old screens.
#   slate    - dark. For a laptop left on at a night shelter reception desk.

THEMES = {
    "native": {
        "ttk": None, "bg": None, "panel": None, "fg": "#1F1F1F", "muted": "#6B7280",
        "accent": "#1F1F1F", "field": None, "head_bg": None, "head_fg": None,
        "tree_bg": None, "select_bg": None, "select_fg": None,
        "row": {"urgent": "#FDF2F1", "low": "#FFF8EC", "ok": ""},
        "status": {"urgent": "#B42318", "low": "#B54708", "ok": "#1B7F4B"},
        "error": "#B42318", "button_bg": None, "button_fg": None,
        "title_family": None, "size": 10, "title_size": 17, "rowheight": 26,
    },
    "paper": {
        "ttk": "clam", "bg": "#F7F3EC", "panel": "#FDFBF7", "fg": "#2B2620", "muted": "#8A8073",
        "accent": "#2B2620", "field": "#FFFFFF", "head_bg": "#EFE9DF", "head_fg": "#5C5347",
        "tree_bg": "#FDFBF7", "select_bg": "#D9CDB8", "select_fg": "#2B2620",
        "row": {"urgent": "#F6E4DC", "low": "#F5ECD6", "ok": ""},
        "status": {"urgent": "#9C3B2B", "low": "#9A6A1B", "ok": "#4F6B3A"},
        "error": "#9C3B2B", "button_bg": "#EFE9DF", "button_fg": "#2B2620",
        "title_family": "serif", "size": 10, "title_size": 19, "rowheight": 28,
    },
    "clinic": {
        "ttk": "clam", "bg": "#FFFFFF", "panel": "#F4F7F5", "fg": "#17211B", "muted": "#6F7A73",
        "accent": "#0F5C3A", "field": "#FFFFFF", "head_bg": "#E8F0EB", "head_fg": "#0F5C3A",
        "tree_bg": "#FFFFFF", "select_bg": "#CFE6D8", "select_fg": "#17211B",
        "row": {"urgent": "#FCEDEA", "low": "#FFF6E3", "ok": ""},
        "status": {"urgent": "#B42318", "low": "#B54708", "ok": "#0F5C3A"},
        "error": "#B42318", "button_bg": "#0F5C3A", "button_fg": "#FFFFFF",
        "title_family": None, "size": 10, "title_size": 18, "rowheight": 30,
    },
    "bigprint": {
        "ttk": "clam", "bg": "#FFFFFF", "panel": "#F2F2F2", "fg": "#000000", "muted": "#444444",
        "accent": "#000000", "field": "#FFFFFF", "head_bg": "#DDDDDD", "head_fg": "#000000",
        "tree_bg": "#FFFFFF", "select_bg": "#FFE9A8", "select_fg": "#000000",
        "row": {"urgent": "#FFD9D4", "low": "#FFF0BF", "ok": ""},
        "status": {"urgent": "#A10000", "low": "#8A5A00", "ok": "#0A6B2A"},
        "error": "#A10000", "button_bg": "#1A1A1A", "button_fg": "#FFFFFF",
        "title_family": None, "size": 13, "title_size": 22, "rowheight": 36,
    },
    "slate": {
        "ttk": "clam", "bg": "#1E2229", "panel": "#262B33", "fg": "#E6E8EB", "muted": "#9AA3AE",
        "accent": "#E6E8EB", "field": "#2E343D", "head_bg": "#2E343D", "head_fg": "#C7CDD4",
        "tree_bg": "#232830", "select_bg": "#3C4A5E", "select_fg": "#FFFFFF",
        "row": {"urgent": "#3A2A2A", "low": "#3A3426", "ok": ""},
        "status": {"urgent": "#F28B82", "low": "#F2C26B", "ok": "#7FD1A0"},
        "error": "#F28B82", "button_bg": "#3C4A5E", "button_fg": "#FFFFFF",
        "title_family": None, "size": 10, "title_size": 17, "rowheight": 28,
    },
}
DEFAULT_THEME = "native"

DOT = "\u25cf"
STATUS_WORD = {"urgent": "Urgent", "low": "Low", "ok": "Fine"}
SORT_OPTIONS = [("Most needed first", "urgent"), ("Name A-Z", "name"), ("Lowest quantity", "qty")]
SHOW_OPTIONS = [("All items", "all"), ("Needs only (urgent + low)", "needs"), ("Urgent only", "urgent-only")]

# Filled in by apply_theme(); read by the widgets.
T = dict(THEMES[DEFAULT_THEME])


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


def apply_theme(root: tk.Tk, name: str):
    """Paint the whole app with one skin. Returns the font set."""
    global T
    T = dict(THEMES.get(name, THEMES[DEFAULT_THEME]))

    base = tkfont.nametofont("TkDefaultFont")
    family = base.actual("family")
    if sys.platform == "win32":
        family = "Segoe UI"
    size = T["size"]
    base.configure(family=family, size=size)
    for fname in ("TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(fname).configure(family=family, size=size)
        except tk.TclError:
            pass
    title_family = family
    if T["title_family"] == "serif":
        title_family = "Georgia" if sys.platform == "win32" else ("Georgia" if sys.platform == "darwin" else "DejaVu Serif")
    fonts = {
        "title": tkfont.Font(family=title_family, size=T["title_size"], weight="bold"),
        "h2": tkfont.Font(family=family, size=size + 1, weight="bold"),
        "body": tkfont.Font(family=family, size=size),
        "big": tkfont.Font(family=title_family, size=size + 4, weight="bold"),
        "small": tkfont.Font(family=family, size=max(8, size - 1)),
        "mono": tkfont.Font(family="Consolas" if sys.platform == "win32" else "Menlo", size=size),
    }

    style = ttk.Style(root)
    if T["ttk"]:
        style.theme_use(T["ttk"])
    else:
        preferred = {"win32": "vista", "darwin": "aqua"}.get(sys.platform, "clam")
        if preferred in style.theme_names():
            style.theme_use(preferred)

    bg = T["bg"] or style.lookup("TFrame", "background") or root.cget("bg")
    T["bg"] = bg
    T["panel"] = T["panel"] or bg
    root.configure(bg=bg)
    if T["ttk"]:                                   # custom skins paint everything
        style.configure(".", background=bg, foreground=T["fg"], fieldbackground=T["field"],
                        font=fonts["body"], bordercolor=T["head_bg"], lightcolor=bg, darkcolor=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=T["fg"])
        style.configure("TButton", background=T["button_bg"], foreground=T["button_fg"],
                        borderwidth=0, focusthickness=0, padding=(12, 6))
        style.map("TButton", background=[("active", T["select_bg"]), ("disabled", T["head_bg"])],
                  foreground=[("disabled", T["muted"])])
        style.configure("TEntry", fieldbackground=T["field"], foreground=T["fg"], padding=4,
                        insertcolor=T["fg"])
        style.configure("TCombobox", fieldbackground=T["field"], background=T["field"],
                        foreground=T["fg"], arrowcolor=T["fg"], padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", T["field"])],
                  foreground=[("readonly", T["fg"])], selectbackground=[("readonly", T["field"])],
                  selectforeground=[("readonly", T["fg"])])
        style.configure("TSpinbox", fieldbackground=T["field"], foreground=T["fg"], arrowcolor=T["fg"],
                        background=T["field"], padding=3)
        style.configure("Treeview", background=T["tree_bg"], fieldbackground=T["tree_bg"],
                        foreground=T["fg"], borderwidth=0)
        style.map("Treeview", background=[("selected", T["select_bg"])],
                  foreground=[("selected", T["select_fg"])])
        style.configure("Treeview.Heading", background=T["head_bg"], foreground=T["head_fg"],
                        relief="flat", padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", T["head_bg"])])
        style.configure("TScrollbar", background=T["head_bg"], troughcolor=bg, arrowcolor=T["muted"],
                        borderwidth=0)
        style.configure("TSeparator", background=T["head_bg"])
        root.option_add("*TCombobox*Listbox.background", T["field"])
        root.option_add("*TCombobox*Listbox.foreground", T["fg"])
        root.option_add("*TCombobox*Listbox.selectBackground", T["select_bg"])
        root.option_add("*TCombobox*Listbox.selectForeground", T["select_fg"])
    style.configure("Treeview", rowheight=T["rowheight"], font=fonts["body"])
    style.configure("Treeview.Heading", font=fonts["h2"])
    style.configure("Muted.TLabel", foreground=T["muted"], font=fonts["small"], background=bg)
    style.configure("Error.TLabel", foreground=T["error"], font=fonts["small"], background=bg)
    style.configure("Title.TLabel", font=fonts["title"], foreground=T["accent"], background=bg)
    style.configure("H2.TLabel", font=fonts["h2"], background=bg)
    style.configure("Big.TLabel", font=fonts["big"], background=T["panel"], foreground=T["fg"])
    style.configure("Detail.TFrame", background=T["panel"], relief="flat" if T["ttk"] else "groove",
                    borderwidth=0 if T["ttk"] else 1)
    style.configure("Panel.TLabel", background=T["panel"], foreground=T["fg"])
    style.configure("PanelMuted.TLabel", background=T["panel"], foreground=T["muted"], font=fonts["small"])
    style.configure("Panel.TFrame", background=T["panel"])
    return fonts


# ============================================================
# STEP 2: THE MAIN WINDOW
# ============================================================
class App:
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        theme = os.environ.get("SHELTER_INVENTORY_THEME") or store.settings.get("theme") or DEFAULT_THEME
        self.fonts = apply_theme(root, theme)
        self.sort_var = tk.StringVar(value="urgent")
        self.filter_var = tk.StringVar(value="all")
        self.search_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="All categories")
        self.selected_id = None

        root.title(self.window_title())
        root.geometry("1240x760" if T["size"] >= 12 else "1040x680")
        root.minsize(860, 540)
        root.report_callback_exception = self.on_unexpected_error

        self.build_menu()
        self.build_layout()
        self.bind_keys()
        self.render()

    # ------------------------------------------------------------ titles

    def window_title(self) -> str:
        name = self.store.settings.get("charity_name")
        return f"{name} - {core.APP_NAME}" if name else core.APP_NAME

    # ------------------------------------------------------------ menu

    def build_menu(self):
        menubar = tk.Menu(self.root)
        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="What we need list...", command=self.show_needs_list, accelerator="Ctrl+N")
        m_file.add_command(label="Export inventory as CSV...", command=self.export_csv, accelerator="Ctrl+E")
        m_file.add_separator()
        m_file.add_command(label="Open data folder", command=self.open_data_folder)
        m_file.add_command(label="Settings...", command=self.open_settings)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=False)
        m_edit.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        m_edit.add_separator()
        m_edit.add_command(label="Add item", command=lambda: self.entry_name.focus_set(), accelerator="Ctrl+A")
        m_edit.add_command(label="Edit selected item...", command=self.edit_selected, accelerator="F2")
        m_edit.add_command(label="Delete selected item", command=self.delete_selected, accelerator="Del")
        menubar.add_cascade(label="Edit", menu=m_edit)

        m_view = tk.Menu(menubar, tearoff=False)
        for label, val in SORT_OPTIONS:
            m_view.add_radiobutton(label=label, variable=self.sort_var, value=val, command=self.render)
        m_view.add_separator()
        for label, val in SHOW_OPTIONS:
            m_view.add_radiobutton(label=label, variable=self.filter_var, value=val, command=self.render)
        menubar.add_cascade(label="View", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="Where is my data?", command=self.show_where_data)
        m_help.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=m_help)
        self.root.config(menu=menubar)
        self.menu_edit = m_edit

    # ------------------------------------------------------------ layout

    def build_layout(self):
        pad = {"padx": 14, "pady": 0}

        # -- Status bar, packed first so it always keeps its strip ---------
        status = ttk.Frame(self.root)
        status.pack(fill="x", side="bottom")
        ttk.Separator(status).pack(fill="x")
        row = ttk.Frame(status)
        row.pack(fill="x", padx=14, pady=4)
        self.lbl_status = ttk.Label(row, text="", style="Muted.TLabel", anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True)
        ttk.Label(row, text=f"v{core.APP_VERSION}", style="Muted.TLabel").pack(side="right")

        # -- Add bar, above the status bar ---------------------------------
        addbar = ttk.Frame(self.root)
        addbar.pack(fill="x", side="bottom")
        ttk.Separator(addbar).pack(fill="x")
        form = ttk.Frame(addbar)
        form.pack(fill="x", padx=14, pady=(8, 6))
        ttk.Label(form, text="Add item", style="H2.TLabel").grid(row=0, column=0, padx=(0, 12), sticky="w")
        ttk.Label(form, text="Name", style="Muted.TLabel").grid(row=0, column=1, sticky="w")
        self.entry_name = ttk.Entry(form, width=22 if T["size"] >= 12 else 30)
        self.entry_name.grid(row=0, column=2, padx=(4, 12))
        ttk.Label(form, text="Category", style="Muted.TLabel").grid(row=0, column=3, sticky="w")
        self.combo_cat = ttk.Combobox(form, values=[], state="readonly", width=12 if T["size"] >= 12 else 16)
        self.combo_cat.grid(row=0, column=4, padx=(4, 12))
        ttk.Label(form, text="Have", style="Muted.TLabel").grid(row=0, column=5, sticky="w")
        self.entry_curr = ttk.Entry(form, width=7, justify="center")
        self.entry_curr.grid(row=0, column=6, padx=(4, 12))
        ttk.Label(form, text="Need", style="Muted.TLabel").grid(row=0, column=7, sticky="w")
        self.entry_tgt = ttk.Entry(form, width=7, justify="center")
        self.entry_tgt.grid(row=0, column=8, padx=(4, 12))
        ttk.Button(form, text="Add", command=self.add_item).grid(row=0, column=9)
        self.lbl_error = ttk.Label(form, text="", style="Error.TLabel")
        self.lbl_error.grid(row=0, column=10, padx=(12, 0), sticky="w")
        for entry in (self.entry_name, self.entry_curr, self.entry_tgt):
            entry.bind("<Return>", lambda e: self.add_item())

        # -- Header ----------------------------------------------------------
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=14, pady=(12, 6))
        self.lbl_title = ttk.Label(header, text="", style="Title.TLabel")
        self.lbl_title.pack(side="left")
        counts = ttk.Frame(header)
        counts.pack(side="left", padx=(16, 0), pady=(7, 0))
        self.lbl_counts = ttk.Label(counts, text="", style="Muted.TLabel")
        self.lbl_counts.pack(side="left")
        self.lbl_count_status = {}
        for st in ("urgent", "low", "ok"):
            lbl = tk.Label(counts, text="", fg=T["status"][st], font=self.fonts["small"], bg=T["bg"])
            lbl.pack(side="left", padx=(10, 0))
            self.lbl_count_status[st] = lbl
        ttk.Button(header, text="What we need", command=self.show_needs_list).pack(side="right")
        ttk.Button(header, text="Undo", command=self.undo).pack(side="right", padx=(0, 6))

        # -- Toolbar: search, category, show, sort ---------------------------
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=14, pady=(2, 6))
        ttk.Label(bar, text="Search", style="Muted.TLabel").pack(side="left")
        big = T["size"] >= 12
        self.entry_search = ttk.Entry(bar, textvariable=self.search_var, width=16 if big else 24)
        self.entry_search.pack(side="left", padx=(4, 14))
        self.search_var.trace_add("write", lambda *a: self.render())
        ttk.Label(bar, text="Category", style="Muted.TLabel").pack(side="left")
        self.combo_filter = ttk.Combobox(bar, textvariable=self.category_var, state="readonly", width=14 if big else 18)
        self.combo_filter.pack(side="left", padx=(4, 14))
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self.render())
        ttk.Label(bar, text="Show", style="Muted.TLabel").pack(side="left")
        self.combo_show = ttk.Combobox(bar, values=[l for l, _ in SHOW_OPTIONS], state="readonly", width=18 if big else 24)
        self.combo_show.current(0)
        self.combo_show.pack(side="left", padx=(4, 14))
        self.combo_show.bind("<<ComboboxSelected>>", self.on_show_changed)
        ttk.Label(bar, text="Sort", style="Muted.TLabel").pack(side="left")
        self.combo_sort = ttk.Combobox(bar, values=[l for l, _ in SORT_OPTIONS], state="readonly", width=17 if big else 22)
        self.combo_sort.current(0)
        self.combo_sort.pack(side="left", padx=(4, 0))
        self.combo_sort.bind("<<ComboboxSelected>>", self.on_sort_changed)

        # -- Main area: table + detail panel --------------------------------
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        table_box = ttk.Frame(main)
        table_box.grid(row=0, column=0, sticky="nsew")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        columns = ("name", "category", "current", "target", "pct", "status")
        self.tree = ttk.Treeview(table_box, columns=columns, show="headings", selectmode="browse")
        scale = T["size"] / 10
        headings = {"name": ("Item", 260, "w"), "category": ("Category", 120, "w"),
                    "current": ("Have", 70, "e"), "target": ("Need", 70, "e"),
                    "pct": ("%", 60, "e"), "status": ("Status", 110, "w")}
        for col in columns:
            text, width, anchor = headings[col]
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_by_column(c))
            self.tree.column(col, width=int(width * scale), minwidth=int(50 * scale),
                             anchor=anchor, stretch=(col == "name"))
        self.tree.tag_configure("urgent", background=T["row"]["urgent"], foreground=T["fg"])
        self.tree.tag_configure("low", background=T["row"]["low"], foreground=T["fg"])
        self.tree.tag_configure("ok", background=T["tree_bg"] or "", foreground=T["fg"])
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.lbl_empty = ttk.Label(table_box, text="", style="Muted.TLabel", justify="center")

        # detail panel
        self.detail = ttk.Frame(main, style="Detail.TFrame", padding=14, width=int(280 * (T["size"] / 10)))
        self.detail.grid(row=0, column=1, sticky="ns", padx=(12, 0))
        self.detail.grid_propagate(False)
        self.d_name = ttk.Label(self.detail, text="", style="Big.TLabel", wraplength=240, justify="left")
        self.d_name.pack(anchor="w")
        self.d_cat = ttk.Label(self.detail, text="", style="PanelMuted.TLabel")
        self.d_cat.pack(anchor="w", pady=(0, 12))
        self.d_status = ttk.Label(self.detail, text="", style="Panel.TLabel")
        self.d_status.pack(anchor="w", pady=(0, 14))

        qrow = ttk.Frame(self.detail, style="Panel.TFrame")
        qrow.pack(anchor="w", fill="x")
        ttk.Label(qrow, text="Have", style="PanelMuted.TLabel").pack(side="left")
        self.qty_var = tk.StringVar(value="")
        self.spin_qty = ttk.Spinbox(qrow, from_=0, to=999999, width=8, textvariable=self.qty_var, justify="center")
        self.spin_qty.pack(side="left", padx=(6, 6))
        self.spin_qty.bind("<Return>", lambda e: self.save_selected_quantity())
        self.d_target = ttk.Label(qrow, text="", style="PanelMuted.TLabel")
        self.d_target.pack(side="left")
        self.btn_save_qty = ttk.Button(self.detail, text="Save quantity", command=self.save_selected_quantity)
        self.btn_save_qty.pack(anchor="w", fill="x", pady=(10, 4))
        brow = ttk.Frame(self.detail, style="Panel.TFrame")
        brow.pack(anchor="w", fill="x", pady=(2, 0))
        self.btn_edit = ttk.Button(brow, text="Edit...", command=self.edit_selected)
        self.btn_edit.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_delete = ttk.Button(brow, text="Delete", command=self.delete_selected)
        self.btn_delete.pack(side="left", fill="x", expand=True)
        self.d_hint = ttk.Label(self.detail, text="Select an item in the list, or add one below.",
                                style="PanelMuted.TLabel", wraplength=240, justify="left")
        self.d_hint.pack(anchor="w", pady=(16, 0))

    def bind_keys(self):
        r = self.root
        r.bind("<Control-z>", lambda e: self.undo())
        r.bind("<Control-Z>", lambda e: self.undo())
        r.bind("<Control-n>", lambda e: self.show_needs_list())
        r.bind("<Control-e>", lambda e: self.export_csv())
        r.bind("<Control-a>", lambda e: (self.entry_name.focus_set(), "break")[1])
        r.bind("<Control-f>", lambda e: (self.entry_search.focus_set(), "break")[1])
        r.bind("<F2>", lambda e: self.edit_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())

    # ------------------------------------------------------------ toolbar

    def on_show_changed(self, _event=None):
        self.filter_var.set(SHOW_OPTIONS[self.combo_show.current()][1])
        self.render()

    def on_sort_changed(self, _event=None):
        self.sort_var.set(SORT_OPTIONS[self.combo_sort.current()][1])
        self.render()

    def sort_by_column(self, col):
        mapping = {"name": "name", "current": "qty", "status": "urgent", "pct": "urgent"}
        if col in mapping:
            self.sort_var.set(mapping[col])
            self.combo_sort.current([v for _, v in SORT_OPTIONS].index(mapping[col]))
            self.render()

    # ============================================================
    # STEP 3: RENDER - redraw everything from the store
    # ============================================================
    def visible_items(self):
        store = self.store
        # The View menu / Show box pick the status filter; the Category box
        # narrows further; the search box narrows further still.
        mode = self.filter_var.get()
        items = store.visible(self.sort_var.get(), mode if mode in {"all", "needs", "urgent-only"} else "all")
        cat = self.category_var.get()
        if cat and cat != "All categories":
            items = [i for i in items if i["category"] == cat]
        q = self.search_var.get().strip().lower()
        if q:
            items = [i for i in items if q in i["name"].lower() or q in i["category"].lower()]
        return items

    def render(self):
        store = self.store
        self.root.title(self.window_title())
        self.lbl_title.config(text=store.settings.get("charity_name") or "Inventory")

        cats = store.categories_in_use()
        current = self.combo_cat.get()
        self.combo_cat.config(values=cats)
        if current in cats:
            self.combo_cat.set(current)
        elif cats:
            self.combo_cat.current(0)
        chosen = self.category_var.get()
        self.combo_filter.config(values=["All categories"] + cats)
        if chosen not in cats:
            self.category_var.set("All categories")

        # Sync the boxes with the variables (the View menu can change them).
        self.combo_sort.current([v for _, v in SORT_OPTIONS].index(self.sort_var.get()))
        self.combo_show.current([v for _, v in SHOW_OPTIONS].index(self.filter_var.get()))

        # Table.
        keep = self.selected_id
        self.tree.delete(*self.tree.get_children())
        items = self.visible_items()
        for item in items:
            st = store.status_of(item)
            pct = core.get_pct(item["current_qty"], item["target_qty"])
            self.tree.insert("", "end", iid=str(item["id"]), tags=(st,), values=(
                item["name"], item["category"], item["current_qty"], item["target_qty"],
                f"{pct}%", STATUS_WORD[st]))
        if items:
            self.lbl_empty.place_forget()
            if keep is not None and self.tree.exists(str(keep)):
                self.tree.selection_set(str(keep))
                self.tree.see(str(keep))
        else:
            hint = ("No items yet.\nAdd your first item in the bar below, or use File > Settings to load examples."
                    if not store.items else "No items match this search or filter.")
            self.lbl_empty.config(text=hint)
            self.lbl_empty.place(relx=0.5, rely=0.4, anchor="center")
            self.selected_id = None

        # Header counts.
        c = store.counts()
        self.lbl_counts.config(text=f"{c['total']} item{'' if c['total'] == 1 else 's'}")
        for st, word in (("urgent", "urgent"), ("low", "low"), ("ok", "fine")):
            self.lbl_count_status[st].config(text=f"{DOT} {c[st]} {word}", bg=T["bg"])
        label = store.undo_label
        self.menu_edit.entryconfig(0, label=f"Undo {label}" if label else "Undo",
                                   state="normal" if label else "disabled")
        self.update_detail()
        self.refresh_status()

    def update_detail(self):
        item = self.store.find(self.selected_id) if self.selected_id is not None else None
        widgets = (self.spin_qty, self.btn_save_qty, self.btn_edit, self.btn_delete)
        if item is None:
            self.d_name.config(text="Nothing selected")
            self.d_cat.config(text="")
            self.d_status.config(text="")
            self.d_target.config(text="")
            self.qty_var.set("")
            for w in widgets:
                w.state(["disabled"])
            self.d_hint.config(text="Select an item in the list to change its quantity, edit it or delete it. "
                                    "Double-click a row to edit. Ctrl+Z undoes the last change.")
            return
        st = self.store.status_of(item)
        pct = core.get_pct(item["current_qty"], item["target_qty"])
        self.d_name.config(text=item["name"])
        self.d_cat.config(text=item["category"])
        self.d_status.config(text=f"{DOT} {STATUS_WORD[st]} - {pct}% of target", foreground=T["status"][st])
        self.d_target.config(text=f"of {item['target_qty']} needed")
        if self.root.focus_get() is not self.spin_qty:
            self.qty_var.set(str(item["current_qty"]))
        for w in widgets:
            w.state(["!disabled"])
        self.d_hint.config(text="Type the new count and press Enter or Save quantity. "
                                "Edit changes the name, category or target.")

    def refresh_status(self, message=None, error=False):
        if message is None:
            if self.store.last_error:
                message, error = f"NOT SAVED - {self.store.last_error}", True
            elif self.store.last_saved:
                message = f"Saved {self.store.last_saved:%H:%M:%S}  -  {self.store.data_file}"
            else:
                message = f"Your data will be saved to  {self.store.data_file}"
        self.lbl_status.config(text=message, style="Error.TLabel" if error else "Muted.TLabel")

    # ============================================================
    # STEP 4: ACTIONS - every button and key ends up here
    # ============================================================
    def on_select(self, _event=None):
        sel = self.tree.selection()
        self.selected_id = int(sel[0]) if sel else None
        self.update_detail()

    def guarded(self, action, *args):
        """Run a store action and turn its errors into things a person can see."""
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
        result = self.guarded(self.store.add_item, self.entry_name.get(), self.combo_cat.get(),
                              self.entry_curr.get(), self.entry_tgt.get())
        if result is not None:
            for entry in (self.entry_name, self.entry_curr, self.entry_tgt):
                entry.delete(0, tk.END)
            self.selected_id = result["id"]
            self.render()
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

    def save_selected_quantity(self):
        if self.selected_id is None:
            return
        self.save_quantity(self.selected_id, self.qty_var.get())
        self.tree.focus_set()

    def undo(self):
        label = self.guarded(self.store.undo)
        if label:
            self.refresh_status(f"Undid: {label}   (saved {self.store.last_saved:%H:%M:%S})")

    def edit_selected(self):
        item = self.store.find(self.selected_id) if self.selected_id is not None else None
        if item is None:
            return
        EditItemDialog(self, item)

    def delete_selected(self):
        item = self.store.find(self.selected_id) if self.selected_id is not None else None
        if item is None:
            return
        if not messagebox.askyesno("Delete item",
                                   f"Delete '{item['name']}'?\n\nYou can bring it back with Undo.",
                                   parent=self.root):
            return
        self.guarded(self.store.delete_item, item["id"])
        self.selected_id = None
        self.render()

    def open_settings(self):
        SettingsDialog(self)

    def open_data_folder(self):
        try:
            open_folder(self.store.folder)
        except OSError as err:
            messagebox.showerror("Could not open folder", f"{self.store.folder}\n\n{err}", parent=self.root)

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
        self.refresh_status(f"Exported CSV  -  {path}")

    def show_needs_list(self):
        NeedsListDialog(self)

    def show_where_data(self):
        messagebox.showinfo(
            "Where is my data?",
            f"Everything is saved automatically, after every change, to:\n\n{self.store.folder}\n\n"
            "inventory_data.json is your inventory (plain text).\n"
            "inventory_data.bak is the version before your last change.\n"
            "backups\\ holds one copy per day for the last 30 days.\n\n"
            "To back up, copy that folder to a USB stick or cloud drive.",
            parent=self.root)

    def show_about(self):
        messagebox.showinfo(
            "About",
            f"{core.APP_NAME} v{core.APP_VERSION}\n\n"
            "A free, open-source inventory tracker for shelters, food banks and small charities.\n"
            "No account, no internet, your data stays on this computer.\n\n"
            f"{core.APP_URL}",
            parent=self.root)

    # ============================================================
    # STEP 5: FIRST RUN
    # ============================================================
    def first_run(self):
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
            "Welcome", "What is the name of your charity or shelter?\n(You can change this later under File > Settings.)",
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

    def on_unexpected_error(self, exc_type, exc, tb):
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
    def __init__(self, app: App, title: str, width=440):
        super().__init__(app.root, bg=T["bg"])
        self.app = app
        self.title(title)
        self.resizable(False, False)
        self.transient(app.root)
        self.bind("<Escape>", lambda e: self.destroy())
        self.body = ttk.Frame(self, padding=16)
        self.body.pack(fill="both", expand=True)
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - width) // 2
        y = app.root.winfo_rooty() + 120
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    def labelled_entry(self, row, label, value="", width=28, justify="left"):
        ttk.Label(self.body, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=(6, 0), padx=(0, 10))
        entry = ttk.Entry(self.body, width=width, justify=justify)
        entry.insert(0, str(value))
        entry.grid(row=row, column=1, sticky="w", pady=(6, 0))
        return entry


class EditItemDialog(Dialog):
    def __init__(self, app: App, item: dict):
        super().__init__(app, f"Edit: {item['name']}")
        self.item = item
        self.e_name = self.labelled_entry(0, "Item name", item["name"], width=32)
        ttk.Label(self.body, text="Category", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        cats = app.store.categories_in_use()
        self.c_cat = ttk.Combobox(self.body, values=cats, state="readonly", width=30)
        self.c_cat.set(item["category"] if item["category"] in cats else cats[0])
        self.c_cat.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.e_curr = self.labelled_entry(2, "Have", item["current_qty"], width=10, justify="center")
        self.e_tgt = self.labelled_entry(3, "Need (target)", item["target_qty"], width=10, justify="center")
        self.lbl_err = ttk.Label(self.body, text="", style="Error.TLabel")
        self.lbl_err.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        btns = ttk.Frame(self.body)
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Delete item", command=self.delete).pack(side="left")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))
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
        if not messagebox.askyesno("Delete item",
                                   f"Delete '{self.item['name']}'?\n\nYou can bring it back with Undo.", parent=self):
            return
        try:
            self.app.store.delete_item(self.item["id"])
        except (ValueError, StoreError) as err:
            messagebox.showerror("Could not delete", str(err), parent=self)
        self.app.selected_id = None
        self.destroy()
        self.app.render()


class SettingsDialog(Dialog):
    def __init__(self, app: App):
        super().__init__(app, "Settings", width=520)
        s = app.store.settings
        self.e_name = self.labelled_entry(0, "Charity / shelter name", s["charity_name"], width=36)
        ttk.Label(self.body, text="Categories\n(one per line)", style="Muted.TLabel", justify="left").grid(
            row=1, column=0, sticky="nw", pady=(10, 0))
        self.t_cats = tk.Text(self.body, width=34, height=7, font=app.fonts["body"], relief="solid", bd=1,
                              bg=T["field"] or "white", fg=T["fg"], insertbackground=T["fg"])
        self.t_cats.insert("1.0", "\n".join(s["categories"]))
        self.t_cats.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self.e_urgent = self.labelled_entry(2, "Urgent when below (% of target)", s["urgent_below_percent"], width=6, justify="center")
        self.e_low = self.labelled_entry(3, "Low when below (% of target)", s["low_below_percent"], width=6, justify="center")
        ttk.Label(self.body, text="Look", style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.c_theme = ttk.Combobox(self.body, values=list(THEMES), state="readonly", width=14)
        self.c_theme.set(s.get("theme") or DEFAULT_THEME)
        self.c_theme.grid(row=4, column=1, sticky="w", pady=(6, 0))
        ttk.Label(self.body, text=f"Data folder:  {app.store.folder}", style="Muted.TLabel",
                  wraplength=460, justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.lbl_err = ttk.Label(self.body, text="", style="Error.TLabel")
        self.lbl_err.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        btns = ttk.Frame(self.body)
        btns.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Load example items", command=self.load_examples).pack(side="left")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))

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
            self.lbl_err.config(text="Urgent must be below Low, and both between 1 and 100.")
            return
        s = self.app.store.settings
        s["charity_name"] = self.e_name.get().strip()[:80]
        s["categories"] = cats
        s["urgent_below_percent"] = urgent
        s["low_below_percent"] = low
        theme_changed = self.c_theme.get() != (s.get("theme") or DEFAULT_THEME)
        s["theme"] = self.c_theme.get()
        try:
            self.app.store.save_settings()
        except StoreError as err:
            messagebox.showerror("Could not save settings", str(err), parent=self)
            return
        self.destroy()
        self.app.render()
        if theme_changed:
            messagebox.showinfo("Look changed", "The new look applies the next time you open the app.",
                                parent=self.app.root)


class NeedsListDialog(Dialog):
    def __init__(self, app: App):
        super().__init__(app, "What we need", width=640)
        self.text_value = core.needs_list_text(app.store)
        ttk.Label(self.body, text="Paste this into an email, a Facebook post, or print it for a donation drive.",
                  style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        box = tk.Text(self.body, font=app.fonts["mono"], width=74, height=18, relief="solid", bd=1, wrap="word",
                      bg=T["field"] or "white", fg=T["fg"])
        box.insert("1.0", self.text_value)
        box.config(state="disabled")
        box.grid(row=1, column=0, pady=(8, 0))
        btns = ttk.Frame(self.body)
        btns.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Copy to clipboard", command=self.copy).pack(side="left")
        ttk.Button(btns, text="Save as text file...", command=self.save).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

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
        self.app.refresh_status(f"Needs list saved  -  {path}")


# ============================================================
# STEP 7: START UP
# ============================================================
def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.withdraw()
    icon = resource_path("icon.ico")
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
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
