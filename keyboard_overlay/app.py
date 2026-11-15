import ctypes
import ctypes.wintypes
import os
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox

import imageio_ffmpeg
from PIL import Image, ImageOps, ImageSequence, ImageTk, ImageDraw

from .keyboard_hook import KeyboardHook
from .mouse_hook import MouseHook
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
    "Shift": {0x10, 0xA0, 0xA1}, "Ctrl": {0x11, 0xA2, 0xA3}, "Alt": {0x12, 0xA4, 0xA5},
    "Caps Lock": {0x14}, "Scroll Lock": {0x91}, "Pause": {0x13},
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

def apply_normalized_crop(frame, crop):
    if not crop or len(crop) != 4: return frame
    width, height = frame.size
    left, top, right, bottom = crop
    left = max(0, min(width - 1, int(float(left) * width)))
    top = max(0, min(height - 1, int(float(top) * height)))
    right = max(left + 1, min(width, int(float(right) * width)))
    bottom = max(top + 1, min(height, int(float(bottom) * height)))
    return frame.crop((left, top, right, bottom))

class GifReader:
    def __init__(self, path):
        self.path = path
        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _put_frame(self, frame_bytes, width, height, duration):
        if self.frames.full():
            try: self.frames.get_nowait()
            except queue.Empty: pass
        try: self.frames.put_nowait((frame_bytes, width, height, duration))
        except queue.Full: pass

    def _run(self):
        while not self.stop_event.is_set():
            try:
                with Image.open(self.path) as gif:
                    width, height = gif.size
                    for frame in ImageSequence.Iterator(gif):
                        if self.stop_event.is_set(): return
                        duration = max(20, int(frame.info.get("duration", 100)))
                        self._put_frame(frame.convert("RGB").tobytes(), width, height, duration)
                        if self.stop_event.wait(duration / 1000): return
            except Exception as exc:
                self.error = str(exc)
                return
    def stop(self): self.stop_event.set()

