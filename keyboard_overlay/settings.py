"""Settings UI, persistence, backgrounds, and individual key customization."""

import json
import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk
from uuid import uuid4

from PIL import Image

from .background_editor import (
    BackgroundCropDialog,
    GifBackgroundCropDialog,
    VideoBackgroundCropDialog,
)
from .layouts import load_layouts


DEFAULTS = {
    "opacity": 100,
    "text_color": "#ffffff",
    "outline_color": "#ffffff",
    "key_fill": None,
    "pressed_color": "#38d6e8",
    "font_family": "Segoe UI",
    "font_size": 9,
    "lock_key": "Shift",
    "background_image": "",
    "background_gif": "",
    "background_gif_crop": None,
    "background_video": "",
    "background_video_crop": None,
    "mouse_background_image": "",
    "mouse_background_gif": "",
    "mouse_background_gif_crop": None,
    "mouse_background_video": "",
    "mouse_background_video_crop": None,
    "keyboard_scale": 100,
    "layout_name": "",
    "compact": False,
    "view_mode": "keyboard",
    "theme": "light",
    "key_overrides": {},
}

THEMES = {
    "light": {
        "BG": "#f3f6fa",
        "CARD": "#ffffff",
        "TEXT": "#172033",
        "MUTED": "#69758a",
        "ACCENT": "#2589d8",
        "LINE": "#e5eaf1",
        "PREVIEW_BG": "#eaf2f9",
        "BTN_BG": "#edf3f8",
        "BTN_ACTIVE": "#dfeaf3",
        "BTN_FG": "#172033",
    },
    "dark": {
        "BG": "#1e1e1e",
        "CARD": "#252526",
        "TEXT": "#cccccc",
        "MUTED": "#858585",
        "ACCENT": "#007acc",
        "LINE": "#3e3e42",
        "PREVIEW_BG": "#2d2d30",
        "BTN_BG": "#3e3e42",
        "BTN_ACTIVE": "#4e4e52",
        "BTN_FG": "#ffffff",
    },
}

LOCK_KEY_CHOICES = (
    "Shift",
    "Ctrl",
    "Alt",
    "Caps Lock",
    "Scroll Lock",
    "Pause",
    *(f"F{i}" for i in range(1, 13)),
)

IMAGE_FILETYPES = [
    ("Images", "*.png *.jpg *.jpeg *.bmp *.webp"),
    ("All files", "*.*"),
]
VIDEO_FILETYPES = [
    ("Videos", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
    ("All files", "*.*"),
]
GIF_FILETYPES = [
    ("GIF images", "*.gif"),
    ("All files", "*.*"),
]


def settings_path():
    root = Path(
        os.environ.get(
            "APPDATA",
            Path.home() / "AppData" / "Roaming",
        )
    )
    folder = root / "KeyTap-Overlay"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "settings.json"

    if not path.exists():
        for old_folder in ("KeyView", "KeyboardOverlay"):
            old_path = root / old_folder / "settings.json"
            if old_path.exists():
                path.write_bytes(old_path.read_bytes())
                break

    return path


def load_settings():
    try:
        loaded = json.loads(settings_path().read_text(encoding="utf-8"))
        settings = {**DEFAULTS, **loaded}

        settings["keyboard_scale"] = min(
            150,
            max(50, int(settings.get("keyboard_scale", 100))),
        )

        if not isinstance(settings.get("key_overrides"), dict):
            settings["key_overrides"] = {}

        if settings.get("background_video"):
            settings["background_image"] = ""
            settings["background_gif"] = ""
        elif settings.get("background_gif"):
            settings["background_image"] = ""

        if settings.get("mouse_background_video"):
            settings["mouse_background_image"] = ""
            settings["mouse_background_gif"] = ""
        elif settings.get("mouse_background_gif"):
            settings["mouse_background_image"] = ""

        if settings.get("view_mode") not in ("keyboard", "mouse", "both"):
            settings["view_mode"] = "keyboard"
        if settings.get("theme") not in ("light", "dark"):
            settings["theme"] = "light"

        return settings
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)


def save_settings(settings):
    settings_path().write_text(
        json.dumps(settings, indent=2),
        encoding="utf-8",
    )


def readable_on(color):
    if not color:
        return "#ffffff"
    try:
        rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
        return "#172033" if sum(rgb) > 390 else "#ffffff"
    except (ValueError, TypeError):
        return "#ffffff"


def copy_background_image(source_path, prefix="keyboard-background"):
    source = Path(source_path)
    folder = settings_path().parent / "backgrounds"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{prefix}-{uuid4().hex}{source.suffix.lower()}"
    shutil.copy2(source, target)
    return str(target)


