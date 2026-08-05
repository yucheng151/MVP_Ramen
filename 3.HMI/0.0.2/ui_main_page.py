"""以設備 3D 圖為核心的主頁總覽。"""
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageEnhance, ImageTk

from register_map import SENSOR_BITS
from ui_common import (
    BG, PANEL, PANEL_2, TEXT, MUTED, GREEN, RED, YELLOW, BLUE, GRAY,
    EmergencyStopButton, button_style, status_color,
)


ASSET_PATH = Path(__file__).resolve().parent / "assets" / "machine_overview.png"

# x/y 為圖片內 normalized coordinate，後續可直接微調。
HOTSPOTS = (
    {"id": "conveyor", "label": "Conveyor", "x": 0.54, "y": 0.57, "target_page": "ConveyorControlPage"},
    {"id": "robot", "label": "Robot", "x": 0.55, "y": 0.27, "target_page": "RobotPage"},
    {"id": "bowl_stack", "label": "Bowl Stack", "x": 0.03, "y": 0.46, "target_page": None},
    {"id": "ingredient", "label": "Ingredient Area", "x": 0.77, "y": 0.38, "target_page": None},
    {"id": "sensor_bowl_drop_confirm", "label": "Bowl Drop", "x": 0.28, "y": 0.50, "target_page": None},
    {"id": "sensor_pause_point_1", "label": "Pause 1", "x": 0.45, "y": 0.50, "target_page": None},
    {"id": "sensor_pause_point_2", "label": "Pause 2", "x": 0.62, "y": 0.50, "target_page": None},
    {"id": "sensor_right_stop_point", "label": "Right Stop", "x": 0.80, "y": 0.50, "target_page": None},
)


