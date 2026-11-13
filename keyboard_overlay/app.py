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

from PIL import Image, ImageOps, ImageTk

from .keyboard_hook import KeyboardHook
from .layouts import load_layouts, user_layout_file
from .settings import SettingsDialog, load_settings, save_settings
from .updates import check_latest_release, current_version, download_and_launch_update

TRANSPARENT = "#010203"
PANEL_COLOR = "#111722"
VK_F1 = 0x70

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

LOCK_KEY_VKS = {
    "Shift": {0x10, 0xA0, 0xA1},
    "Ctrl": {0x11, 0xA2, 0xA3},
    "Alt": {0x12, 0xA4, 0xA5},
    "Caps Lock": {0x14},
    "Scroll Lock": {0x91},
    "Pause": {0x13},
    **{f"F{i}": {0x70 + i - 1} for i in range(1, 13)},
}

BASE_HEADER_HEIGHT = 28
BASE_KEY_HEIGHT = 27
BASE_ROW_GAP = 4
BASE_KEY_GAP = 4
BASE_SIDE_GAP = 8

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

        saved_layout = self.settings.get("layout_name", "")
        self.layout_name = (
            saved_layout
            if saved_layout in self.layouts
            else next(
                (
                    name for name, item in self.layouts.items()
                    if item.get("group") == "PC"
                ),
                next(iter(self.layouts)),
            )
        )
        self.compact = bool(self.settings.get("compact", False))

        self.locked = False
        self.lock_key_scans = set()
        self.auto_labels = True
        self.keys = {}
        self.function_keys = {}
        self.down = set()
        self.held_ids = set()
        self.active_chords = set()
        self.events = queue.SimpleQueue()
        self.update_results = queue.SimpleQueue()
        self.update_checking = False
        self.background_photo = None

        self.user32 = ctypes.windll.user32
        self.user32.GetKeyNameTextW.argtypes = (
            ctypes.wintypes.LONG,
            ctypes.wintypes.LPWSTR,
            ctypes.c_int,
        )
        self.user32.GetKeyNameTextW.restype = ctypes.c_int
        self.user32.GetWindowLongW.argtypes = (
            ctypes.wintypes.HWND,
            ctypes.c_int,
        )
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowLongW.argtypes = (
            ctypes.wintypes.HWND,
            ctypes.c_int,
            ctypes.c_long,
        )
        self.user32.SetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowPos.argtypes = (
            ctypes.wintypes.HWND,
            ctypes.wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.wintypes.UINT,
        )

        self.build()
        self.place_bottom_left()
        self.hwnd = ctypes.wintypes.HWND(self.root.winfo_id())

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

    @property
    def scale(self):
        try:
            return min(
                1.5,
                max(0.5, float(self.settings.get("keyboard_scale", 100)) / 100),
            )
        except (TypeError, ValueError):
            return 1.0

    def scaled(self, value, minimum=1):
        return max(minimum, round(value * self.scale))

    def key_width(self, width):
        base = max(3, int(width * 4)) * 8 + 4
        return self.scaled(base)

    def cell_width(self, width):
        return self.key_width(width) + self.scaled(BASE_KEY_GAP)

    def row_width(self, row):
        return sum(self.cell_width(item[2]) for item in row)

    def build(self):
        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()

        old_x = self.root.winfo_x()
        old_y = self.root.winfo_y()

        self.keys = {}
        self.function_keys = {}
        self.background_photo = None

        self.header_height = self.scaled(BASE_HEADER_HEIGHT, minimum=12)
        self.key_height = self.scaled(BASE_KEY_HEIGHT, minimum=12)
        self.row_gap = self.scaled(BASE_ROW_GAP)
        self.key_gap = self.scaled(BASE_KEY_GAP)
        self.side_gap = self.scaled(BASE_SIDE_GAP)

        layout = self.layouts[self.layout_name]
        rows = layout["rows"]
        fn_after = layout.get("fn_after") if layout.get("group") == "Laptop" else None

        display_rows = []
        for row_index, row in enumerate(rows):
            display_row = list(row)
            if fn_after is not None and row_index == len(rows) - 1:
                display_row.insert(
                    min(fn_after + 1, len(display_row)),
                    ("Fn", "", 1),
                )
            display_rows.append(display_row)

        main_width = max((self.row_width(row) for row in display_rows), default=0)
        clusters = []
        if not self.compact:
            clusters = layout.get("right", [{"rows": NAV_ROWS}, {"rows": NUMPAD_ROWS}])

        x_right = self.scaled(5) + main_width + self.side_gap
        right_width = 0
        right_rows = 0

        for cluster in clusters:
            cluster_rows = cluster["rows"]
            cluster_width = max(
                (self.row_width(row) for row in cluster_rows),
                default=0,
            )
            right_width += cluster_width + self.side_gap
            right_rows = max(right_rows, len(cluster_rows))

        if clusters:
            right_width -= self.side_gap

        canvas_width = max(
            1,
            self.scaled(10)
            + main_width
            + (self.side_gap + right_width if clusters else 0),
        )
        main_row_count = len(display_rows)
        row_count = max(main_row_count, right_rows)
        canvas_height = (
            self.header_height
            + self.scaled(5)
            + row_count * (self.key_height + self.row_gap)
        )

        self.canvas = tk.Canvas(
            self.root,
            width=canvas_width,
            height=canvas_height,
            bg=TRANSPARENT,
            bd=0,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        image_path = self.settings.get("background_image", "")
        if image_path and os.path.isfile(image_path):
            self.canvas.configure(bg=PANEL_COLOR)
            self.set_background_image(image_path, canvas_width, canvas_height)

        self.layout_title_item = self.canvas.create_text(
            self.scaled(8),
            self.header_height // 2,
            text=self.layout_name,
            anchor="w",
            fill=self.settings["text_color"],
            font=(
                self.settings["font_family"],
                self.scaled(self.settings["font_size"], minimum=5),
                "bold",
            ),
        )

        self.status_item = self.canvas.create_text(
            canvas_width - self.scaled(31),
            self.header_height // 2,
            text="drag · ⚙ for options",
            anchor="e",
            fill=self.settings["text_color"],
            font=(
                self.settings["font_family"],
                self.scaled(max(7, self.settings["font_size"] - 2), minimum=5),
            ),
        )

        self.gear_item = self.canvas.create_text(
            canvas_width - self.scaled(8),
            self.header_height // 2,
            text="⚙",
            anchor="e",
            fill=self.settings["text_color"],
            font=("Segoe UI Symbol", self.scaled(11, minimum=6), "bold"),
        )
        self.update_lock_indicators()

        body_y = self.header_height + self.scaled(3)

        for row_index, row in enumerate(display_rows):
            x = self.scaled(5)
            y = body_y + row_index * (self.key_height + self.row_gap)

            for label, scan, width in row:
                self.add_key(x, y, label, scan, width)
                x += self.cell_width(width)

        if clusters:
            cluster_x = x_right
            for cluster in clusters:
                for row_index, row in enumerate(cluster["rows"]):
                    x = cluster_x
                    y = body_y + row_index * (self.key_height + self.row_gap)

                    for label, scan, width in row:
                        if scan or label:
                            self.add_key(x, y, label, scan, width)
                        x += self.cell_width(width)

                cluster_width = max(
                    (self.row_width(row) for row in cluster["rows"]),
                    default=0,
                )
                cluster_x += cluster_width + self.side_gap

        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<Button-3>", self.menu)

        self.root.attributes("-alpha", self.settings["opacity"] / 100)
        self.root.update_idletasks()
        self.root.geometry(
            f"{canvas_width}x{canvas_height}+{max(0, old_x)}+{max(0, old_y)}"
        )

    def update_lock_indicators(self):
        state = "hidden" if self.locked else "normal"
        self.canvas.itemconfigure(self.layout_title_item, state=state)
        self.canvas.itemconfigure(self.status_item, state=state)
        self.canvas.itemconfigure(self.gear_item, state=state)

    def set_background_image(self, path, width, height):
        try:
            with Image.open(path) as source:
                image = ImageOps.contain(
                    source.convert("RGBA"),
                    (width, height),
                    method=Image.Resampling.LANCZOS,
                )

            self.background_photo = ImageTk.PhotoImage(image, master=self.root)
            self.canvas.create_image(
                width // 2,
                height // 2,
                image=self.background_photo,
                anchor="center",
                tags=("background",),
            )
            self.canvas.tag_lower("background")
        except (OSError, ValueError):
            self.background_photo = None

    def add_key(self, x, y, label, scan, width):
        ident = scan.upper() if scan else ""
        shown = self.key_label(ident, label) if ident else label
        key_width = self.key_width(width)

        fill = self.settings.get("key_fill") or ""
        outline = self.settings["outline_color"]

        rectangle = self.canvas.create_rectangle(
            x,
            y,
            x + key_width,
            y + self.key_height,
            fill=fill,
            outline=outline,
            width=self.scaled(1),
        )
        text = self.canvas.create_text(
            x + key_width // 2,
            y + self.key_height // 2,
            text=shown,
            fill=self.settings["text_color"],
            font=(
                self.settings["font_family"],
                self.scaled(self.settings["font_size"], minimum=5),
                "bold",
            ),
        )

        if ident:
            self.keys.setdefault(ident, []).append((rectangle, text))

            match = re.fullmatch(r"F(\d{1,2})", label)
            if match:
                self.function_keys[VK_F1 + int(match.group(1)) - 1] = ident

    def key_label(self, ident, fallback):
        if self.auto_labels and len(fallback) == 1 and fallback.isprintable():
            scan = int(ident[-2:], 16)
            lparam = (scan << 16) | (int(ident.startswith("E")) << 24)
            buffer = ctypes.create_unicode_buffer(32)

            if self.user32.GetKeyNameTextW(lparam, buffer, len(buffer)) > 0:
                if len(buffer.value) == 1:
                    return buffer.value.upper()

        return fallback

    def place_bottom_left(self):
        self.root.update_idletasks()
        height = self.root.winfo_height()
        if height <= 1:
            height = self.root.winfo_reqheight()
        y = max(0, self.root.winfo_screenheight() - height - 48)
        self.root.geometry(f"+12+{y}")

    def set_mouse_passthrough(self):
        style = self.user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)

        if self.locked:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT

        self.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        self.user32.SetWindowPos(
            self.hwnd,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    def toggle_lock(self):
        self.locked = not self.locked
        self.set_mouse_passthrough()
        self.update_lock_indicators()

    def start_drag(self, event):
        if self.locked:
            return

        if (
            event.y <= self.header_height
            and event.x >= self.canvas.winfo_width() - self.scaled(28)
        ):
            self.open_options()
            return

        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def drag(self, event):
        if self.locked:
            return

        self.root.geometry(
            f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}"
        )

    def menu(self, event):
        if self.locked:
            return
        self.show_options_menu(event.x_root, event.y_root)

    def open_options(self):
        if self.locked:
            return
        self.show_options_menu(
            self.root.winfo_pointerx(),
            self.root.winfo_pointery(),
        )

    def show_options_menu(self, x, y):
        if self.locked:
            return

        menu = tk.Menu(self.root, tearoff=False)

        for group in ("PC", "Laptop"):
            submenu = tk.Menu(menu, tearoff=False)
            for name, layout in self.layouts.items():
                if layout.get("group", "PC") == group:
                    submenu.add_command(
                        label=("✓ " if name == self.layout_name else "") + name,
                        command=lambda n=name: self.select_layout(n),
                    )
            if submenu.index("end") is not None:
                menu.add_cascade(label=group, menu=submenu)

        menu.add_command(
            label="Turn compact layout off" if self.compact
            else "Turn compact layout on",
            command=self.toggle_compact,
        )
        menu.add_command(
            label="Use preset labels" if self.auto_labels
            else "Use Windows detected labels",
            command=self.toggle_auto_labels,
        )
        menu.add_command(label="Settings…", command=self.open_settings)
        menu.add_command(
            label="Open layout definitions…",
            command=lambda: os.startfile(str(user_layout_file())),
        )
        menu.add_command(
            label="Check for updates…",
            command=lambda: self.check_for_updates(manual=True),
        )
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
        self.settings["layout_name"] = name
        save_settings(self.settings)
        self.build()

    def toggle_compact(self):
        self.compact = not self.compact
        self.settings["compact"] = self.compact
        save_settings(self.settings)
        self.build()

    def toggle_auto_labels(self):
        self.auto_labels = not self.auto_labels
        self.build()

    def open_settings(self):
        if self.locked:
            return

        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        SettingsDialog(
            self.root,
            self.settings,
            self.preview_settings,
            background_aspect=width / height,
        )

    def preview_settings(self, values):
        self.settings = dict(values)
        self.build()

    def flash(self, ident, pressed):
        for rectangle, text in self.keys.get(ident, []):
            self.canvas.itemconfigure(
                rectangle,
                fill=self.settings["pressed_color"]
                if pressed
                else (self.settings.get("key_fill") or ""),
            )
            self.canvas.itemconfigure(text, fill=self.settings["text_color"])

    def process_events(self):
        while True:
            try:
                ident, pressed, vk = self.events.get_nowait()
            except queue.Empty:
                break

            ident = self.function_keys.get(vk, ident)
            lock_name = self.settings.get("lock_key", "Shift")
            lock_codes = LOCK_KEY_VKS.get(lock_name, LOCK_KEY_VKS["Shift"])

            if vk in lock_codes:
                if pressed:
                    if ident not in self.lock_key_scans:
                        was_down = bool(self.lock_key_scans)
                        self.lock_key_scans.add(ident)
                        if not was_down:
                            self.toggle_lock()
                else:
                    self.lock_key_scans.discard(ident)

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
                    if target in self.active_chords:
                        if not set(combo.split("+")).issubset(self.held_ids):
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
                        messagebox.showinfo(
                            "KeyTap Overlay",
                            "You’re using the latest version.",
                            parent=self.root,
                        )
                    continue

                answer = messagebox.askyesno(
                    "KeyTap Overlay update available",
                    f"Version {result['version']} is available. "
                    f"You’re using version {current_version()}.\n\n"
                    "Download and install it now? KeyTap will close and reopen "
                    "after the update.",
                    parent=self.root,
                )
                if answer:
                    self.install_update(result)

            elif kind == "check_error":
                self.update_checking = False
                if manual:
                    messagebox.showwarning(
                        "KeyTap Overlay",
                        f"Couldn’t check for updates.\n\n{result}",
                        parent=self.root,
                    )

            elif kind == "install_started":
                self.update_checking = False
                outcome, release_url = result
                if outcome == "source":
                    webbrowser.open(release_url)
                    messagebox.showinfo(
                        "KeyTap Overlay update available",
                        "This copy was started from source code. The Releases page "
                        "is opening so you can download the updated app.",
                        parent=self.root,
                    )
                else:
                    messagebox.showinfo(
                        "Updating KeyTap Overlay",
                        "The update is ready. KeyTap Overlay will close, replace "
                        "its app file, and reopen.",
                        parent=self.root,
                    )
                    self.close()

            elif kind == "install_error":
                self.update_checking = False
                messagebox.showerror(
                    "KeyTap Overlay update failed",
                    str(result),
                    parent=self.root,
                )

    def install_update(self, release):
        self.update_checking = True

        def install():
            try:
                outcome = download_and_launch_update(release)
                self.update_results.put(
                    ("install_started", False, (outcome, release["release_url"]))
                )
            except Exception as exc:
                self.update_results.put(("install_error", False, str(exc)))

        threading.Thread(target=install, daemon=True).start()

    def close(self):
        if hasattr(self, "hook"):
            self.hook.close()
        self.root.destroy()


def main():
    KeyboardOverlayApp()


if __name__ == "__main__":
    main()