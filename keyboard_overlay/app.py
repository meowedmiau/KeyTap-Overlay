"""Transparent keyboard overlay and its user interface."""
import ctypes
import ctypes.wintypes
import os
import queue
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox
from .keyboard_hook import KeyboardHook
from .layouts import load_layouts, user_layout_file
from .settings import SettingsDialog, load_settings
from .updates import check_latest_release, current_version, download_and_launch_update

TRANSPARENT = "#010203"
VK_F1 = 0x70

NAV_ROWS = [
    [["Ins", "E052", 1], ["Home", "E047", 1], ["PgUp", "E049", 1]],
    [["Del", "E053", 1], ["End", "E04F", 1], ["PgDn", "E051", 1]],
    [["", "", 1], ["↑", "E048", 1], ["", "", 1]],
    [["←", "E04B", 1], ["↓", "E050", 1], ["→", "E04D", 1]],
]
NUMPAD_ROWS = [
    [["Num", "45", 1], ["/", "E035", 1], ["*", "37", 1], ["-", "4A", 1]],
    [["7", "47", 1], ["8", "48", 1], ["9", "49", 1], ["+", "4E", 1]],
    [["4", "4B", 1], ["5", "4C", 1], ["6", "4D", 1], ["", "", 1]],
    [["1", "4F", 1], ["2", "50", 1], ["3", "51", 1], ["Enter", "E01C", 1]],
    [["0", "52", 2], [".", "53", 1], ["", "", 1], ["", "", 1]],
]

class KeyboardOverlayApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KeyTap Overlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.settings = load_settings()
        self.layouts = load_layouts()
        self.layout_name = next((name for name, item in self.layouts.items()
                                 if item.get("group") == "PC"), next(iter(self.layouts)))
        self.compact = False
        self.auto_labels = True
        self.keys = {}
        self.function_keys = {}
        self.down = set()
        self.held_ids = set()
        self.active_chords = set()
        self.events = queue.SimpleQueue()
        self.update_results = queue.SimpleQueue()
        self.update_checking = False
        self.user32 = ctypes.windll.user32
        self.user32.GetKeyNameTextW.argtypes = (ctypes.wintypes.LONG, ctypes.wintypes.LPWSTR, ctypes.c_int)
        self.user32.GetKeyNameTextW.restype = ctypes.c_int
        self.build()
        self.place_bottom_left()
        self.root.bind("<ButtonPress-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<Button-3>", self.menu)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.hook = KeyboardHook(self.events)
        except OSError as exc:
            messagebox.showerror("KeyTap Overlay", str(exc))
            self.root.destroy()
            return
        self.root.after(15, self.process_events)
        self.root.after(2500, lambda: self.check_for_updates(manual=False))
        self.root.mainloop()

    def build(self):
        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self.keys = {}
        self.function_keys = {}
        bar = tk.Frame(self.root, bg=TRANSPARENT)
        bar.pack(fill="x", padx=6, pady=(2, 1))
        tk.Label(bar, text=self.layout_name, fg=self.settings["text_color"], bg=TRANSPARENT,
                 font=(self.settings["font_family"], self.settings["font_size"], "bold")).pack(side="left")
        tk.Label(bar, text="drag · ⚙ for options", fg=self.settings["text_color"],
                 bg=TRANSPARENT, font=(self.settings["font_family"], max(7, self.settings["font_size"] - 2))).pack(side="right", padx=(0, 6))
        options_button = tk.Label(
            bar,
            text="⚙",
            bg=TRANSPARENT,
            fg=self.settings["text_color"],
            font=("Segoe UI Symbol", 11, "bold"),
            cursor="hand2",
            padx=4,
        )
        options_button.pack(side="right")
        options_button.bind("<Button-1>", lambda _event: self.open_options())
        body = tk.Frame(self.root, bg=TRANSPARENT)
        body.pack(anchor="w")
        main = tk.Frame(body, bg=TRANSPARENT)
        main.pack(side="left", anchor="n")
        layout = self.layouts[self.layout_name]
        rows = layout["rows"]
        fn_after = layout.get("fn_after") if layout.get("group") == "Laptop" else None
        for row_index, row in enumerate(rows):
            display_row = list(row)
            if fn_after is not None and row_index == len(rows) - 1:
                display_row.insert(min(fn_after + 1, len(display_row)), ("Fn", "", 1))
            line = tk.Frame(main, bg=TRANSPARENT)
            line.pack(padx=5, pady=2, anchor="w")
            for label, scan, width in display_row:
                self.add_key(line, label, scan, width)
        if not self.compact:
            side = tk.Frame(body, bg=TRANSPARENT)
            side.pack(side="left", anchor="n", padx=(8, 5), pady=2)
            clusters = layout.get("right", [{"rows": NAV_ROWS}, {"rows": NUMPAD_ROWS}])
            for cluster in clusters:
                column = tk.Frame(side, bg=TRANSPARENT)
                column.pack(side="left", anchor="n", padx=(0, 8))
                for row in cluster["rows"]:
                    line = tk.Frame(column, bg=TRANSPARENT)
                    line.pack(pady=2)
                    for label, scan, width in row:
                        if scan:
                            self.add_key(line, label, scan, width)
                        else:
                            tk.Label(line, text="", width=4, bg=TRANSPARENT).pack(side="left", padx=2)
        self.root.attributes("-alpha", self.settings["opacity"] / 100)
        self.root.update_idletasks()

    def add_key(self, parent, label, scan, width):
        if not scan:
            self.make_key(parent, label, width)
            return
        ident = scan.upper()
        shown = self.key_label(ident, label)
        widget = self.make_key(parent, shown, width)
        self.keys.setdefault(ident, []).append(widget)
        match = re.fullmatch(r"F(\d{1,2})", label)
        if match:
            self.function_keys[VK_F1 + int(match.group(1)) - 1] = ident

    def make_key(self, parent, label, width):
        fill = self.settings["key_fill"] or TRANSPARENT
        widget = tk.Label(parent, text=label, width=max(3, int(width * 4)), height=1,
                          bg=fill, fg=self.settings["text_color"],
                          font=(self.settings["font_family"], self.settings["font_size"], "bold"),
                          relief="flat", bd=0, highlightbackground=self.settings["outline_color"],
                          highlightcolor=self.settings["outline_color"], highlightthickness=1,
                          padx=2, pady=5)
        widget.pack(side="left", padx=2)
        return widget

    def key_label(self, ident, fallback):
        if self.auto_labels and len(fallback) == 1 and fallback.isprintable():
            scan = int(ident[-2:], 16)
            lparam = (scan << 16) | (int(ident.startswith("E")) << 24)
            buffer = ctypes.create_unicode_buffer(32)
            if self.user32.GetKeyNameTextW(lparam, buffer, len(buffer)) > 0 and len(buffer.value) == 1:
                return buffer.value.upper()
        return fallback

    def place_bottom_left(self):
        self.root.update_idletasks()
        self.root.geometry(f"+12+{self.root.winfo_screenheight()-self.root.winfo_reqheight()-48}")

    def start_drag(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def drag(self, event):
        self.root.geometry(f"+{event.x_root-self.drag_x}+{event.y_root-self.drag_y}")

    def menu(self, event):
        self.show_options_menu(event.x_root, event.y_root)

    def open_options(self):
        self.show_options_menu(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def show_options_menu(self, x, y):
        menu = tk.Menu(self.root, tearoff=False)
        for group in ("PC", "Laptop"):
            submenu = tk.Menu(menu, tearoff=False)
            for name, layout in self.layouts.items():
                if layout.get("group", "PC") == group:
                    submenu.add_command(label=("✓ " if name == self.layout_name else "") + name,
                                        command=lambda n=name: self.select_layout(n))
            if submenu.index("end") is not None:
                menu.add_cascade(label=group, menu=submenu)
        menu.add_command(label="Turn compact layout off" if self.compact else "Turn compact layout on",
                         command=self.toggle_compact)
        menu.add_command(label="Use preset labels" if self.auto_labels else "Use Windows detected labels",
                         command=self.toggle_auto_labels)
        menu.add_command(label="Settings…", command=self.open_settings)
        menu.add_command(label="Open layout definitions…", command=lambda: os.startfile(str(user_layout_file())))
        menu.add_command(label="Check for updates…", command=lambda: self.check_for_updates(manual=True))
        menu.add_separator()
        menu.add_command(label="Quit", command=self.close)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def select_layout(self, name):
        self.down.clear()
        self.held_ids.clear()
        self.active_chords.clear()
        self.layout_name = name
        self.auto_labels = False
        self.build()

    def toggle_compact(self):
        self.compact = not self.compact
        self.build()

    def toggle_auto_labels(self):
        self.auto_labels = not self.auto_labels
        self.build()

    def open_settings(self):
        SettingsDialog(self.root, self.settings, self.preview_settings)

    def preview_settings(self, values):
        self.settings = dict(values)
        self.build()

    def flash(self, ident, pressed):
        for widget in self.keys.get(ident, []):
            widget.configure(bg=self.settings["pressed_color"] if pressed else (self.settings["key_fill"] or TRANSPARENT),
                             fg=self.settings["text_color"])

    def process_events(self):
        while True:
            try:
                ident, pressed, vk = self.events.get_nowait()
            except queue.Empty:
                break
            ident = self.function_keys.get(vk, ident)
            chords = self.layouts[self.layout_name].get("chords", {})
            if pressed and ident not in self.down:
                self.down.add(ident)
                self.flash(ident, True)
                self.held_ids.add(ident)
                combo = "+".join(sorted(self.held_ids))
                target = chords.get(combo)
                if target and target not in self.active_chords:
                    self.active_chords.add(target)
                    self.flash(target, True)
            elif not pressed and ident in self.down:
                self.down.discard(ident)
                self.flash(ident, False)
                self.held_ids.discard(ident)
                for combo, target in chords.items():
                    if target in self.active_chords and not set(combo.split("+")).issubset(self.held_ids):
                        self.active_chords.discard(target)
                        self.flash(target, False)
        self.process_update_results()
        self.root.after(15, self.process_events)

    def check_for_updates(self, manual=True):
        if self.update_checking:
            return
        self.update_checking = True

        def check():
            try:
                result = check_latest_release()
                self.update_results.put(("checked", manual, result))
            except Exception as exc:
                self.update_results.put(("check_error", manual, str(exc)))

        threading.Thread(target=check, daemon=True).start()

    def process_update_results(self):
        while True:
            try:
                kind, manual, result = self.update_results.get_nowait()
            except queue.Empty:
                break
            if kind == "checked":
                self.update_checking = False
                if result is None:
                    if manual:
                        messagebox.showinfo("KeyTap Overlay", "You’re using the latest version.", parent=self.root)
                    continue
                answer = messagebox.askyesno(
                    "KeyTap Overlay update available",
                    f"Version {result['version']} is available. You’re using version {current_version()}.\n\n"
                    "Download and install it now? KeyTap will close and reopen after the update.",
                    parent=self.root,
                )
                if answer:
                    self.install_update(result)
            elif kind == "check_error":
                self.update_checking = False
                if manual:
                    messagebox.showwarning("KeyTap Overlay", f"Couldn’t check for updates.\n\n{result}", parent=self.root)
            elif kind == "install_started":
                self.update_checking = False
                outcome, release_url = result
                if outcome == "source":
                    webbrowser.open(release_url)
                    messagebox.showinfo(
                        "KeyTap Overlay update available",
                        "This copy was started from source code. The Releases page is opening so you can download the updated app.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        "Updating KeyTap Overlay",
                        "The update is ready. KeyTap Overlay will close, replace its app file, and reopen.",
                        parent=self.root,
                    )
                    self.close()
            elif kind == "install_error":
                self.update_checking = False
                messagebox.showerror("KeyTap Overlay update failed", str(result), parent=self.root)

    def install_update(self, release):
        self.update_checking = True

        def install():
            try:
                outcome = download_and_launch_update(release)
                self.update_results.put(("install_started", False, (outcome, release["release_url"])))
            except Exception as exc:
                self.update_results.put(("install_error", False, str(exc)))

        threading.Thread(target=install, daemon=True).start()

    def close(self):
        if hasattr(self, "hook"):
            self.hook.close()
        self.root.destroy()