class ModeSelectorKnob(tk.Frame):
    """Three-position Manual / Semi Auto / Auto UI-only selector."""

    def __init__(self, parent, command):
        super().__init__(parent, width=105, height=98, bg=BG)
        self.pack_propagate(False)
        asset_dir = Path(__file__).resolve().parent / "assets"
        self._manual_image = tk.PhotoImage(file=str(asset_dir / "mode_manual.png"))
        self._auto_image = tk.PhotoImage(file=str(asset_dir / "mode_auto.png"))
        semi_source = Image.open(asset_dir / "mode_manual.png").convert("RGBA")
        self._semi_image = ImageTk.PhotoImage(
            semi_source.rotate(-45, resample=Image.Resampling.BICUBIC)
        )
        self._button = tk.Button(
            self, image=self._manual_image, command=command,
            bg=BG, activebackground=BG, width=78, height=78,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self._button.pack()
        self._label = tk.Label(
            self, text="MANUAL", bg=BG, fg=YELLOW,
            font=("Segoe UI", 8, "bold"),
        )
        self._label.pack(pady=(0, 1))

    def set_mode(self, mode):
        if mode == "Manual":
            image, text, color = self._manual_image, "MANUAL", YELLOW
        elif mode == "Semi Auto":
            image, text, color = self._semi_image, "SEMI AUTO", BLUE
        else:
            image, text, color = self._auto_image, "AUTO", GREEN
        self._button.configure(image=image)
        self._label.configure(text=text, fg=color)


class InitializePhysicalButton(tk.Frame):
    """Blue physical pushbutton styled to match the EMC control."""

    def __init__(self, parent, command):
        super().__init__(parent, width=105, height=98, bg=BG)
        self.pack_propagate(False)
        asset_dir = Path(__file__).resolve().parent / "assets"
        self._normal_image = tk.PhotoImage(file=str(asset_dir / "initialize_button.png"))
        self._pressed_image = tk.PhotoImage(file=str(asset_dir / "initialize_button_pressed.png"))
        self._button = tk.Button(
            self, image=self._normal_image, command=command,
            bg=BG, activebackground=BG, width=78, height=78,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self._button.pack()
        self._button.bind(
            "<ButtonPress-1>",
            lambda _event: self._button.configure(image=self._pressed_image),
            add="+",
        )
        self._button.bind(
            "<ButtonRelease-1>",
            lambda _event: self.after(
                120, lambda: self._button.configure(image=self._normal_image)
            ),
            add="+",
        )
        self._label = tk.Label(
            self, text="INITIALIZE", bg=BG, fg=BLUE,
            font=("Segoe UI", 8, "bold"),
        )
        self._label.pack(pady=(0, 1))

    def set_enabled(self, enabled):
        self._button.configure(state="normal" if enabled else "disabled")
        self._label.configure(fg=BLUE if enabled else GRAY)


class AlarmResetPhysicalButton(tk.Frame):
    """Alarm reset button that flashes while any alarm is active."""

    def __init__(self, parent, command):
        super().__init__(parent, width=105, height=98, bg=BG)
        self.pack_propagate(False)
        asset_dir = Path(__file__).resolve().parent / "assets"
        self._normal_image = tk.PhotoImage(file=str(asset_dir / "alarm_reset.png"))
        self._active_image = tk.PhotoImage(file=str(asset_dir / "alarm_reset_active.png"))
        self._alarm_active = False
        self._flash_on = False
        self._flash_job = None
        self._button = tk.Button(
            self, image=self._normal_image, command=command,
            bg=BG, activebackground=BG, width=78, height=78,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self._button.pack()
        self._label = tk.Label(
            self, text="ALM RST", bg=BG, fg=YELLOW,
            font=("Segoe UI", 8, "bold"),
        )
        self._label.pack(pady=(0, 1))

    def set_state(self, alarm_active, online):
        # Do not use Tk's disabled state here: it grays out the alarm lamp image.
        # The command handler already blocks reset commands while PLC is offline.
        self._button.configure(
            state="normal",
            cursor="hand2" if online else "arrow",
        )
        alarm_active = bool(alarm_active)
        if alarm_active != self._alarm_active:
            self._alarm_active = alarm_active
            if alarm_active:
                self._flash_on = True
                self._flash()
            else:
                if self._flash_job is not None:
                    self.after_cancel(self._flash_job)
                    self._flash_job = None
                self._button.configure(image=self._normal_image)
        self._label.configure(
            fg=RED if alarm_active else YELLOW if online else GRAY
        )

    def _flash(self):
        if not self._alarm_active:
            return
        self._button.configure(
            image=self._active_image if self._flash_on else self._normal_image
        )
        self._flash_on = not self._flash_on
        self._flash_job = self.after(420, self._flash)


class MainControlPanel(tk.Frame):
    """Shared top control strip used by the overview and every detail page."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG, height=98)
        self.app = app
        self.grid_rowconfigure(0, minsize=98)
        for column in range(4):
            self.grid_columnconfigure(column, minsize=105, uniform="top-control")

        self.mode_knob = ModeSelectorKnob(self, app.toggle_mode)
        self.mode_knob.grid(row=0, column=0, padx=1, sticky="nsew")
        self.initialize_button = InitializePhysicalButton(self, self._initialize_machine)
        self.initialize_button.grid(row=0, column=1, padx=1, sticky="nsew")
        self.alarm_reset_button = AlarmResetPhysicalButton(self, self._reset_alarm)
        self.alarm_reset_button.grid(row=0, column=2, padx=1, sticky="nsew")

        emergency_group = tk.Frame(self, bg=BG, width=105, height=98)
        emergency_group.grid(row=0, column=3, padx=1, sticky="nsew")
        emergency_group.pack_propagate(False)
        self.emergency_stop_button = EmergencyStopButton(
            emergency_group, app.show_emergency_stop_unconfigured
        )
        self.emergency_stop_button.pack(anchor="n")
        tk.Label(
            emergency_group, text="EMC", bg=BG, fg=RED,
            font=("Segoe UI", 8, "bold"),
        ).pack(pady=(0, 1))

    def refresh(self):
        snapshot = self.app.snapshot
        self.mode_knob.set_mode(self.app.machine_mode)
        self.initialize_button.set_enabled(snapshot["online"])
        self.alarm_reset_button.set_state(
            snapshot["system"] == "Alarm", snapshot["online"]
        )

    def _initialize_machine(self):
        if not self.app.snapshot.get("online", False):
            messagebox.showerror("INITIALIZE", "PLC Offline，無法執行整機初始化。", parent=self)
            return
        if not messagebox.askyesno(
            "INITIALIZE", "確定要執行整台機台初始化？",
            icon="warning", parent=self,
        ):
            return
        result = self.app.command.send_initialize()
        if result.ok:
            messagebox.showinfo("INITIALIZE", "初始化命令已送出。", parent=self)
        else:
            messagebox.showerror("INITIALIZE", f"命令送出失敗：{result.message}", parent=self)

    def _reset_alarm(self):
        if not self.app.snapshot.get("online", False):
            messagebox.showerror("ALM RST", "PLC Offline，無法執行 Alarm Reset。", parent=self)
            return
        if not messagebox.askyesno(
            "ALM RST", "確定要執行 Alarm Reset？",
            icon="warning", parent=self,
        ):
            return
        result = self.app.send_alarm_reset()
        if result.ok:
            messagebox.showinfo("ALM RST", "Alarm Reset 命令已送出。", parent=self)
        else:
            messagebox.showerror("ALM RST", f"命令送出失敗：{result.message}", parent=self)


class SideNavigation(tk.Frame):
    """Shared fixed page navigation available on every HMI page."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG, width=190)
        self.app = app
        self._items = []
        self.status_labels = {}
        self.pack_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        nav_items = (
            ("HOME", "HME", "Home", "MainPage"),
            ("ALARM", "ALM", "System", "AlarmPage"),
            ("PLC COMM", "PLC", "PLC", "CommunicationPage"),
            ("IPC COMM", "IPC", "IPC", "IPCCommunicationPage"),
            ("ROBOT", "RBT", "Robot", "RobotPage"),
            ("CONVEYOR", "CNV", "Conveyor", "ConveyorControlPage"),
        )
        for row, (caption_text, short_text, key, page_name) in enumerate(nav_items):
            self.grid_rowconfigure(row, weight=1, uniform="main-nav")
            box = tk.Frame(
                self, bg=PANEL, highlightthickness=2,
                highlightbackground="#40515e", cursor="hand2",
            )
            box.grid(row=row, column=0, sticky="nsew", pady=3)
            caption = tk.Label(
                box, text=caption_text, bg=PANEL, fg=MUTED,
                font=("Segoe UI", 15, "bold"), cursor="hand2",
            )
            caption.pack(anchor="w", padx=12, pady=(8, 1))
            value = tk.Label(
                box, text="--", bg=PANEL, fg=TEXT,
                font=("Segoe UI", 11), cursor="hand2",
            )
            value.pack(anchor="w", padx=12)
            self.status_labels[key] = value
            action = (
                (lambda: app.show_page("MainPage"))
                if page_name == "MainPage"
                else (lambda page=page_name: app.toggle_page(page))
            )
            for widget in (box, caption, value):
                widget.bind("<Button-1>", lambda _event, callback=action: callback())
            self._items.append((box, caption, value, caption_text, short_text, page_name))

    def refresh(self):
        snapshot = self.app.snapshot
        arm_online = snapshot.get("arm_online")
        robot_manual = snapshot.get("robot_manual")
        robot_alarm = bool(
            (
                robot_manual is not None
                and robot_manual.read_ok
                and (
                    robot_manual.alarm_code not in (None, 0)
                    or (
                        robot_manual.result_code is not None
                        and 400 <= robot_manual.result_code <= 599
                    )
                )
            )
        )
        robot_state = (
            "Alarm" if robot_alarm
            else "Online" if arm_online is True
            else "Offline" if arm_online is False
            else "Unknown"
        )
        values = {
            "Home": "Main Page",
            "System": snapshot["system"],
            "PLC": "Online" if snapshot["online"] else "Offline",
            "IPC": "Online" if snapshot["ipc_online"] else "Offline",
            "Robot": robot_state,
            "Conveyor": snapshot["conveyor_state"],
        }
        for key, value in values.items():
            color = MUTED if key == "Home" else status_color(value)
            self.status_labels[key].configure(text=value, fg=color)
        current_page = self.app.current_page
        for box, caption, value, _full_text, _short_text, page_name in self._items:
            active = current_page == page_name
            box.configure(
                highlightthickness=2,
                highlightbackground=BLUE if active else "#40515e",
                bg="#213746" if active else PANEL,
            )
            item_bg = "#213746" if active else PANEL
            caption.configure(bg=item_bg, fg=TEXT if active else MUTED)
            value.configure(bg=item_bg)


class MainPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._photo = None
        self._resize_job = None
        self._image_box = (0, 0, 1, 1)
        self._hovered_sensor_id = None
        self._bowl_button_hovered = False

        header = tk.Frame(self, bg=BG, height=100)
        header.pack(fill="x", padx=24, pady=(14, 4))
        header.pack_propagate(False)
        title = tk.Frame(header, bg=BG)
        title.pack(side="left", fill="y")
        tk.Label(title, text="MVP RAMEN MACHINE", bg=BG, fg=TEXT,
                 font=("Segoe UI", 25, "bold")).pack(anchor="w")
        subtitle_row = tk.Frame(title, bg=BG)
        subtitle_row.pack(anchor="w")
        tk.Label(subtitle_row, text="SYSTEM OVERVIEW", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left")

        self._global_controls = MainControlPanel(header, app)
        self._global_controls.pack(side="right")

        self._side_nav = SideNavigation(self, app)
        self._side_nav.pack(side="left", fill="y", padx=(24, 6), pady=(6, 12))

        self.canvas = tk.Canvas(self, bg="#070b0f", highlightthickness=1,
                                highlightbackground="#293945", bd=0)
        self.canvas.pack(fill="both", expand=True, padx=(0, 24), pady=6)
        self.canvas.bind("<Configure>", self._schedule_render)
        self._source = self._load_source()

        if app.mock_mode:
            tk.Button(self, text="Mock Alarm", command=app.toggle_mock_alarm,
                      **button_style("#68404a")).place(relx=0.975, rely=0.16, anchor="ne")

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
                  and self.app.snapshot.get("online", False)
                  and not self.app.snapshot.get("bowl_dispenser_busy", False)):
                self.canvas.tag_bind(tag, "<Button-1>", self._send_bowl_dispense)
                self.canvas.tag_bind(tag, "<Enter>", self._bowl_button_enter)
                self.canvas.tag_bind(tag, "<Leave>", self._bowl_button_leave)

    def _send_bowl_dispense(self, _event=None):
        """每次 click 僅送出一個 CMD_BOWL_DISPENSE。"""
        if (self.app.machine_mode != "Manual"
                or not self.app.snapshot.get("online", False)
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
            arm_online = snapshot.get("arm_online")
            robot_manual = snapshot.get("robot_manual")
            if (
                (
                    robot_manual is not None
                    and robot_manual.read_ok
                    and (
                        robot_manual.alarm_code not in (None, 0)
                        or (
                            robot_manual.result_code is not None
                            and 400 <= robot_manual.result_code <= 599
                        )
                    )
                )
            ):
                return "Alarm"
            if arm_online is None:
                return "Unknown"
            return "Online" if arm_online else "Offline"
        if hotspot_id == "bowl_stack":
            if not snapshot.get("online", False):
                return "Unknown"
            return "Busy" if snapshot.get("bowl_dispenser_busy", False) else "Ready"
        if hotspot_id == "ingredient":
            return "Reserved"
        return "Unknown"

    def refresh(self):
        self._global_controls.refresh()
        self._side_nav.refresh()
        # 狀態更新時只重畫 overlay；尺寸改變則由 Configure 事件重建圖片。
        if self._photo:
            self.canvas.delete("hotspot")
            self._draw_hotspots()
