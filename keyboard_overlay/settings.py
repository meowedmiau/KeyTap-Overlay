"""Appearance settings, live preview, and persistent user preferences."""
import json
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import colorchooser, filedialog, font as tkfont, messagebox, ttk
from uuid import uuid4
from .background_editor import BackgroundCropDialog

from PIL import Image

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
}

BG = "#f3f6fa"
CARD = "#ffffff"
TEXT = "#172033"
MUTED = "#69758a"
ACCENT = "#2589d8"
LINE = "#e5eaf1"

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
    ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
    ("All files", "*.*"),
]


def settings_path():
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
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
        return {**DEFAULTS, **loaded}
    except (OSError, ValueError, TypeError):
        return dict(DEFAULTS)


def save_settings(settings):
    settings_path().write_text(json.dumps(settings, indent=2), encoding="utf-8")


def readable_on(color):
    if not color:
        return TEXT

    try:
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        return TEXT if sum(rgb) > 390 else "#ffffff"
    except (ValueError, TypeError):
        return TEXT


def copy_background_image(source_path):
    source = Path(source_path)
    folder = settings_path().parent / "backgrounds"
    folder.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    target = folder / f"keyboard-background-{uuid4().hex}{suffix}"
    shutil.copy2(source, target)
    return str(target)


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
        self.draft = dict(settings)
        self.on_preview = on_preview
        self.background_aspect = background_aspect

        self.window = tk.Toplevel(parent)
        self.window.title("KeyTap Overlay · Settings")
        self.window.transient(parent)
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(
            "Overlay.Horizontal.TScale",
            background=CARD,
            troughcolor="#dce5ef",
            sliderlength=18,
            sliderthickness=22,
        )
        style.configure(
            "Overlay.TCombobox",
            padding=6,
            fieldbackground="#ffffff",
        )
        style.configure(
            "Overlay.TButton",
            padding=(12, 7),
            font=("Segoe UI", 9),
        )
        style.configure(
            "Overlay.Primary.TButton",
            padding=(14, 8),
            foreground="#ffffff",
            background=ACCENT,
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Overlay.Primary.TButton",
            background=[("active", "#1572bd")],
        )

        shell = tk.Frame(self.window, bg=BG, padx=22, pady=18)
        shell.pack(fill="both", expand=True)

        tk.Label(
            shell,
            text="Make it yours",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="Tune the keyboard overlay's look and feel.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 16))

        self.preview_card = tk.Frame(
            shell,
            bg="#eaf2f9",
            padx=13,
            pady=11,
        )
        self.preview_card.pack(fill="x", pady=(0, 13))

        tk.Label(
            self.preview_card,
            text="LIVE PREVIEW",
            bg="#eaf2f9",
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

        self.sample = tk.Frame(self.preview_card, bg="#eaf2f9")
        self.sample.pack(anchor="center", pady=(7, 0))

        self.preview_keys = []
        for title in ("Q", "W", "E", "R", "T", "Y"):
            key = tk.Label(
                self.sample,
                text=title,
                width=4,
                pady=5,
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

        self.card(
            shell,
            "TRANSPARENCY",
            "Set the overlay opacity from invisible to fully visible.",
        )
        opacity_row = tk.Frame(self.last_card, bg=CARD)
        opacity_row.pack(fill="x", padx=15, pady=(0, 12))

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
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        )
        self.opacity_label.pack(side="right", padx=(10, 0))

        self.card(
            shell,
            "KEY COLORS",
            "Choose colors for labels, outlines, and presses.",
        )
        color_grid = tk.Frame(self.last_card, bg=CARD)
        color_grid.pack(fill="x", padx=14, pady=(0, 13))

        for index, (title, setting, description) in enumerate(self.COLORS):
            cell = tk.Frame(color_grid, bg=CARD, padx=3, pady=4)
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
                bg=CARD,
                fg=TEXT,
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")

            line = tk.Frame(cell, bg=CARD)
            line.pack(fill="x", pady=(5, 0))

            swatch = tk.Label(line, width=3, height=1, relief="solid", bd=1)
            swatch.pack(side="left")

            tk.Button(
                line,
                text="Choose",
                relief="flat",
                bg="#edf3f8",
                fg=TEXT,
                activebackground="#dfeaf3",
                padx=9,
                pady=4,
                command=lambda key=setting: self.choose_color(key),
            ).pack(side="left", padx=(7, 0))

            if setting == "key_fill":
                tk.Button(
                    line,
                    text="Clear",
                    relief="flat",
                    bg=CARD,
                    fg=MUTED,
                    command=self.clear_fill,
                ).pack(side="left", padx=3)

            tk.Label(
                cell,
                text=description,
                bg=CARD,
                fg=MUTED,
                wraplength=200,
                justify="left",
                font=("Segoe UI", 8),
            ).pack(anchor="w", pady=(3, 0))

            setattr(self, f"swatch_{setting}", swatch)

        self.card(
            shell,
            "TYPE",
            "Pick any font installed on this Windows computer.",
        )
        type_row = tk.Frame(self.last_card, bg=CARD)
        type_row.pack(fill="x", padx=15, pady=(0, 12))

        families = sorted(
            set(tkfont.families(self.window)),
            key=str.casefold,
        )
        if not families:
            families = ["Segoe UI", "Arial", "Calibri", "Consolas", "Tahoma"]

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
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9),
        )
        self.size_label.pack(side="right", padx=(5, 0))

        self.card(
            shell,
            "BACKGROUND IMAGE",
            "Choose an image to fit behind the keyboard.",
        )
        background_row = tk.Frame(self.last_card, bg=CARD)
        background_row.pack(fill="x", padx=15, pady=(0, 12))

        background_path = self.draft.get("background_image", "")
        background_name = Path(background_path).name if background_path else "None"
        self.background_label = tk.Label(
            background_row,
            text=background_name,
            bg=CARD,
            fg=MUTED,
            anchor="w",
        )
        self.background_label.pack(side="left", fill="x", expand=True)

        tk.Button(
            background_row,
            text="Choose image",
            relief="flat",
            bg="#edf3f8",
            fg=TEXT,
            activebackground="#dfeaf3",
            padx=9,
            pady=4,
            command=self.choose_background,
        ).pack(side="left", padx=(7, 0))

        tk.Button(
            background_row,
            text="Remove",
            relief="flat",
            bg=CARD,
            fg=MUTED,
            command=self.remove_background,
        ).pack(side="left", padx=(5, 0))

        self.card(
            shell,
            "OVERLAY LOCK",
            "Choose the key that toggles click-through.",
        )
        lock_row = tk.Frame(self.last_card, bg=CARD)
        lock_row.pack(fill="x", padx=15, pady=(0, 12))

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

        buttons = tk.Frame(shell, bg=BG)
        buttons.pack(fill="x", pady=(13, 0))

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
        self.window.geometry(
            f"{self.window.winfo_reqwidth()}x{self.window.winfo_reqheight()}"
        )
        self.window.grab_set()

    def card(self, parent, heading, detail):
        card = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=LINE,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 10))

        tk.Label(
            card,
            text=heading,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=15, pady=(11, 2))

        tk.Label(
            card,
            text=detail,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=15, pady=(0, 10))

        self.last_card = card

    def update_sample(self):
        fill = self.draft["key_fill"] or "#eaf2f9"

        for index, key in enumerate(self.preview_keys):
            is_pressed = index == 2
            key.configure(
                bg=self.draft["pressed_color"] if is_pressed else fill,
                fg=readable_on(
                    self.draft["pressed_color"]
                    if is_pressed
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
            color = self.draft.get(setting) or "#eaf2f9"
            swatch.configure(bg=color, highlightbackground=LINE)

    def preview(self):
        self.update_sample()
        self.on_preview(dict(self.draft))

    def update_opacity(self, value):
        self.draft["opacity"] = round(float(value))
        self.opacity_label.configure(text=f"{self.draft['opacity']}%")
        self.preview()

    def update_font(self, _event=None):
        self.draft["font_family"] = self.font_var.get()
        self.preview()

    def update_font_size(self, value):
        self.draft["font_size"] = round(float(value))
        self.size_label.configure(text=f"{self.draft['font_size']} pt")
        self.preview()

    def choose_color(self, setting):
        chosen = colorchooser.askcolor(
            color=self.draft.get(setting) or "#ffffff",
            parent=self.window,
        )[1]
        if chosen:
            self.draft[setting] = chosen
            self.preview()

    def choose_background(self):
        selected = filedialog.askopenfilename(
            parent=self.window,
            title="Choose keyboard background",
            filetypes=IMAGE_FILETYPES,
        )
        if not selected:
            return

        try:
            BackgroundCropDialog(
                self.window,
                selected,
                self.background_aspect,
                self.set_background_crop,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "KeyTap Overlay",
                f"Could not open that image:\n{exc}",
                parent=self.window,
            )

def set_background_crop(self, path):
    self.draft["background_image"] = path
    self.background_label.configure(
        text=Path(path).name,
        fg=TEXT,
    )
    self.preview()

    def remove_background(self):
        self.draft["background_image"] = ""
        self.background_label.configure(text="None", fg=MUTED)
        self.preview()

    def clear_fill(self):
        self.draft["key_fill"] = None
        self.preview()

    def save(self):
        self.draft["font_family"] = self.font_var.get()
        self.draft["font_size"] = round(self.size_var.get())
        self.draft["opacity"] = round(self.opacity_var.get())
        self.draft["lock_key"] = self.lock_var.get()
        save_settings(self.draft)
        self.on_preview(dict(self.draft))
        self.window.destroy()

    def cancel(self):
        self.on_preview(self.original)
        self.window.destroy()