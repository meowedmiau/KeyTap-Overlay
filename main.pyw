"""Start the KeyTap Overlay desktop application."""
import sys
from tkinter import messagebox

if sys.platform != "win32":
    raise SystemExit("KeyTap Overlay currently supports Windows only.")

from keyboard_overlay.app import KeyboardOverlayApp

try:
    KeyboardOverlayApp()
except Exception as exc:
    messagebox.showerror("KeyTap Overlay", f"The app could not start:\n{exc}")
