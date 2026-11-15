import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

import imageio_ffmpeg
from PIL import Image, ImageTk

BG = "#f3f6fa"
TEXT = "#172033"
MUTED = "#69758a"

class _CropDialog:
    def __init__(self, parent, image, aspect_ratio, title, on_save, is_mouse=False):
        self.image = image.convert("RGBA")
        self.aspect = max(1.0, float(aspect_ratio))
        self.view_width = 640
        self.view_height = max(180, round(self.view_width / self.aspect))
        self.on_save = on_save
        self.is_mouse = is_mouse
        self.zoom = 1.0
        self.center_x = self.image.width / 2
        self.center_y = self.image.height / 2
        self.drag_origin = None
        self.photo = None

        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        shell = tk.Frame(self.window, bg=BG, padx=18, pady=16)
        shell.pack(fill="both", expand=True)

        tk.Label(shell, text="Position your background", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(shell, text="Drag to move the preview. Adjust zoom, then use this crop.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 12))

        self.canvas = tk.Canvas(shell, width=self.view_width, height=self.view_height, bg="#111722", bd=0, highlightthickness=1, highlightbackground="#cbd5e1", cursor="fleur")
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)

        zoom_row = tk.Frame(shell, bg=BG)
        zoom_row.pack(fill="x", pady=(10, 4))

        tk.Label(zoom_row, text="Zoom", bg=BG, fg=TEXT).pack(side="left")

        self.zoom_var = tk.DoubleVar(value=1.0)
        ttk.Scale(zoom_row, from_=1.0, to=3.0, variable=self.zoom_var, command=self.set_zoom).pack(side="left", fill="x", expand=True, padx=10)

        self.zoom_label = tk.Label(zoom_row, text="1.0×", width=5, bg=BG, fg=TEXT)
        self.zoom_label.pack(side="right")

        buttons = tk.Frame(shell, bg=BG)
        buttons.pack(fill="x", pady=(10, 0))

        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(buttons, text="Use this crop", command=self.save_crop).pack(side="right", padx=(0, 8))

        self.render()
        self.window.update_idletasks()
        self.window.grab_set()

    def crop_box(self):
        width = self.image.width
        height = self.image.height

        if width / height > self.aspect:
            crop_height = height / self.zoom
            crop_width = crop_height * self.aspect
        else:
            crop_width = width / self.zoom
            crop_height = crop_width / self.aspect

        half_width = crop_width / 2
        half_height = crop_height / 2

        self.center_x = min(max(self.center_x, half_width), width - half_width)
        self.center_y = min(max(self.center_y, half_height), height - half_height)

        left = round(self.center_x - half_width)
        top = round(self.center_y - half_height)
        right = round(self.center_x + half_width)
        bottom = round(self.center_y + half_height)

        return (left, top, right, bottom)

    def normalized_crop(self):
        left, top, right, bottom = self.crop_box()
        return (left / self.image.width, top / self.image.height, right / self.image.width, bottom / self.image.height)

    def render(self):
        cropped = self.image.crop(self.crop_box()).resize((self.view_width, self.view_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(cropped, master=self.window)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        
        if self.is_mouse:
            self.draw_mouse_guide()
        else:
            self.draw_keyboard_guide()

    def draw_mouse_guide(self):
        cx = self.view_width / 2
        cy = self.view_height / 2
        w = self.view_height * 0.35
        h = w * 1.75
        x1 = cx - w/2
        y1 = cy - h/2
        x2 = cx + w/2
        y2 = cy + h/2

        self.canvas.create_arc(x1, y1, x2, y1 + w, start=0, extent=180, style=tk.ARC, outline="#ffffff", width=2)
        self.canvas.create_arc(x1, y2 - w, x2, y2, start=180, extent=180, style=tk.ARC, outline="#ffffff", width=2)
        self.canvas.create_line(x1, y1 + w/2, x1, y2 - w/2, fill="#ffffff", width=2)
        self.canvas.create_line(x2, y1 + w/2, x2, y2 - w/2, fill="#ffffff", width=2)
        
        self.canvas.create_line(cx, y1, cx, y1 + w/2, fill="#ffffff", width=2)
        self.canvas.create_line(x1, y1 + w/2, x2, y1 + w/2, fill="#ffffff", width=2)
        
        wheel_w = w * 0.25
        wheel_h = w * 0.45
        self.canvas.create_rectangle(cx - wheel_w/2, y1 + w/2 - wheel_h/2, cx + wheel_w/2, y1 + w/2 + wheel_h/2, outline="#ffffff", width=2)

    def draw_keyboard_guide(self):
        rows = [
            [("Esc", 0.8)] + [(f"F{i}", 0.8) for i in range(1, 13)],
            [(key, 1) for key in "`1234567890-="] + [("Back", 1.8)],
            [("Tab", 1.4)] + [(key, 1) for key in "QWERTYUIOP[]\\"],
            [("Caps", 1.7)] + [(key, 1) for key in "ASDFGHJKL;'"] + [("Enter", 1.7)],
            [("Shift", 2.1)] + [(key, 1) for key in "ZXCVBNM,./"] + [("Shift", 2.1)],
            [("Ctrl", 1.3), ("Win", 1.2), ("Alt", 1.2), ("Space", 5.5), ("Alt", 1.2), ("Menu", 1.2), ("Ctrl", 1.3)],
        ]

        max_units = max(sum(width for _, width in row) for row in rows)
        gap = 2
        key_height = max(12, round(self.view_height * 0.055))
        row_gap = max(3, round(key_height * 0.18))
        unit = (self.view_width * 0.88 - gap * 12) / max_units
        total_height = len(rows) * key_height + (len(rows) - 1) * row_gap
        start_y = (self.view_height - total_height) / 2

        for row_index, row in enumerate(rows):
            row_width = sum(width * unit for _, width in row) + gap * (len(row) - 1)
            x = (self.view_width - row_width) / 2
            y = start_y + row_index * (key_height + row_gap)

            for label, width in row:
                key_width = width * unit
                self.canvas.create_rectangle(x, y, x + key_width, y + key_height, outline="#ffffff", width=1)
                self.canvas.create_text(x + key_width / 2, y + key_height / 2, text=label, fill="#ffffff", font=("Segoe UI", max(6, round(key_height * 0.38))))
                x += key_width + gap

    def start_drag(self, event):
        self.drag_origin = (event.x, event.y, self.center_x, self.center_y, self.crop_box())

    def drag(self, event):
        if not self.drag_origin: return
        start_x, start_y, center_x, center_y, box = self.drag_origin
        crop_width = box[2] - box[0]
        crop_height = box[3] - box[1]

        self.center_x = center_x - (event.x - start_x) * crop_width / self.view_width
        self.center_y = center_y - (event.y - start_y) * crop_height / self.view_height
        self.render()

    def set_zoom(self, value):
        self.zoom = max(1.0, float(value))
        self.zoom_label.configure(text=f"{self.zoom:.1f}×")
        self.render()

class BackgroundCropDialog(_CropDialog):
    def __init__(self, parent, image_path, aspect_ratio, on_save, is_mouse=False):
        with Image.open(image_path) as source:
            image = source.convert("RGBA")
        self.on_image_save = on_save
        super().__init__(parent, image, aspect_ratio, "Fit background", self._save_image, is_mouse=is_mouse)

    def _save_image(self, _unused):
        folder = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "KeyTap-Overlay" / "backgrounds"
        folder.mkdir(parents=True, exist_ok=True)
        output_path = folder / f"background-{uuid4().hex}.png"
        self.image.crop(self.crop_box()).save(output_path, "PNG")
        self.on_image_save(str(output_path))
        self.window.destroy()

    def save_crop(self): self._save_image(None)

class GifBackgroundCropDialog(_CropDialog):
    def __init__(self, parent, gif_path, aspect_ratio, on_save, is_mouse=False):
        with Image.open(gif_path) as source:
            source.seek(0)
            frame = source.convert("RGBA")
        self.gif_path = gif_path
        self.on_gif_save = on_save
        super().__init__(parent, frame, aspect_ratio, "Fit GIF background", self._save_gif, is_mouse=is_mouse)

    def _save_gif(self, _unused):
        self.on_gif_save(self.gif_path, self.normalized_crop())
        self.window.destroy()

    def save_crop(self): self._save_gif(None)

class VideoBackgroundCropDialog(_CropDialog):
    def __init__(self, parent, video_path, aspect_ratio, on_save, is_mouse=False):
        self.video_path = video_path
        reader = imageio_ffmpeg.read_frames(video_path, pix_fmt="rgb24")
        try:
            metadata = next(reader)
            width, height = metadata["size"]
            frame_data = next(reader)
        finally:
            reader.close()
        frame = Image.frombytes("RGB", (width, height), frame_data).convert("RGBA")
        self.on_video_save = on_save
        super().__init__(parent, frame, aspect_ratio, "Fit video background", self._save_video, is_mouse=is_mouse)

    def _save_video(self, _unused):
        self.on_video_save(self.video_path, self.normalized_crop())
        self.window.destroy()

    def save_crop(self): self._save_video(None)