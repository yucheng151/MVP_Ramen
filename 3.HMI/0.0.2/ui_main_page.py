"""以設備 3D 圖為核心的主頁總覽。"""
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageEnhance, ImageTk

from register_map import SENSOR_BITS
from ui_common import BG, PANEL, TEXT, MUTED, GREEN, RED, YELLOW, BLUE, GRAY, button_style, status_color


ASSET_PATH = Path(__file__).resolve().parent / "assets" / "machine_overview.png"

# x/y 為圖片內 normalized coordinate，後續可直接微調。
HOTSPOTS = (
    {"id": "conveyor", "label": "Conveyor", "x": 0.54, "y": 0.57, "target_page": "ConveyorControlPage"},
    {"id": "robot", "label": "Robot", "x": 0.55, "y": 0.27, "target_page": None},
    {"id": "bowl_stack", "label": "Bowl Stack", "x": 0.03, "y": 0.46, "target_page": None},
    {"id": "ingredient", "label": "Ingredient Area", "x": 0.77, "y": 0.38, "target_page": None},
    {"id": "sensor_bowl_drop_confirm", "label": "Bowl Drop", "x": 0.28, "y": 0.50, "target_page": None},
    {"id": "sensor_pause_point_1", "label": "Pause 1", "x": 0.45, "y": 0.50, "target_page": None},
    {"id": "sensor_pause_point_2", "label": "Pause 2", "x": 0.62, "y": 0.50, "target_page": None},
    {"id": "sensor_right_stop_point", "label": "Right Stop", "x": 0.80, "y": 0.50, "target_page": None},
)


class MainPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._photo = None
        self._resize_job = None
        self._image_box = (0, 0, 1, 1)
        self._hovered_sensor_id = None
        self._bowl_button_hovered = False

        header = tk.Frame(self, bg=BG, height=84)
        header.pack(fill="x", padx=24, pady=(14, 4))
        header.pack_propagate(False)
        title = tk.Frame(header, bg=BG)
        title.pack(side="left", fill="y")
        tk.Label(title, text="MVP RAMEN MACHINE", bg=BG, fg=TEXT,
                 font=("Segoe UI", 25, "bold")).pack(anchor="w")
        tk.Label(title, text="SYSTEM OVERVIEW", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self.labels = {}
        summary = tk.Frame(header, bg=BG)
        summary.pack(side="right", fill="y")
        summary_actions = {
            "System": lambda: self.app.toggle_page("AlarmPage"),
            "Mode": self.app.toggle_mode,
            "PLC": lambda: self.app.toggle_page("CommunicationPage"),
            "IPC": lambda: self.app.toggle_page("IPCCommunicationPage"),
        }
        for col, name in enumerate(("Mode", "System", "PLC", "IPC")):
            item = tk.Frame(summary, bg=PANEL, width=118, height=58)
            item.grid(row=0, column=col, padx=3, sticky="nsew")
            item.grid_propagate(False)
            caption = tk.Label(item, text=name.upper(), bg=PANEL, fg=MUTED, font=("Segoe UI", 8), cursor="hand2")
            caption.pack(anchor="w", padx=12, pady=(6, 0))
            label = tk.Label(item, text="--", width=10, anchor="w", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold"))
            label.pack(anchor="w", padx=12)
            self.labels[name] = label
            action = summary_actions[name]
            for widget in (item, caption, label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _event, callback=action: callback())

        self.canvas = tk.Canvas(self, bg="#070b0f", highlightthickness=1,
                                highlightbackground="#293945", bd=0)
        self.canvas.pack(fill="both", expand=True, padx=24, pady=6)
        self.canvas.bind("<Configure>", self._schedule_render)
        self._source = self._load_source()

        if app.mock_mode:
            tk.Button(self, text="Mock Alarm", command=app.toggle_mock_alarm,
                      **button_style("#68404a")).place(relx=0.985, rely=0.985, anchor="se")

    def _load_source(self):
        if not ASSET_PATH.exists():
            return None
        image = Image.open(ASSET_PATH).convert("RGB")
        return ImageEnhance.Brightness(image).enhance(0.58)

    def _schedule_render(self, _event=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._render_scene)

    def _render_scene(self):
        self._resize_job = None
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 10 or height < 10:
            return
        self.canvas.delete("all")
        if self._source is None:
            self.canvas.create_text(width / 2, height / 2, text="找不到 assets/machine_overview.png",
                                    fill=RED, font=("Segoe UI", 16, "bold"))
            return
        scale = min(width / self._source.width, height / self._source.height)
        image_w, image_h = max(1, int(self._source.width * scale)), max(1, int(self._source.height * scale))
        image = self._source.resize((image_w, image_h), Image.Resampling.LANCZOS).convert("RGBA")
        image.alpha_composite(Image.new("RGBA", image.size, (5, 14, 21, 62)))
        self._photo = ImageTk.PhotoImage(image)
        left, top = (width - image_w) / 2, (height - image_h) / 2
        self._image_box = (left, top, image_w, image_h)
        self.canvas.create_image(left, top, image=self._photo, anchor="nw", tags="machine")
        self._draw_hotspots()

    def _draw_hotspots(self):
        self.canvas.delete("sensor_tooltip")
        left, top, width, height = self._image_box
        for hotspot in HOTSPOTS:
            x, y = left + hotspot["x"] * width, top + hotspot["y"] * height
            state = self._hotspot_state(hotspot["id"])
            color = status_color(state)
            tag = f"hotspot_{hotspot['id']}"
            is_sensor = hotspot["id"].startswith("sensor_")
            if is_sensor:
                color = GREEN if state == "Detected" else GRAY
                box_w, box_h = 22, 12
                self.canvas.create_rectangle(
                    x - box_w / 2, y - box_h / 2, x + box_w / 2, y + box_h / 2,
                    fill=color, outline="#d7e3e9", width=1,
                    tags=(tag, "hotspot"),
                )
                self.canvas.tag_bind(tag, "<Enter>",
                                     lambda _event, sensor_id=hotspot["id"]: self._show_sensor_tooltip(sensor_id))
                self.canvas.tag_bind(tag, "<Leave>", lambda _event: self._hide_sensor_tooltip())
                if self._hovered_sensor_id == hotspot["id"]:
                    self._draw_sensor_tooltip(hotspot, state, x, y)
                continue

            box_w, box_h = 142, 48
            self.canvas.create_rectangle(x - box_w/2, y - box_h/2, x + box_w/2, y + box_h/2,
                                         fill="#111d26", outline=color, width=3 if state == "Alarm" else 1,
                                         tags=(tag, f"{tag}_bg", "hotspot"))
            dot_size = 12
            self.canvas.create_oval(x - box_w/2 + 9, y - dot_size/2, x - box_w/2 + 9 + dot_size, y + dot_size/2,
                                    fill=color, outline="", tags=(tag, "hotspot"))
            text_x = x - box_w/2 + 24
            self.canvas.create_text(text_x, y - 9, text=hotspot["label"], anchor="w",
                                    fill=TEXT, font=("Segoe UI", 10, "bold"), tags=(tag, "hotspot"))
            self.canvas.create_text(text_x, y + 10, text=state, anchor="w",
                                    fill=color, font=("Segoe UI", 9), tags=(tag, "hotspot"))
            target = hotspot["target_page"]
            if target:
                self.canvas.tag_bind(tag, "<Button-1>", lambda _e, p=target: self.app.show_page(p))
                self.canvas.tag_bind(tag, "<Enter>", lambda _e: self.canvas.configure(cursor="hand2"))
                self.canvas.tag_bind(tag, "<Leave>", lambda _e: self.canvas.configure(cursor=""))
            elif (hotspot["id"] == "bowl_stack"
                  and self.app.machine_mode == "Manual"
                  and not self.app.snapshot.get("bowl_dispenser_busy", False)):
                self.canvas.tag_bind(tag, "<Button-1>", self._send_bowl_dispense)
                self.canvas.tag_bind(tag, "<Enter>", self._bowl_button_enter)
                self.canvas.tag_bind(tag, "<Leave>", self._bowl_button_leave)

    def _send_bowl_dispense(self, _event=None):
        """每次 click 僅送出一個 CMD_BOWL_DISPENSE。"""
        if (self.app.machine_mode != "Manual"
                or self.app.snapshot.get("bowl_dispenser_busy", False)):
            return
        self.app.command.send_bowl_dispense()

    def _bowl_button_enter(self, _event=None):
        self._bowl_button_hovered = True
        self.canvas.configure(cursor="hand2")
        self.canvas.itemconfigure("hotspot_bowl_stack_bg", fill="#315773")

    def _bowl_button_leave(self, _event=None):
        self._bowl_button_hovered = False
        self.canvas.configure(cursor="")
        self.canvas.itemconfigure("hotspot_bowl_stack_bg", fill="#111d26")

    def _show_sensor_tooltip(self, sensor_id):
        self._hovered_sensor_id = sensor_id
        self.canvas.delete("sensor_tooltip")
        hotspot = next(item for item in HOTSPOTS if item["id"] == sensor_id)
        left, top, width, height = self._image_box
        x = left + hotspot["x"] * width
        y = top + hotspot["y"] * height
        self._draw_sensor_tooltip(hotspot, self._hotspot_state(sensor_id), x, y)

    def _hide_sensor_tooltip(self):
        self._hovered_sensor_id = None
        self.canvas.delete("sensor_tooltip")

    def _draw_sensor_tooltip(self, hotspot, state, x, y):
        sensor_name = hotspot["id"].removeprefix("sensor_")
        bit = SENSOR_BITS[sensor_name]
        color = GREEN if state == "Detected" else GRAY
        box_w, box_h = 132, 40
        tip_x, tip_y = x, y - 38
        self.canvas.create_rectangle(
            tip_x - box_w / 2, tip_y - box_h / 2,
            tip_x + box_w / 2, tip_y + box_h / 2,
            fill="#0b141b", outline=color, width=1,
            tags="sensor_tooltip",
        )
        self.canvas.create_text(
            tip_x - box_w / 2 + 10, tip_y - 9,
            text=hotspot["label"], anchor="w", fill=TEXT,
            font=("Segoe UI", 8, "bold"), tags="sensor_tooltip",
        )
        self.canvas.create_text(
            tip_x - box_w / 2 + 10, tip_y + 10,
            text=f"D1110.{bit}  •  {'ON' if state == 'Detected' else 'OFF'}", anchor="w", fill=color,
            font=("Segoe UI", 7), tags="sensor_tooltip",
        )

    def _hotspot_state(self, hotspot_id):
        snapshot = self.app.snapshot
        if hotspot_id.startswith("sensor_"):
            sensor_name = hotspot_id.removeprefix("sensor_")
            return "Detected" if snapshot["sensors"].get(sensor_name, False) else "Not Detected"
        if hotspot_id == "conveyor":
            return snapshot["conveyor_state"]
        if hotspot_id == "communication":
            return "Online" if snapshot["online"] and snapshot["heartbeat_ok"] else "Offline"
        if hotspot_id == "ipc":
            return "Future"
        if hotspot_id == "robot":
            return "Future / Reserved"
        if hotspot_id == "bowl_stack":
            return "Busy" if snapshot.get("bowl_dispenser_busy", False) else "Ready"
        if hotspot_id == "ingredient":
            return "Reserved"
        return "Unknown"

    def refresh(self):
        snapshot = self.app.snapshot
        values = {"System": snapshot["system"], "Mode": self.app.machine_mode,
                  "PLC": "Online" if snapshot["online"] else "Offline",
                  "IPC": "Online" if snapshot["ipc_online"] else "Offline"}
        for key, value in values.items():
            self.labels[key].configure(text=value, fg=status_color(value))
        # 狀態更新時只重畫 overlay；尺寸改變則由 Configure 事件重建圖片。
        if self._photo:
            self.canvas.delete("hotspot")
            self._draw_hotspots()
