"""Load keyboard layout definitions bundled with the app."""
import json
import os
import shutil
from pathlib import Path
import sys

def data_file(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "data" / name

def user_layout_file():
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    base = appdata / "KeyTap-Overlay"
    base.mkdir(parents=True, exist_ok=True)
    target = base / "keyboard_layouts.json"
    if not target.exists():
        old_layouts = next((appdata / old / "keyboard_layouts.json"
                            for old in ("KeyView", "KeyboardOverlay")
                            if (appdata / old / "keyboard_layouts.json").exists()), None)
        shutil.copy2(old_layouts or data_file("keyboard_layouts.json"), target)
    return target

def load_layouts():
    layouts = json.loads(user_layout_file().read_text(encoding="utf-8"))
    if not layouts:
        raise ValueError("No keyboard layouts were found.")
    return layouts