class VideoReader:
    def __init__(self, path):
        self.path = path
        self.frames = queue.Queue(maxsize=2)
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _put_frame(self, frame, width, height):
        if self.frames.full():
            try: self.frames.get_nowait()
            except queue.Empty: pass
        try: self.frames.put_nowait((frame, width, height))
        except queue.Full: pass

    def _run(self):
        while not self.stop_event.is_set():
            reader = None
            try:
                reader = imageio_ffmpeg.read_frames(self.path, pix_fmt="rgb24")
                metadata = next(reader)
                width, height = metadata["size"]
                fps = max(1.0, float(metadata.get("fps", 30)))
                interval = 1.0 / min(fps, 30.0)
                while not self.stop_event.is_set():
                    started = time.monotonic()
                    frame = next(reader)
                    self._put_frame(frame, width, height)
                    remaining = interval - (time.monotonic() - started)
                    if remaining > 0: self.stop_event.wait(remaining)
            except StopIteration:
                continue
            except Exception as exc:
                self.error = str(exc)
                return
            finally:
                if reader is not None:
                    try: reader.close()
                    except Exception: pass
    def stop(self): self.stop_event.set()

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
            saved_layout if saved_layout in self.layouts else next(
                (name for name, item in self.layouts.items() if item.get("group") == "PC"),
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
        self.mouse_events = queue.SimpleQueue() 
        self.update_results = queue.SimpleQueue()
        self.update_checking = False

        self.background_photo = None
        self.video_reader = None
        self.gif_reader = None
        self.video_after_id = None
        self.gif_after_id = None
        self.video_background_item = None
        self.gif_background_item = None
        self.background_error_shown = False

        self.mouse_bg_photo = None
        self.mouse_gif_reader = None
        self.mouse_video_reader = None
        self.mouse_gif_after_id = None
        self.mouse_video_after_id = None
        
        self.mouse_left = False
        self.mouse_right = False
        self.mouse_middle = False
        self.mouse_scroll = 0
        self.mouse_scroll_timer = None
        self.mouse_left_item = None
        self.mouse_right_item = None
        self.mouse_wheel_item = None

        self.user32 = ctypes.windll.user32
        self.user32.GetKeyNameTextW.argtypes = (ctypes.wintypes.LONG, ctypes.wintypes.LPWSTR, ctypes.c_int)
        self.user32.GetKeyNameTextW.restype = ctypes.c_int
        self.user32.GetWindowLongW.argtypes = (ctypes.wintypes.HWND, ctypes.c_int)
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowLongW.argtypes = (ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long)
        self.user32.SetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowPos.argtypes = (ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.wintypes.UINT)

        self.build()
        self.place_bottom_left()
        self.hwnd = ctypes.wintypes.HWND(self.root.winfo_id())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        try:
            self.hook = KeyboardHook(self.events)
            self.mouse_hook = MouseHook(self.mouse_events)
        except OSError as exc:
            messagebox.showerror("KeyTap Overlay", str(exc))
            self.stop_backgrounds()
            self.root.destroy()
            return

        self.root.after(15, self.process_events)
        self.root.after(2500, lambda: self.check_for_updates(manual=False))
        self.root.mainloop()

    @property
    def scale(self):
        try: return min(1.5, max(0.5, float(self.settings.get("keyboard_scale", 100)) / 100))
        except (TypeError, ValueError): return 1.0

    def scaled(self, value, minimum=1): return max(minimum, round(value * self.scale))
    def key_width(self, width): return self.scaled(max(3, int(width * 4)) * 8 + 4)
    def cell_width(self, width): return self.key_width(width) + self.scaled(BASE_KEY_GAP)
    def row_width(self, row): return sum(self.cell_width(item[2]) for item in row)

    def stop_backgrounds(self):
        for after_id in (self.video_after_id, self.gif_after_id, self.mouse_video_after_id, self.mouse_gif_after_id):
            if after_id is not None:
                try: self.root.after_cancel(after_id)
                except tk.TclError: pass
        self.video_after_id = None; self.gif_after_id = None
        self.mouse_video_after_id = None; self.mouse_gif_after_id = None
        
        for reader in (self.video_reader, self.gif_reader, self.mouse_video_reader, self.mouse_gif_reader):
            if reader is not None: reader.stop()
            
        self.video_reader = None; self.gif_reader = None
        self.mouse_video_reader = None; self.mouse_gif_reader = None

    def build(self):
        self.stop_backgrounds()

        for child in self.root.winfo_children():
            if not isinstance(child, tk.Toplevel): child.destroy()

        old_x = self.root.winfo_x()
        old_y = self.root.winfo_y()

        self.keys = {}
        self.background_photo = None; self.video_background_item = None; self.gif_background_item = None
        self.mouse_bg_photo = None; self.background_error_shown = False
        self.mouse_left_item = None; self.mouse_right_item = None; self.mouse_wheel_item = None

        self.header_height = self.scaled(BASE_HEADER_HEIGHT, minimum=12)
        self.key_height = self.scaled(BASE_KEY_HEIGHT, minimum=12)
        self.row_gap = self.scaled(BASE_ROW_GAP)
        self.key_gap = self.scaled(BASE_KEY_GAP)
        self.side_gap = self.scaled(BASE_SIDE_GAP)

        view_mode = self.settings.get("view_mode", "keyboard")
        self.settings["view_mode"] = view_mode
        
        self.show_kb = view_mode in ("keyboard", "both")
        show_mouse = view_mode in ("mouse", "both")

        self.mouse_width = self.scaled(80)
        self.mouse_height = self.scaled(140)

        layout = self.layouts[self.layout_name]
        rows = layout["rows"]
        fn_after = layout.get("fn_after") if layout.get("group") == "Laptop" else None

        display_rows = []
        if self.show_kb:
            for row_index, row in enumerate(rows):
                display_row = list(row)
                if fn_after is not None and row_index == len(rows) - 1:
                    display_row.insert(min(fn_after + 1, len(display_row)), ("Fn", "", 1))
                display_rows.append(display_row)

        main_width = max((self.row_width(row) for row in display_rows), default=0)
        clusters = []
        if not self.compact and self.show_kb:
            clusters = layout.get("right", [{"rows": NAV_ROWS}, {"rows": NUMPAD_ROWS}])

        x_right = self.scaled(5) + main_width + self.side_gap
        right_width = 0
        right_rows = 0

        for cluster in clusters:
            cluster_rows = cluster["rows"]
            cluster_width = max((self.row_width(row) for row in cluster_rows), default=0)
            right_width += cluster_width + self.side_gap
            right_rows = max(right_rows, len(cluster_rows))

        if clusters: right_width -= self.side_gap

        gap = self.scaled(35) if (self.show_kb and show_mouse) else 0
        
        kb_total_width = 0
        if self.show_kb:
            kb_total_width = self.scaled(10) + main_width + (self.side_gap + right_width if clusters else 0)

        canvas_width = max(
            1,
            kb_total_width + gap + (self.mouse_width if show_mouse else 0) + (self.scaled(10) if show_mouse else 0)
        )
        
        row_count = max(len(display_rows), right_rows)
        kb_height = self.header_height + self.scaled(5) + row_count * (self.key_height + self.row_gap)
        
        canvas_height = max(
            kb_height,
            self.header_height + self.scaled(15) + self.mouse_height if show_mouse else 0
        )

        self.canvas = tk.Canvas(self.root, width=canvas_width, height=canvas_height, bg=TRANSPARENT, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        video_path = self.settings.get("background_video", "")
        gif_path = self.settings.get("background_gif", "")
        image_path = self.settings.get("background_image", "")

        if self.show_kb:
            if video_path and os.path.isfile(video_path):
                self.start_video_background(video_path, kb_total_width, canvas_height)
            elif gif_path and os.path.isfile(gif_path):
                self.start_gif_background(gif_path, kb_total_width, canvas_height)
            elif image_path and os.path.isfile(image_path):
                self.set_background_image(image_path, kb_total_width, canvas_height)

        header_right_x = kb_total_width if self.show_kb else canvas_width

        self.layout_title_item = self.canvas.create_text(
            self.scaled(8), self.header_height // 2, text=self.layout_name, anchor="w",
            fill=self.settings["text_color"], font=(self.settings["font_family"], self.scaled(self.settings["font_size"], minimum=5), "bold")
        )
        self.status_item = self.canvas.create_text(
            header_right_x - self.scaled(31), self.header_height // 2, text="drag · ⚙ for options", anchor="e",
            fill=self.settings["text_color"], font=(self.settings["font_family"], self.scaled(max(7, self.settings["font_size"] - 2), minimum=5))
        )
        self.gear_item = self.canvas.create_text(
            header_right_x - self.scaled(8), self.header_height // 2, text="⚙", anchor="e",
            fill=self.settings["text_color"], font=("Segoe UI Symbol", self.scaled(11, minimum=6), "bold")
        )
        
        self.update_lock_indicators()

        body_y = self.header_height + self.scaled(3)

        if self.show_kb:
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
                            if scan or label: self.add_key(x, y, label, scan, width)
                            x += self.cell_width(width)
                    cluster_width = max((self.row_width(row) for row in cluster["rows"]), default=0)
                    cluster_x += cluster_width + self.side_gap

        if show_mouse:
            mouse_x = kb_total_width + gap
            mouse_y = body_y + self.scaled(5)
            self.draw_mouse(mouse_x, mouse_y)

        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<Button-3>", self.menu)

        self.root.attributes("-alpha", self.settings["opacity"] / 100)
        self.root.update_idletasks()
        self.root.geometry(f"{canvas_width}x{canvas_height}+{max(0, old_x)}+{max(0, old_y)}")

    def draw_mouse(self, x, y):
        w, h = self.mouse_width, self.mouse_height
        r = w // 2
        line_w = self.scaled(2)

        video_path = self.settings.get("mouse_background_video", "")
        gif_path = self.settings.get("mouse_background_gif", "")
        image_path = self.settings.get("mouse_background_image", "")

        if video_path and os.path.isfile(video_path):
            self.start_mouse_video_background(video_path, w, h, x, y)
        elif gif_path and os.path.isfile(gif_path):
            self.start_mouse_gif_background(gif_path, w, h, x, y)
        elif image_path and os.path.isfile(image_path):
            self.set_mouse_background_image(image_path, w, h, x, y)

        self.canvas.create_arc(x, y + h - w, x + w, y + h, start=180, extent=180, outline=self.settings["outline_color"], width=line_w, style=tk.ARC)
        self.canvas.create_line(x, y + r, x, y + h - r, fill=self.settings["outline_color"], width=line_w)
        self.canvas.create_line(x + w, y + r, x + w, y + h - r, fill=self.settings["outline_color"], width=line_w)

        fill_l = self.settings["pressed_color"] if self.mouse_left else ""
        self.mouse_left_item = self.canvas.create_arc(x, y, x + w, y + w, start=90, extent=90, fill=fill_l, outline=self.settings["outline_color"], width=line_w, style=tk.PIESLICE)
        
        fill_r = self.settings["pressed_color"] if self.mouse_right else ""
        self.mouse_right_item = self.canvas.create_arc(x, y, x + w, y + w, start=0, extent=90, fill=fill_r, outline=self.settings["outline_color"], width=line_w, style=tk.PIESLICE)

        self.canvas.create_line(x, y + r, x + w, y + r, fill=self.settings["outline_color"], width=line_w)
        self.canvas.create_line(x + r, y, x + r, y + r, fill=self.settings["outline_color"], width=line_w)

        wheel_w = w * 0.22
        wheel_h = w * 0.4
        wheel_x = x + r - wheel_w // 2
        wheel_y = y + r - wheel_h // 2
        fill_m = self.settings["pressed_color"] if self.mouse_middle else ""
        self.mouse_wheel_item = self.canvas.create_rectangle(wheel_x, wheel_y, wheel_x + wheel_w, wheel_y + wheel_h, fill=fill_m, outline=self.settings["outline_color"], width=line_w)

        sb_w = self.scaled(8)
        sb_h = self.scaled(16)
        sb_x = x - sb_w
        sb_y = y + w * 0.6
        self.canvas.create_rectangle(sb_x, sb_y, sb_x + sb_w, sb_y + sb_h, fill="#333333", outline=self.settings["outline_color"], width=line_w)
        self.canvas.create_rectangle(sb_x, sb_y + sb_h + self.scaled(2), sb_x + sb_w, sb_y + 2*sb_h + self.scaled(2), fill="#333333", outline=self.settings["outline_color"], width=line_w)

    def get_mouse_mask(self, w, h):
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        r = w // 2
        draw.ellipse((0, 0, w, w), fill=255)
        draw.ellipse((0, h - w, w, h), fill=255)
        draw.rectangle((0, r, w, h - r), fill=255)
        return mask

    def apply_mouse_mask(self, frame, w, h):
        frame = ImageOps.fit(frame, (w, h), method=Image.Resampling.LANCZOS)
        mask = self.get_mouse_mask(w, h)
        result = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        result.paste(frame, (0, 0), mask)
        return result

    def start_mouse_video_background(self, path, w, h, x, y):
        self.mouse_video_reader = VideoReader(path)
        self.mouse_bg_item = self.canvas.create_image(x, y, anchor="nw", tags=("mouse_bg",))
        self.poll_mouse_video_frames(w, h, x, y)

    def poll_mouse_video_frames(self, w, h, x, y):
        if self.mouse_video_reader is None: return
        if self.mouse_video_reader.error and not self.background_error_shown:
            self.background_error_shown = True
            messagebox.showerror("KeyTap Overlay", f"Could not play this mouse video:\n\n{self.mouse_video_reader.error}", parent=self.root)
        newest = None
        try:
            while True: newest = self.mouse_video_reader.frames.get_nowait()
        except queue.Empty: pass
        if newest is not None:
            frame_data, frame_width, frame_height = newest
            try:
                frame = Image.frombytes("RGB", (frame_width, frame_height), frame_data)
                frame = apply_normalized_crop(frame, self.settings.get("mouse_background_video_crop"))
                masked_frame = self.apply_mouse_mask(frame, w, h)
                self.mouse_bg_photo = ImageTk.PhotoImage(masked_frame, master=self.root)
                self.canvas.itemconfigure(self.mouse_bg_item, image=self.mouse_bg_photo)
            except (tk.TclError, ValueError): pass
        self.mouse_video_after_id = self.root.after(30, lambda: self.poll_mouse_video_frames(w, h, x, y))

    def start_mouse_gif_background(self, path, w, h, x, y):
        self.mouse_gif_reader = GifReader(path)
        self.mouse_bg_item = self.canvas.create_image(x, y, anchor="nw", tags=("mouse_bg",))
        self.poll_mouse_gif_frames(w, h, x, y)

    def poll_mouse_gif_frames(self, w, h, x, y):
        if self.mouse_gif_reader is None: return
        if self.mouse_gif_reader.error and not self.background_error_shown:
            self.background_error_shown = True
            messagebox.showerror("KeyTap Overlay", f"Could not play this mouse GIF:\n\n{self.mouse_gif_reader.error}", parent=self.root)
        newest = None
        try:
            while True: newest = self.mouse_gif_reader.frames.get_nowait()
        except queue.Empty: pass
        delay = 30
        if newest is not None:
            frame_data, frame_width, frame_height, delay = newest
            try:
                frame = Image.frombytes("RGB", (frame_width, frame_height), frame_data)
                frame = apply_normalized_crop(frame, self.settings.get("mouse_background_gif_crop"))
                masked_frame = self.apply_mouse_mask(frame, w, h)
                self.mouse_bg_photo = ImageTk.PhotoImage(masked_frame, master=self.root)
                self.canvas.itemconfigure(self.mouse_bg_item, image=self.mouse_bg_photo)
            except (tk.TclError, ValueError): pass
        self.mouse_gif_after_id = self.root.after(max(20, min(int(delay), 1000)), lambda: self.poll_mouse_gif_frames(w, h, x, y))

    def set_mouse_background_image(self, path, w, h, x, y):
        try:
            with Image.open(path) as source:
                frame = source.convert("RGBA")
                masked_frame = self.apply_mouse_mask(frame, w, h)
                self.mouse_bg_photo = ImageTk.PhotoImage(masked_frame, master=self.root)
                self.canvas.create_image(x, y, image=self.mouse_bg_photo, anchor="nw", tags=("mouse_bg",))
        except (OSError, ValueError): self.mouse_bg_photo = None

    def start_video_background(self, path, width, height):
        self.video_reader = VideoReader(path)
        self.video_background_item = self.canvas.create_image(width // 2, height // 2, anchor="center", tags=("background",))
        self.canvas.tag_lower("background")
        self.poll_video_frames(width, height)

    def poll_video_frames(self, width, height):
        if self.video_reader is None: return
        if self.video_reader.error and not self.background_error_shown:
            self.background_error_shown = True
            messagebox.showerror("KeyTap Overlay", f"Could not play this video:\n\n{self.video_reader.error}", parent=self.root)
        newest = None
        try:
            while True: newest = self.video_reader.frames.get_nowait()
        except queue.Empty: pass
        if newest is not None:
            frame_data, frame_width, frame_height = newest
            try:
                frame = Image.frombytes("RGB", (frame_width, frame_height), frame_data)
                frame = apply_normalized_crop(frame, self.settings.get("background_video_crop"))
                frame = ImageOps.fit(frame, (width, height), method=Image.Resampling.LANCZOS)
                self.background_photo = ImageTk.PhotoImage(frame, master=self.root)
                self.canvas.itemconfigure(self.video_background_item, image=self.background_photo)
            except (tk.TclError, ValueError): pass
        self.video_after_id = self.root.after(30, lambda: self.poll_video_frames(width, height))

    def start_gif_background(self, path, width, height):
        self.gif_reader = GifReader(path)
        self.gif_background_item = self.canvas.create_image(width // 2, height // 2, anchor="center", tags=("background",))
        self.canvas.tag_lower("background")
        self.poll_gif_frames(width, height)

    def poll_gif_frames(self, width, height):
        if self.gif_reader is None: return
        if self.gif_reader.error and not self.background_error_shown:
            self.background_error_shown = True
            messagebox.showerror("KeyTap Overlay", f"Could not play this GIF:\n\n{self.gif_reader.error}", parent=self.root)
        newest = None
        try:
            while True: newest = self.gif_reader.frames.get_nowait()
        except queue.Empty: pass
        delay = 30
        if newest is not None:
            frame_data, frame_width, frame_height, delay = newest
            try:
                frame = Image.frombytes("RGB", (frame_width, frame_height), frame_data)
                frame = apply_normalized_crop(frame, self.settings.get("background_gif_crop"))
                frame = ImageOps.fit(frame, (width, height), method=Image.Resampling.LANCZOS)
                self.background_photo = ImageTk.PhotoImage(frame, master=self.root)
                self.canvas.itemconfigure(self.gif_background_item, image=self.background_photo)
            except (tk.TclError, ValueError): pass
        self.gif_after_id = self.root.after(max(20, min(int(delay), 1000)), lambda: self.poll_gif_frames(width, height))

    def update_lock_indicators(self):
        title_state = "hidden" if (self.locked or not self.show_kb) else "normal"
        self.canvas.itemconfigure(self.layout_title_item, state=title_state)
        self.canvas.itemconfigure(self.status_item, state=title_state)
        
        gear_state = "hidden" if self.locked else "normal"
        self.canvas.itemconfigure(self.gear_item, state=gear_state)

    def set_background_image(self, path, width, height):
        try:
            with Image.open(path) as source:
                image = ImageOps.contain(source.convert("RGBA"), (width, height), method=Image.Resampling.LANCZOS)
            self.background_photo = ImageTk.PhotoImage(image, master=self.root)
            self.canvas.create_image(width // 2, height // 2, image=self.background_photo, anchor="center", tags=("background",))
            self.canvas.tag_lower("background")
        except (OSError, ValueError): self.background_photo = None

    def add_key(self, x, y, label, scan, width):
        ident = scan.upper() if scan else ""
        shown = self.key_label(ident, label) if ident else label
        key_width = self.key_width(width)
        rectangle = self.canvas.create_rectangle(x, y, x + key_width, y + self.key_height, fill=self.settings.get("key_fill") or "", outline=self.settings["outline_color"], width=self.scaled(1))
        text = self.canvas.create_text(x + key_width // 2, y + self.key_height // 2, text=shown, fill=self.settings["text_color"], font=(self.settings["font_family"], self.scaled(self.settings["font_size"], minimum=5), "bold"))
        if ident:
            self.keys.setdefault(ident, []).append((rectangle, text))
            match = re.fullmatch(r"F(\d{1,2})", label)
            if match: self.function_keys[VK_F1 + int(match.group(1)) - 1] = ident

    def key_label(self, ident, fallback):
        if self.auto_labels and len(fallback) == 1 and fallback.isprintable():
            scan = int(ident[-2:], 16)
            lparam = (scan << 16) | (int(ident.startswith("E")) << 24)
            buffer = ctypes.create_unicode_buffer(32)
            if self.user32.GetKeyNameTextW(lparam, buffer, len(buffer)) > 0:
                if len(buffer.value) == 1: return buffer.value.upper()
        return fallback

    def place_bottom_left(self):
        self.root.update_idletasks()
        height = self.root.winfo_height()
        if height <= 1: height = self.root.winfo_reqheight()
        y = max(0, self.root.winfo_screenheight() - height - 48)
        self.root.geometry(f"+12+{y}")

    def set_mouse_passthrough(self):
        style = self.user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        if self.locked: style |= WS_EX_TRANSPARENT
        else: style &= ~WS_EX_TRANSPARENT
        self.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        self.user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)

    def toggle_lock(self):
        self.locked = not self.locked
        self.set_mouse_passthrough()
        self.update_lock_indicators()

    def start_drag(self, event):
        if self.locked: return
        if event.y <= self.header_height and event.x >= self.canvas.winfo_width() - self.scaled(28):
            self.open_options()
            return
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def drag(self, event):
        if not self.locked:
            self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def menu(self, event):
        if not self.locked: self.show_options_menu(event.x_root, event.y_root)

    def open_options(self):
        if not self.locked: self.show_options_menu(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def show_options_menu(self, x, y):
        if self.locked: return
        menu = tk.Menu(self.root, tearoff=False)
        for group in ("PC", "Laptop"):
            submenu = tk.Menu(menu, tearoff=False)
            for name, layout in self.layouts.items():
                if layout.get("group", "PC") == group:
                    submenu.add_command(label=("✓ " if name == self.layout_name else "") + name, command=lambda n=name: self.select_layout(n))
            if submenu.index("end") is not None: menu.add_cascade(label=group, menu=submenu)
        menu.add_command(label="Turn compact layout off" if self.compact else "Turn compact layout on", command=self.toggle_compact)
        menu.add_command(label="Use preset labels" if self.auto_labels else "Use Windows detected labels", command=self.toggle_auto_labels)
        menu.add_command(label="Settings…", command=self.open_settings)
        menu.add_command(label="Open layout definitions…", command=lambda: os.startfile(str(user_layout_file())))
        menu.add_command(label="Check for updates…", command=lambda: self.check_for_updates(manual=True))
        menu.add_separator()
        menu.add_command(label="Quit", command=self.close)
        try: menu.tk_popup(x, y)
        finally: menu.grab_release()

    def select_layout(self, name):
        self.down.clear(); self.held_ids.clear(); self.active_chords.clear()
        self.layout_name = name; self.auto_labels = False
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
        if self.locked: return
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        SettingsDialog(self.root, self.settings, self.preview_settings, background_aspect=width / height)

    def preview_settings(self, values):
        self.settings = dict(values)
        self.build()

    def flash(self, ident, pressed):
        for rectangle, text in self.keys.get(ident, []):
            self.canvas.itemconfigure(rectangle, fill=self.settings["pressed_color"] if pressed else (self.settings.get("key_fill") or ""))
            self.canvas.itemconfigure(text, fill=self.settings["text_color"])
            
    def flash_mouse(self):
        if self.mouse_left_item: self.canvas.itemconfigure(self.mouse_left_item, fill=self.settings["pressed_color"] if self.mouse_left else "")
        if self.mouse_right_item: self.canvas.itemconfigure(self.mouse_right_item, fill=self.settings["pressed_color"] if self.mouse_right else "")
        if self.mouse_wheel_item: self.canvas.itemconfigure(self.mouse_wheel_item, fill=self.settings["pressed_color"] if self.mouse_middle else "")

    def process_events(self):
        while True:
            try: ident, pressed, vk = self.events.get_nowait()
            except queue.Empty: break

            ident = self.function_keys.get(vk, ident)
            lock_name = self.settings.get("lock_key", "Shift")
            lock_codes = LOCK_KEY_VKS.get(lock_name, LOCK_KEY_VKS["Shift"])

            if vk in lock_codes:
                if pressed:
                    if ident not in self.lock_key_scans:
                        was_down = bool(self.lock_key_scans)
                        self.lock_key_scans.add(ident)
                        if not was_down: self.toggle_lock()
                else: self.lock_key_scans.discard(ident)

            chords = self.layouts[self.layout_name].get("chords", {})
            if pressed and ident not in self.down:
                self.down.add(ident); self.flash(ident, True); self.held_ids.add(ident)
                combo = "+".join(sorted(self.held_ids))
                target = chords.get(combo)
                if target and target not in self.active_chords:
                    self.active_chords.add(target); self.flash(target, True)
            elif not pressed and ident in self.down:
                self.down.discard(ident); self.flash(ident, False); self.held_ids.discard(ident)
                for combo, target in chords.items():
                    if target in self.active_chords:
                        if not set(combo.split("+")).issubset(self.held_ids):
                            self.active_chords.discard(target); self.flash(target, False)

        while True:
            try: action, param = self.mouse_events.get_nowait()
            except queue.Empty: break

            if action == "click":
                if param in (0x0201, 0x0202):
                    self.mouse_left = (param == 0x0201); self.flash_mouse()
                elif param in (0x0204, 0x0205):
                    self.mouse_right = (param == 0x0204); self.flash_mouse()
                elif param in (0x0207, 0x0208):
                    self.mouse_middle = (param == 0x0207); self.flash_mouse()
            elif action == "scroll":
                if self.mouse_wheel_item:
                    self.canvas.itemconfigure(self.mouse_wheel_item, fill=self.settings["pressed_color"])
                    if self.mouse_scroll_timer: self.root.after_cancel(self.mouse_scroll_timer)
                    self.mouse_scroll_timer = self.root.after(150, self.reset_scroll)

        self.process_update_results()
        self.root.after(15, self.process_events)

    def reset_scroll(self):
        if self.mouse_wheel_item and not self.mouse_middle:
            self.canvas.itemconfigure(self.mouse_wheel_item, fill="")

    def check_for_updates(self, manual=True):
        if self.update_checking: return
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
            try: kind, manual, result = self.update_results.get_nowait()
            except queue.Empty: break

            if kind == "checked":
                self.update_checking = False
                if result is None:
                    if manual: messagebox.showinfo("KeyTap Overlay", "You’re using the latest version.", parent=self.root)
                    continue
                answer = messagebox.askyesno("KeyTap Overlay update available", f"Version {result['version']} is available. You’re using version {current_version()}.\n\nDownload and install it now? KeyTap will close and reopen after the update.", parent=self.root)
                if answer: self.install_update(result)
            elif kind == "check_error":
                self.update_checking = False
                if manual: messagebox.showwarning("KeyTap Overlay", f"Couldn’t check for updates.\n\n{result}", parent=self.root)
            elif kind == "install_started":
                self.update_checking = False
                outcome, release_url = result
                if outcome == "source":
                    webbrowser.open(release_url)
                    messagebox.showinfo("KeyTap Overlay update available", "This copy was started from source code. The Releases page is opening so you can download the updated app.", parent=self.root)
                else:
                    messagebox.showinfo("Updating KeyTap Overlay", "The update is ready. KeyTap Overlay will close, replace its app file, and reopen.", parent=self.root)
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
        self.stop_backgrounds()
        if hasattr(self, "hook"): self.hook.close()
        if hasattr(self, "mouse_hook"): self.mouse_hook.close()
        self.root.destroy()

def main():
    KeyboardOverlayApp()

if __name__ == "__main__":
    main()