class KeyCustomizerDialog:
    """Customize individual keys in the selected complete keyboard layout."""

    def __init__(self, parent, settings, layouts, on_save):
        self.parent = parent
        self.settings = settings
        self.layouts = layouts
        self.on_save = on_save
        self.theme = THEMES.get(settings.get("theme", "light"), THEMES["light"])
        self.overrides = json.loads(
            json.dumps(settings.get("key_overrides", {}))
        )
        self.selected_key = None
        self.keys_ui = {}

        saved_layout = settings.get("layout_name", "")
        if saved_layout not in layouts:
            saved_layout = next(
                (
                    name for name, item in layouts.items()
                    if item.get("group") == "PC"
                ),
                next(iter(layouts)),
            )
        self.layout_name = saved_layout

        self.window = tk.Toplevel(parent)
        self.window.title("Customize Keys")
        self.window.transient(parent)
        self.window.attributes("-topmost", True)
        self.window.configure(bg=self.theme["BG"])
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        top = tk.Frame(
            self.window,
            bg=self.theme["CARD"],
            padx=12,
            pady=9,
        )
        top.pack(fill="x")

        tk.Label(
            top,
            text="Choose a layout, then click any key to edit it.",
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self.layout_var = tk.StringVar(value=self.layout_name)
        self.layout_box = ttk.Combobox(
            top,
            textvariable=self.layout_var,
            values=list(self.layouts),
            state="readonly",
            width=28,
        )
        self.layout_box.pack(side="left", padx=(12, 0))
        self.layout_box.bind("<<ComboboxSelected>>", self.change_layout)

        tk.Button(
            top,
            text="Reset all keys",
            command=self.reset_all,
            bg="#d93838",
            fg="#ffffff",
            relief="flat",
            padx=9,
            pady=4,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            top,
            text="Close",
            command=self.close,
            bg=self.theme["ACCENT"],
            fg="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="right")

        body = tk.Frame(self.window, bg=self.theme["BG"], padx=12, pady=12)
        body.pack(fill="both", expand=True)

        preview = tk.Frame(body, bg=self.theme["BG"])
        preview.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(
            preview,
            bg=self.theme["PREVIEW_BG"],
            highlightthickness=0,
            width=850,
            height=540,
        )
        xbar = ttk.Scrollbar(
            preview,
            orient="horizontal",
            command=self.canvas.xview,
        )
        ybar = ttk.Scrollbar(
            preview,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.canvas.configure(
            xscrollcommand=xbar.set,
            yscrollcommand=ybar.set,
        )
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.keyboard_frame = tk.Frame(
            self.canvas,
            bg=self.theme["PREVIEW_BG"],
            padx=10,
            pady=10,
        )
        self.canvas.create_window(
            (0, 0),
            window=self.keyboard_frame,
            anchor="nw",
        )
        self.keyboard_frame.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            ),
        )

        self.side_panel = tk.Frame(
            body,
            bg=self.theme["CARD"],
            padx=14,
            pady=14,
            width=245,
            highlightbackground=self.theme["LINE"],
            highlightthickness=1,
        )
        self.side_panel.pack(side="right", fill="y", padx=(12, 0))
        self.side_panel.pack_propagate(False)
        self._show_empty_panel()

        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        self.window.geometry(
            f"{min(1320, screen_width - 30)}x"
            f"{min(760, screen_height - 80)}"
        )
        self.window.minsize(
            min(900, screen_width - 30),
            min(560, screen_height - 80),
        )

        self.draw_layout()

    def _show_empty_panel(self):
        for child in self.side_panel.winfo_children():
            child.destroy()
        tk.Label(
            self.side_panel,
            text="Select a key",
            bg=self.theme["CARD"],
            fg=self.theme["MUTED"],
            font=("Segoe UI", 10),
        ).pack(expand=True)

    def change_layout(self, _event=None):
        name = self.layout_var.get()
        if name in self.layouts:
            self.layout_name = name
            self.draw_layout()
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)

    def draw_layout(self):
        for child in self.keyboard_frame.winfo_children():
            child.destroy()
        self.keys_ui = {}

        layout = self.layouts[self.layout_name]
        main = tk.Frame(
            self.keyboard_frame,
            bg=self.theme["PREVIEW_BG"],
        )
        main.pack(side="left", anchor="nw", padx=(0, 12))

        rows = layout.get("rows", [])
        fn_after = (
            layout.get("fn_after")
            if layout.get("group") == "Laptop"
            else None
        )
        display_rows = []

        for row_index, row in enumerate(rows):
            row = list(row)
            if fn_after is not None and row_index == len(rows) - 1:
                row.insert(
                    min(fn_after + 1, len(row)),
                    ("Fn", "", 1),
                )
            display_rows.append(row)

        for row in display_rows:
            row_frame = tk.Frame(main, bg=self.theme["PREVIEW_BG"])
            row_frame.pack(anchor="w", pady=2)
            for label, scan, width in row:
                self._add_key_button(row_frame, label, scan, width)

        clusters = layout.get("right", [])
        if clusters:
            right = tk.Frame(
                self.keyboard_frame,
                bg=self.theme["PREVIEW_BG"],
            )
            right.pack(side="left", anchor="nw")

            for cluster in clusters:
                cluster_frame = tk.Frame(
                    right,
                    bg=self.theme["PREVIEW_BG"],
                )
                cluster_frame.pack(side="left", anchor="nw", padx=5)

                for row in cluster.get("rows", []):
                    row_frame = tk.Frame(
                        cluster_frame,
                        bg=self.theme["PREVIEW_BG"],
                    )
                    row_frame.pack(anchor="w", pady=2)
                    for label, scan, width in row:
                        self._add_key_button(
                            row_frame,
                            label,
                            scan,
                            width,
                        )

        self.keyboard_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        if self.selected_key and self.selected_key in self.overrides:
            self.select_key(self.selected_key)
        elif self.selected_key:
            self._show_empty_panel()

    def _add_key_button(self, parent, label, scan, width):
        ident = scan.upper() if scan else ""
        override = self.overrides.get(ident, {}) if ident else {}
        hidden = bool(override.get("hidden", False))

        fill = override.get(
            "fill",
            self.settings.get("key_fill") or self.theme["PREVIEW_BG"],
        )
        outline = override.get(
            "outline",
            self.settings.get("outline_color", "#ffffff"),
        )
        text = override.get(
            "text",
            self.settings.get("text_color", "#ffffff"),
        )

        # Keep hidden keys visible in the editor so they can be restored.
        if hidden:
            fill = "#5b3030"
            outline = "#ff7676"
            text = "#ffffff"

        width_units = max(3, min(12, round(float(width) * 3.0)))
        button = tk.Button(
            parent,
            text=label or " ",
            width=width_units,
            height=1,
            bg=fill,
            fg=text,
            activebackground=self.theme["BTN_ACTIVE"],
            activeforeground=text,
            highlightbackground=outline,
            highlightcolor=outline,
            highlightthickness=2,
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padx=1,
            pady=2,
            takefocus=False,
        )

        if ident:
            button.configure(
                command=lambda key_id=ident: self.select_key(key_id)
            )
            self.keys_ui.setdefault(ident, []).append(button)
        else:
            button.configure(state="disabled")

        button.pack(side="left", padx=1, pady=1)

    def select_key(self, ident):
        if not ident:
            return

        self.selected_key = ident
        for child in self.side_panel.winfo_children():
            child.destroy()

        tk.Label(
            self.side_panel,
            text=f"Key: {ident}",
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        override = self.overrides.get(ident, {})
        self.hidden_var = tk.BooleanVar(
            value=bool(override.get("hidden", False))
        )
        tk.Checkbutton(
            self.side_panel,
            text="Hide this key",
            variable=self.hidden_var,
            command=self.update_hidden,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            selectcolor=self.theme["BG"],
            activebackground=self.theme["CARD"],
            activeforeground=self.theme["TEXT"],
        ).pack(anchor="w", pady=(0, 12))

        for title, key in (
            ("Text color", "text"),
            ("Outline color", "outline"),
            ("Fill color", "fill"),
            ("Pressed color", "pressed"),
        ):
            self._color_row(title, key, override)

        tk.Button(
            self.side_panel,
            text="Reset this key",
            command=self.reset_current_key,
            bg="#d93838",
            fg="#ffffff",
            relief="flat",
            pady=5,
        ).pack(fill="x", pady=(18, 0))

    def _color_row(self, title, key, override):
        row = tk.Frame(self.side_panel, bg=self.theme["CARD"])
        row.pack(fill="x", pady=5)

        tk.Label(
            row,
            text=title,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            anchor="w",
        ).pack(anchor="w")

        value = override.get(key)
        tk.Button(
            row,
            text=value if value else "Use global default",
            command=lambda color_key=key: self.pick_color(color_key),
            bg=self.theme["BTN_BG"],
            fg=self.theme["BTN_FG"],
            relief="flat",
            anchor="w",
            padx=8,
            pady=4,
        ).pack(side="left", fill="x", expand=True)

        if value:
            tk.Button(
                row,
                text="Reset",
                command=lambda color_key=key: self.clear_color(color_key),
                bg=self.theme["CARD"],
                fg=self.theme["MUTED"],
                relief="flat",
                padx=5,
            ).pack(side="right", padx=(5, 0))

    def pick_color(self, key):
        if not self.selected_key:
            return

        override = self.overrides.setdefault(self.selected_key, {})
        initial = override.get(key, "#ffffff")

        self.window.attributes("-topmost", False)
        try:
            chosen = colorchooser.askcolor(
                color=initial,
                parent=self.window,
            )[1]
        finally:
            self.window.attributes("-topmost", True)

        if chosen:
            override[key] = chosen
            self.refresh()

    def clear_color(self, key):
        override = self.overrides.get(self.selected_key, {})
        override.pop(key, None)
        if not override:
            self.overrides.pop(self.selected_key, None)
        self.refresh()

    def update_hidden(self):
        if not self.selected_key:
            return

        override = self.overrides.setdefault(self.selected_key, {})
        if self.hidden_var.get():
            override["hidden"] = True
        else:
            override.pop("hidden", None)
            if not override:
                self.overrides.pop(self.selected_key, None)
        self.refresh()

    def reset_current_key(self):
        if not self.selected_key:
            return
        self.overrides.pop(self.selected_key, None)
        self.refresh()

    def reset_all(self):
        confirmed = messagebox.askyesno(
            "Reset all keys",
            "Remove every individual key color and hidden-key setting?",
            parent=self.window,
        )
        if not confirmed:
            return

        self.overrides = {}
        self.selected_key = None
        self.draw_layout()
        self._show_empty_panel()
        self._save_changes()

    def refresh(self):
        selected = self.selected_key
        self.draw_layout()
        if selected:
            self.select_key(selected)
        self._save_changes()

    def _save_changes(self):
        self.settings["key_overrides"] = self.overrides
        self.on_save(dict(self.settings))

    def close(self):
        if self.window.winfo_exists():
            self.window.destroy()


class SettingsDialog:
    COLORS = [
        ("Key labels", "text_color", "The letters and legends shown on each key."),
        ("Key outline", "outline_color", "The thin border around the keys."),
        ("Key fill", "key_fill", "Leave transparent to show your desktop through."),
        ("Pressed key", "pressed_color", "The color used while a key is held down."),
    ]

    def __init__(self, parent, settings, on_preview, background_aspect=2.5):
        self.parent = parent
        self.original = dict(settings)
        self.draft = {**DEFAULTS, **settings}
        self.on_preview = on_preview
        self.background_aspect = background_aspect
        self.theme = THEMES.get(self.draft["theme"], THEMES["light"])
        self.layouts = load_layouts()

        self.window = tk.Toplevel(parent)
        self.window.title("KeyTap Overlay · Settings")
        self.window.transient(parent)
        self.window.attributes("-topmost", True)
        self.window.resizable(True, True)
        self.window.configure(bg=self.theme["BG"])
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(
            "Overlay.Horizontal.TScale",
            background=self.theme["CARD"],
            troughcolor=self.theme["LINE"],
            sliderlength=18,
            sliderthickness=22,
        )
        style.configure(
            "Overlay.TCombobox",
            padding=6,
            fieldbackground="#ffffff",
            background="#ffffff",
            foreground="#172033",
            arrowcolor="#172033",
        )
        style.map(
            "Overlay.TCombobox",
            fieldbackground=[("readonly", "#ffffff"), ("disabled", "#edf3f8")],
            foreground=[("readonly", "#172033"), ("disabled", "#69758a")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", "#172033")],
        )   
        style.configure(
            "Overlay.TButton",
            padding=(12, 7),
            font=("Segoe UI", 9),
            foreground=self.theme["TEXT"],
            background=self.theme["BTN_BG"],
            bordercolor=self.theme["LINE"],
        )
        style.map(
            "Overlay.TButton",
            background=[("active", self.theme["BTN_ACTIVE"])],
        )
        style.configure(
            "Overlay.Primary.TButton",
            padding=(14, 8),
            foreground="#ffffff",
            background=self.theme["ACCENT"],
            font=("Segoe UI", 9, "bold"),
            bordercolor=self.theme["ACCENT"],
        )
        style.map(
            "Overlay.Primary.TButton",
            background=[("active", "#1572bd")],
        )

        outer = tk.Frame(self.window, bg=self.theme["BG"])
        outer.pack(fill="both", expand=True)

        content = tk.Frame(outer, bg=self.theme["BG"])
        canvas = tk.Canvas(
            content,
            bg=self.theme["BG"],
            bd=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            content,
            orient="vertical",
            command=canvas.yview,
        )
        shell = tk.Frame(
            canvas,
            bg=self.theme["BG"],
            padx=18,
            pady=12,
        )
        shell_window = canvas.create_window(
            (0, 0),
            window=shell,
            anchor="nw",
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(shell_window, width=canvas.winfo_width())

        shell.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)
        content.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            if event.widget.winfo_class() in (
                "Listbox",
                "TCombobox",
                "TScrollbar",
                "TScale",
            ):
                return
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        self.window.bind(
            "<Destroy>",
            lambda _event: canvas.unbind_all("<MouseWheel>"),
            add="+",
        )

        tk.Label(
            shell,
            text="Make it yours",
            bg=self.theme["BG"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="Tune the overlay's look and feel.",
            bg=self.theme["BG"],
            fg=self.theme["MUTED"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 12))

        self.preview_card = tk.Frame(
            shell,
            bg=self.theme["PREVIEW_BG"],
            padx=13,
            pady=9,
        )
        self.preview_card.pack(fill="x", pady=(0, 10))
        tk.Label(
            self.preview_card,
            text="LIVE PREVIEW",
            bg=self.theme["PREVIEW_BG"],
            fg=self.theme["MUTED"],
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        self.sample = tk.Frame(
            self.preview_card,
            bg=self.theme["PREVIEW_BG"],
        )
        self.sample.pack(anchor="center", pady=(5, 0))
        self.preview_keys = []

        for title in ("Q", "W", "E", "R", "T", "Y"):
            key = tk.Label(
                self.sample,
                text=title,
                width=4,
                pady=4,
                padx=2,
                font=(
                    self.draft["font_family"],
                    self.draft["font_size"],
                    "bold",
                ),
                relief="flat",
                highlightthickness=1,
            )
            key.pack(side="left", padx=3)
            self.preview_keys.append(key)

        self.preview_keys[2].configure(
            bg=self.draft["pressed_color"],
            fg=readable_on(self.draft["pressed_color"]),
        )

        self.card(shell, "THEME", "Switch between light and dark mode.")
        theme_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        theme_row.pack(fill="x", padx=15, pady=(0, 9))
        self.theme_var = tk.StringVar(value=self.draft["theme"])
        theme_box = ttk.Combobox(
            theme_row,
            textvariable=self.theme_var,
            values=["light", "dark"],
            state="readonly",
            style="Overlay.TCombobox",
        )
        theme_box.pack(side="left", fill="x", expand=True)
        theme_box.bind("<<ComboboxSelected>>", self.update_theme)

        self.card(
            shell,
            "VIEW MODE",
            "Choose whether to show the keyboard, the mouse, or both.",
        )
        view_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        view_row.pack(fill="x", padx=15, pady=(0, 9))
        self.view_var = tk.StringVar(value=self.draft["view_mode"])
        self.view_box = ttk.Combobox(
            view_row,
            textvariable=self.view_var,
            values=["keyboard", "mouse", "both"],
            state="readonly",
            style="Overlay.TCombobox",
        )
        self.view_box.pack(side="left", fill="x", expand=True)
        self.view_box.bind("<<ComboboxSelected>>", self.update_view_mode)

        self.card(
            shell,
            "OVERLAY SIZE",
            "Scale the complete keyboard and mouse evenly, from 50% to 150%.",
        )
        scale_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        scale_row.pack(fill="x", padx=15, pady=(0, 9))
        self.keyboard_scale_var = tk.DoubleVar(
            value=self.draft["keyboard_scale"]
        )
        ttk.Scale(
            scale_row,
            from_=50,
            to=150,
            variable=self.keyboard_scale_var,
            command=self.update_keyboard_scale,
            style="Overlay.Horizontal.TScale",
        ).pack(side="left", fill="x", expand=True)
        self.keyboard_scale_label = tk.Label(
            scale_row,
            text=f"{self.draft['keyboard_scale']}%",
            width=6,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 9, "bold"),
        )
        self.keyboard_scale_label.pack(side="right", padx=(10, 0))

        self.card(
            shell,
            "TRANSPARENCY",
            "Set the overlay opacity from invisible to fully visible.",
        )
        opacity_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        opacity_row.pack(fill="x", padx=15, pady=(0, 9))
        self.opacity_var = tk.DoubleVar(value=self.draft["opacity"])
        ttk.Scale(
            opacity_row,
            from_=0,
            to=100,
            variable=self.opacity_var,
            command=self.update_opacity,
            style="Overlay.Horizontal.TScale",
        ).pack(side="left", fill="x", expand=True)
        self.opacity_label = tk.Label(
            opacity_row,
            text=f"{self.draft['opacity']}%",
            width=5,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 9, "bold"),
        )
        self.opacity_label.pack(side="right", padx=(10, 0))

        self.card(
            shell,
            "GLOBAL KEY COLORS",
            "Choose defaults for all keys.",
        )
        color_grid = tk.Frame(self.last_card, bg=self.theme["CARD"])
        color_grid.pack(fill="x", padx=14, pady=(0, 10))

        for index, (title, setting, description) in enumerate(self.COLORS):
            cell = tk.Frame(
                color_grid,
                bg=self.theme["CARD"],
                padx=3,
                pady=3,
            )
            cell.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=3,
            )
            color_grid.grid_columnconfigure(index % 2, weight=1)
            tk.Label(
                cell,
                text=title,
                bg=self.theme["CARD"],
                fg=self.theme["TEXT"],
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            line = tk.Frame(cell, bg=self.theme["CARD"])
            line.pack(fill="x", pady=(4, 0))
            swatch = tk.Label(line, width=3, height=1, relief="solid", bd=1)
            swatch.pack(side="left")
            tk.Button(
                line,
                text="Choose",
                relief="flat",
                bg=self.theme["BTN_BG"],
                fg=self.theme["BTN_FG"],
                activebackground=self.theme["BTN_ACTIVE"],
                padx=9,
                pady=3,
                command=lambda key=setting: self.choose_color(key),
            ).pack(side="left", padx=(7, 0))
            if setting == "key_fill":
                tk.Button(
                    line,
                    text="Clear",
                    relief="flat",
                    bg=self.theme["CARD"],
                    fg=self.theme["MUTED"],
                    command=self.clear_fill,
                ).pack(side="left", padx=3)
            tk.Label(
                cell,
                text=description,
                bg=self.theme["CARD"],
                fg=self.theme["MUTED"],
                wraplength=200,
                justify="left",
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=(2, 0))
            setattr(self, f"swatch_{setting}", swatch)

        self.card(
            shell,
            "CUSTOMIZE INDIVIDUAL KEYS",
            "Hide keys or change their specific colors.",
        )
        custom_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        custom_row.pack(fill="x", padx=15, pady=(0, 9))
        tk.Button(
            custom_row,
            text="Open Key Customizer…",
            bg=self.theme["ACCENT"],
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=6,
            command=self.open_key_customizer,
        ).pack(fill="x")

        self.card(
            shell,
            "TYPE",
            "Pick any font installed on this Windows computer.",
        )
        type_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        type_row.pack(fill="x", padx=15, pady=(0, 9))
        families = sorted(
            set(tkfont.families(self.window)),
            key=str.casefold,
        ) or ["Segoe UI", "Arial", "Consolas"]
        self.font_var = tk.StringVar(value=self.draft["font_family"])
        self.font_box = ttk.Combobox(
            type_row,
            textvariable=self.font_var,
            values=families,
            state="readonly",
            style="Overlay.TCombobox",
            width=26,
        )
        self.font_box.pack(side="left", fill="x", expand=True)
        self.font_box.bind("<<ComboboxSelected>>", self.update_font)
        self.size_var = tk.DoubleVar(value=self.draft["font_size"])
        ttk.Scale(
            type_row,
            from_=7,
            to=18,
            variable=self.size_var,
            command=self.update_font_size,
            style="Overlay.Horizontal.TScale",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.size_label = tk.Label(
            type_row,
            text=f"{self.draft['font_size']} pt",
            width=6,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 9),
        )
        self.size_label.pack(side="right", padx=(5, 0))

        self.card(
            shell,
            "KEYBOARD BACKGROUND",
            "Choose one still image, GIF, or looping video.",
        )
        kb_frame = tk.Frame(self.last_card, bg=self.theme["CARD"])
        kb_frame.pack(fill="x", padx=15, pady=(0, 9))
        active_kb = (
            self.draft.get("background_video")
            or self.draft.get("background_gif")
            or self.draft.get("background_image")
            or ""
        )
        self.background_label = tk.Label(
            kb_frame,
            text=Path(active_kb).name if active_kb else "None",
            bg=self.theme["CARD"],
            fg=self.theme["MUTED"],
            anchor="w",
        )
        self.background_label.pack(fill="x", pady=(0, 5))
        kb_buttons = tk.Frame(kb_frame, bg=self.theme["CARD"])
        kb_buttons.pack(fill="x")
        for title, command in (
            ("Image", self.choose_background),
            ("GIF", self.choose_gif),
            ("Video", self.choose_video),
            ("Remove", self.remove_background),
        ):
            tk.Button(
                kb_buttons,
                text=title,
                command=command,
                relief="flat",
                bg=self.theme["BTN_BG"],
                fg=self.theme["BTN_FG"],
            ).pack(side="left", padx=3)

        self.card(
            shell,
            "MOUSE BACKGROUND",
            "Customize the mouse background individually.",
        )
        mouse_frame = tk.Frame(self.last_card, bg=self.theme["CARD"])
        mouse_frame.pack(fill="x", padx=15, pady=(0, 9))
        active_mouse = (
            self.draft.get("mouse_background_video")
            or self.draft.get("mouse_background_gif")
            or self.draft.get("mouse_background_image")
            or ""
        )
        self.mouse_bg_label = tk.Label(
            mouse_frame,
            text=Path(active_mouse).name if active_mouse else "None",
            bg=self.theme["CARD"],
            fg=self.theme["MUTED"],
            anchor="w",
        )
        self.mouse_bg_label.pack(fill="x", pady=(0, 5))
        mouse_buttons = tk.Frame(mouse_frame, bg=self.theme["CARD"])
        mouse_buttons.pack(fill="x")
        for title, command in (
            ("Image", self.choose_mouse_background),
            ("GIF", self.choose_mouse_gif),
            ("Video", self.choose_mouse_video),
            ("Remove", self.remove_mouse_background),
        ):
            tk.Button(
                mouse_buttons,
                text=title,
                command=command,
                relief="flat",
                bg=self.theme["BTN_BG"],
                fg=self.theme["BTN_FG"],
            ).pack(side="left", padx=3)

        self.card(
            shell,
            "OVERLAY LOCK",
            "Choose the key that toggles click-through.",
        )
        lock_row = tk.Frame(self.last_card, bg=self.theme["CARD"])
        lock_row.pack(fill="x", padx=15, pady=(0, 9))
        self.lock_var = tk.StringVar(
            value=self.draft.get("lock_key", "Shift")
        )
        self.lock_box = ttk.Combobox(
            lock_row,
            textvariable=self.lock_var,
            values=LOCK_KEY_CHOICES,
            state="readonly",
            style="Overlay.TCombobox",
            width=24,
        )
        self.lock_box.pack(side="left", fill="x", expand=True)

        buttons = tk.Frame(
            outer,
            bg=self.theme["BG"],
            padx=18,
            pady=10,
        )
        buttons.pack(fill="x", side="bottom")
        ttk.Button(
            buttons,
            text="Cancel",
            style="Overlay.TButton",
            command=self.cancel,
        ).pack(side="right")
        ttk.Button(
            buttons,
            text="Save settings",
            style="Overlay.Primary.TButton",
            command=self.save,
        ).pack(side="right", padx=(0, 8))

        self.update_sample()
        self.window.update_idletasks()
        screen_height = self.window.winfo_screenheight()
        screen_width = self.window.winfo_screenwidth()
        height = min(
            self.window.winfo_reqheight(),
            max(400, screen_height - 100),
        )
        width = min(
            max(520, self.window.winfo_reqwidth() + 20),
            screen_width - 40,
        )
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(480, min(480, height))
        self.window.grab_set()

    def open_key_customizer(self):
        KeyCustomizerDialog(
            self.window,
            self.draft,
            self.layouts,
            self.save_customizer,
        )

    def save_customizer(self, updated_settings):
        self.draft["key_overrides"] = updated_settings["key_overrides"]
        save_settings(self.draft)
        self.on_preview(dict(self.draft))

    def card(self, parent, heading, detail):
        card = tk.Frame(
            parent,
            bg=self.theme["CARD"],
            highlightbackground=self.theme["LINE"],
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 7))
        tk.Label(
            card,
            text=heading,
            bg=self.theme["CARD"],
            fg=self.theme["TEXT"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=15, pady=(8, 2))
        tk.Label(
            card,
            text=detail,
            bg=self.theme["CARD"],
            fg=self.theme["MUTED"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=15, pady=(0, 7))
        self.last_card = card

    def update_sample(self):
        fill = self.draft["key_fill"] or self.theme["PREVIEW_BG"]
        for index, key in enumerate(self.preview_keys):
            pressed = index == 2
            key.configure(
                bg=self.draft["pressed_color"] if pressed else fill,
                fg=readable_on(
                    self.draft["pressed_color"]
                    if pressed
                    else self.draft["text_color"]
                ),
                highlightbackground=self.draft["outline_color"],
                highlightcolor=self.draft["outline_color"],
                font=(
                    self.draft["font_family"],
                    self.draft["font_size"],
                    "bold",
                ),
            )

        for _, setting, _ in self.COLORS:
            swatch = getattr(self, f"swatch_{setting}")
            swatch.configure(
                bg=self.draft.get(setting) or self.theme["PREVIEW_BG"],
                highlightbackground=self.theme["LINE"],
            )

    def preview(self):
        self.update_sample()
        self.on_preview(dict(self.draft))

    def update_theme(self, _event=None):
        self.draft["theme"] = self.theme_var.get()
        save_settings(self.draft)
        self.window.destroy()
        SettingsDialog(
            self.parent,
            self.draft,
            self.on_preview,
            self.background_aspect,
        )

    def update_view_mode(self, _event=None):
        self.draft["view_mode"] = self.view_var.get()
        self.preview()

    def update_keyboard_scale(self, value):
        self.draft["keyboard_scale"] = min(
            150,
            max(50, round(float(value))),
        )
        self.keyboard_scale_label.configure(
            text=f"{self.draft['keyboard_scale']}%"
        )
        self.preview()

    def update_opacity(self, value):
        self.draft["opacity"] = round(float(value))
        self.opacity_label.configure(text=f"{self.draft['opacity']}%")
        self.preview()

    def update_font(self, _event=None):
        self.draft["font_family"] = self.font_var.get()
        self.preview()

    def update_font_size(self, value):
        self.draft["font_size"] = round(float(value))
        self.size_label.configure(
            text=f"{self.draft['font_size']} pt"
        )
        self.preview()

    def choose_color(self, setting):
        self.window.attributes("-topmost", False)
        try:
            chosen = colorchooser.askcolor(
                color=self.draft.get(setting) or "#ffffff",
                parent=self.window,
            )[1]
        finally:
            self.window.attributes("-topmost", True)
        if chosen:
            self.draft[setting] = chosen
            self.preview()

    def choose_background(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose keyboard background image",
            filetypes=IMAGE_FILETYPES,
        )
        if not selected:
            return
        try:
            BackgroundCropDialog(
                self.window,
                selected,
                self.background_aspect,
                self.set_background_image,
                is_mouse=False,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that image:\n{exc}",
                parent=self.window,
            )

    def choose_gif(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose looping keyboard GIF background",
            filetypes=GIF_FILETYPES,
        )
        if not selected:
            return
        try:
            GifBackgroundCropDialog(
                self.window,
                selected,
                self.background_aspect,
                self.set_background_gif,
                is_mouse=False,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that GIF:\n{exc}",
                parent=self.window,
            )

    def choose_video(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose looping keyboard video background",
            filetypes=VIDEO_FILETYPES,
        )
        if not selected:
            return
        try:
            VideoBackgroundCropDialog(
                self.window,
                selected,
                self.background_aspect,
                self.set_background_video,
                is_mouse=False,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that video:\n{exc}",
                parent=self.window,
            )

    def set_background_image(self, path):
        self.draft["background_image"] = path
        self.draft["background_gif"] = ""
        self.draft["background_gif_crop"] = None
        self.draft["background_video"] = ""
        self.draft["background_video_crop"] = None
        self.background_label.configure(
            text=Path(path).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def set_background_gif(self, source_path, crop):
        try:
            saved = copy_background_image(source_path, "kb-gif")
        except OSError as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not copy that GIF:\n{exc}",
                parent=self.window,
            )
            return

        self.draft["background_gif"] = saved
        self.draft["background_gif_crop"] = list(crop)
        self.draft["background_image"] = ""
        self.draft["background_video"] = ""
        self.draft["background_video_crop"] = None
        self.background_label.configure(
            text=Path(saved).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def set_background_video(self, source_path, crop):
        try:
            saved = copy_background_image(source_path, "kb-video")
        except OSError as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not copy that video:\n{exc}",
                parent=self.window,
            )
            return

        self.draft["background_video"] = saved
        self.draft["background_video_crop"] = list(crop)
        self.draft["background_image"] = ""
        self.draft["background_gif"] = ""
        self.draft["background_gif_crop"] = None
        self.background_label.configure(
            text=Path(saved).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def remove_background(self):
        self.draft["background_image"] = ""
        self.draft["background_gif"] = ""
        self.draft["background_gif_crop"] = None
        self.draft["background_video"] = ""
        self.draft["background_video_crop"] = None
        self.background_label.configure(
            text="None",
            fg=self.theme["MUTED"],
        )
        self.preview()

    def choose_mouse_background(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose mouse background image",
            filetypes=IMAGE_FILETYPES,
        )
        if not selected:
            return
        try:
            BackgroundCropDialog(
                self.window,
                selected,
                0.6,
                self.set_mouse_background_image,
                is_mouse=True,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that image:\n{exc}",
                parent=self.window,
            )

    def choose_mouse_gif(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose mouse GIF background",
            filetypes=GIF_FILETYPES,
        )
        if not selected:
            return
        try:
            GifBackgroundCropDialog(
                self.window,
                selected,
                0.6,
                self.set_mouse_background_gif,
                is_mouse=True,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that GIF:\n{exc}",
                parent=self.window,
            )

    def choose_mouse_video(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose mouse video background",
            filetypes=VIDEO_FILETYPES,
        )
        if not selected:
            return
        try:
            VideoBackgroundCropDialog(
                self.window,
                selected,
                0.6,
                self.set_mouse_background_video,
                is_mouse=True,
            )
        except Exception as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that video:\n{exc}",
                parent=self.window,
            )

    def set_mouse_background_image(self, path):
        self.draft["mouse_background_image"] = path
        self.draft["mouse_background_gif"] = ""
        self.draft["mouse_background_gif_crop"] = None
        self.draft["mouse_background_video"] = ""
        self.draft["mouse_background_video_crop"] = None
        self.mouse_bg_label.configure(
            text=Path(path).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def set_mouse_background_gif(self, source_path, crop):
        try:
            saved = copy_background_image(source_path, "mouse-gif")
        except OSError as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not copy that GIF:\n{exc}",
                parent=self.window,
            )
            return

        self.draft["mouse_background_gif"] = saved
        self.draft["mouse_background_gif_crop"] = list(crop)
        self.draft["mouse_background_image"] = ""
        self.draft["mouse_background_video"] = ""
        self.draft["mouse_background_video_crop"] = None
        self.mouse_bg_label.configure(
            text=Path(saved).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def set_mouse_background_video(self, source_path, crop):
        try:
            saved = copy_background_image(source_path, "mouse-video")
        except OSError as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not copy that video:\n{exc}",
                parent=self.window,
            )
            return

        self.draft["mouse_background_video"] = saved
        self.draft["mouse_background_video_crop"] = list(crop)
        self.draft["mouse_background_image"] = ""
        self.draft["mouse_background_gif"] = ""
        self.draft["mouse_background_gif_crop"] = None
        self.mouse_bg_label.configure(
            text=Path(saved).name,
            fg=self.theme["TEXT"],
        )
        self.preview()

    def remove_mouse_background(self):
        self.draft["mouse_background_image"] = ""
        self.draft["mouse_background_gif"] = ""
        self.draft["mouse_background_gif_crop"] = None
        self.draft["mouse_background_video"] = ""
        self.draft["mouse_background_video_crop"] = None
        self.mouse_bg_label.configure(
            text="None",
            fg=self.theme["MUTED"],
        )
        self.preview()

    def clear_fill(self):
        self.draft["key_fill"] = None
        self.preview()

    def save(self):
        self.draft["font_family"] = self.font_var.get()
        self.draft["font_size"] = round(self.size_var.get())
        self.draft["opacity"] = round(self.opacity_var.get())
        self.draft["keyboard_scale"] = round(
            self.keyboard_scale_var.get()
        )
        self.draft["lock_key"] = self.lock_var.get()
        self.draft["view_mode"] = self.view_var.get()
        self.draft["theme"] = self.theme_var.get()
        save_settings(self.draft)
        self.on_preview(dict(self.draft))
        self.window.destroy()

    def cancel(self):
        self.on_preview(self.original)
        self.window.destroy()