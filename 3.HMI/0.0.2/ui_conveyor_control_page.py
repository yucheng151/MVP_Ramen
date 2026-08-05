"""簡化版輸送帶操作頁：讀值、寫值、按住運轉、ALM。"""
import tkinter as tk
from tkinter import messagebox

from register_map import CONVEYOR_SET_SPEED_WRITE, FAULT_NAMES, PARAMETER_LIMITS, SENSOR_BITS
from ui_common import (
    BG, PANEL, PANEL_2, TEXT, MUTED, GREEN, RED, BLUE, GRAY,
    button_style,
)


READBACK_FIELDS = (
    ("Actual Speed", "RPM", "D101", 1),
    ("Actual Bus Current", "A", "D102", 2),
    ("Set Speed", "RPM", "D103", 3),
    ("Acceleration", "-", "D104", 4),
    ("Deceleration", "-", "D105", 5),
    ("Bus Current Setting", "-", "D106", 6),
    ("Phase Current Setting", "-", "D107", 7),
)

class ConveyorControlPage(tk.Frame):
    # 保留名稱供既有主頁入口相容；目前已無分頁。
    TAB_STATUS = "Status / Live Data"
    TAB_PARAMETER = "Parameter Edit"
    TAB_MANUAL = "Manual Control"
    TAB_FAULT = "Fault / Alarm"

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._run_pressed = False
        self._parameter_loaded = False
        self._sensor_tooltip = None
        self._build_header()
        self._build_content()

    def _build_header(self):
        from ui_main_page import MainControlPanel, SideNavigation

        header = tk.Frame(self, bg=BG, height=100)
        header.pack(fill="x", padx=24, pady=(14, 4))
        header.pack_propagate(False)
        title = tk.Frame(header, bg=BG)
        title.pack(side="left", fill="y")
        title_label = tk.Label(title, text="CONVEYOR CONTROL", bg=BG, fg=TEXT,
                               font=("Segoe UI", 25, "bold"))
        title_label.pack(anchor="w")
        subtitle = tk.Label(title, text="SELECT PAGE FROM LEFT MENU",
                            bg=BG, fg=MUTED, font=("Segoe UI", 10))
        subtitle.pack(anchor="w")
        self._global_controls = MainControlPanel(header, self.app)
        self._global_controls.pack(side="right", fill="y")
        self._side_nav = SideNavigation(self, self.app)
        self._side_nav.pack(side="left", fill="y", padx=(24, 6), pady=(6, 12))

    def _build_content(self):
        content = tk.Frame(self, bg=PANEL_2)
        content.pack(fill="both", expand=True, padx=(0, 24), pady=(0, 18))
        content.grid_columnconfigure(0, weight=1, uniform="column")
        content.grid_columnconfigure(1, weight=1, uniform="column")
        content.grid_rowconfigure(0, weight=3)
        content.grid_rowconfigure(1, weight=2)
        self._build_readback(content)
        self._build_write(content)
        self._build_manual(content)
        self._build_alarm(content)

    def _build_sensor_strip(self):
        strip = tk.Frame(self, bg="#14212a", highlightbackground="#344957", highlightthickness=1)
        strip.pack(fill="x", padx=24, pady=(0, 6))
        self.sensor_labels = {}
        for key in SENSOR_BITS:
            label = tk.Label(strip, text="", bg=GRAY, width=6, height=1,
                             relief="solid", bd=1, cursor="hand2")
            label.pack(side="left", expand=True, padx=20, pady=8)
            label.bind("<Enter>", lambda event, sensor_key=key: self._show_sensor_tooltip(event, sensor_key))
            label.bind("<Leave>", self._hide_sensor_tooltip)
            self.sensor_labels[key] = label

    def _show_sensor_tooltip(self, event, key):
        self._hide_sensor_tooltip()
        names = {
            "bowl_drop_confirm": "Bowl Drop Confirm / 落碗確認",
            "pause_point_1": "Pause Point 1 / 暫停點 1",
            "pause_point_2": "Pause Point 2 / 暫停點 2",
            "right_stop_point": "Right Stop Point / 右側停止點",
        }
        detected = self.app.snapshot["sensors"].get(key, False)
        bit = SENSOR_BITS[key]
        tooltip = tk.Toplevel(self)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
        box = tk.Frame(tooltip, bg="#0b141b",
                       highlightbackground=GREEN if detected else GRAY,
                       highlightthickness=1, padx=12, pady=8)
        box.pack()
        tk.Label(box, text=names[key], bg="#0b141b", fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(box,
                 text=f"D1110.{bit}  •  {'Detected / ON' if detected else 'Not Detected / OFF'}",
                 bg="#0b141b", fg=GREEN if detected else GRAY,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        self._sensor_tooltip = tooltip

    def _hide_sensor_tooltip(self, _event=None):
        if self._sensor_tooltip is not None:
            self._sensor_tooltip.destroy()
            self._sensor_tooltip = None

    def _section(self, parent, title, row, column):
        frame = tk.Frame(parent, bg=PANEL, highlightbackground="#344957", highlightthickness=1)
        frame.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
        tk.Label(frame, text=title, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(12, 7))
        return frame

    def _build_readback(self, parent):
        frame = self._section(parent, "A. READBACK PARAMETERS", 0, 0)
        table = tk.Frame(frame, bg=PANEL)
        table.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for col, text in enumerate(("Parameter", "Value", "Unit", "PLC")):
            tk.Label(table, text=text, bg="#263946", fg=TEXT, padx=8, pady=5,
                     font=("Segoe UI", 9, "bold")).grid(row=0, column=col, sticky="ew")
        table.columnconfigure(0, weight=1)
        self.readback_labels = {}
        for row, (name, unit, address, _index) in enumerate(READBACK_FIELDS, 1):
            shade = PANEL if row % 2 else "#192a35"
            tk.Label(table, text=name, bg=shade, fg=TEXT, anchor="w", padx=8, pady=5).grid(row=row, column=0, sticky="ew")
            value = tk.Label(table, text="--", bg=shade, fg="#8bd5ff", anchor="e",
                             padx=8, font=("Segoe UI", 11, "bold"))
            value.grid(row=row, column=1, sticky="ew")
            tk.Label(table, text=unit, bg=shade, fg=MUTED, padx=8).grid(row=row, column=2, sticky="ew")
            tk.Label(table, text=address, bg=shade, fg=MUTED, padx=8).grid(row=row, column=3, sticky="ew")
            self.readback_labels[name] = value

    def _build_write(self, parent):
        frame = self._section(parent, "B. WRITE PARAMETERS", 0, 1)
        form = tk.Frame(frame, bg=PANEL)
        form.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        for col, text in enumerate(("Parameter", "Input", "Range", "PLC")):
            tk.Label(form, text=text, bg="#263946", fg=TEXT, padx=8, pady=5,
                     font=("Segoe UI", 9, "bold")).grid(row=0, column=col, sticky="ew")
        form.columnconfigure(0, weight=1)
        self.parameter_entries = {}
        for row, (name, limits) in enumerate(PARAMETER_LIMITS.items(), 1):
            address = 107 + row
            tk.Label(form, text=name, bg=PANEL, fg=TEXT, anchor="w", padx=8, pady=7).grid(row=row, column=0, sticky="ew")
            entry = tk.Entry(form, width=10, justify="right", bg="#0d171e", fg=TEXT,
                             insertbackground=TEXT, relief="flat", font=("Segoe UI", 12))
            entry.grid(row=row, column=1, padx=8)
            tk.Label(form, text=f"{limits[0]}～{limits[1]}", bg=PANEL, fg=MUTED, padx=8).grid(row=row, column=2)
            tk.Label(form, text=f"D{address}", bg=PANEL, fg="#7fc8ff", padx=8).grid(row=row, column=3)
            self.parameter_entries[name] = entry
        actions = tk.Frame(frame, bg=PANEL)
        actions.pack(fill="x", padx=16, pady=(4, 12))
        self.write_parameters_button = tk.Button(
            actions, text="Write Parameters", command=self.write_parameters,
            **button_style(BLUE),
        )
        self.write_parameters_button.pack(fill="x")

    def _build_manual(self, parent):
        frame = self._section(parent, "C. MANUAL RUN", 1, 0)
        controls = tk.Frame(frame, bg=PANEL)
        controls.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.hold_button = tk.Button(controls, text="HOLD TO RUN", bg=GREEN, fg="white",
                                     activebackground="#159766", activeforeground="white",
                                     relief="flat", bd=0, font=("Segoe UI", 20, "bold"), cursor="hand2")
        self.hold_button.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.hold_button.bind("<ButtonPress-1>", self._hold_start)
        self.hold_button.bind("<ButtonRelease-1>", self._hold_stop)
        self.manual_message = tk.Label(frame, text="Release HOLD TO RUN to stop", bg=PANEL,
                                       fg=MUTED, font=("Segoe UI", 10, "bold"))
        self.manual_message.pack(pady=(0, 10))

    def _build_alarm(self, parent):
        frame = self._section(parent, "D. ALM STATUS", 1, 1)
        body = tk.Frame(frame, bg=PANEL)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        summary = tk.Frame(body, bg=PANEL)
        summary.pack(fill="x")
        self.alm_lamp = tk.Label(summary, text="●", bg=PANEL, fg=GREEN,
                                 font=("Segoe UI", 25, "bold"))
        self.alm_lamp.pack(side="left", padx=(2, 10))
        info = tk.Frame(summary, bg=PANEL)
        info.pack(side="left", fill="x", expand=True)
        self.alm_status = tk.Label(info, text="ALM: Normal", bg=PANEL, fg=GREEN,
                                   font=("Segoe UI", 17, "bold"))
        self.alm_status.pack(anchor="w")
        self.alm_reason = tk.Label(info, text="No active fault", bg=PANEL, fg=MUTED,
                                   font=("Segoe UI", 9))
        self.alm_reason.pack(anchor="w")

        fault_grid = tk.Frame(body, bg="#15232d", highlightbackground="#344957",
                              highlightthickness=1)
        fault_grid.pack(fill="both", expand=True, pady=(5, 0))
        for column in range(3):
            fault_grid.grid_columnconfigure(column, weight=1, uniform="fault")
        fault_names = tuple(FAULT_NAMES) + (
            "Communication Timeout",
            "Initialize Timeout",
        )
        self.fault_status_labels = {}
        for index, name in enumerate(fault_names):
            row, column = divmod(index, 3)
            label = tk.Label(
                fault_grid, text=f"●  {name}", bg="#15232d", fg=MUTED,
                anchor="w", padx=7, pady=3, font=("Segoe UI", 8, "bold"),
            )
            label.grid(row=row, column=column, sticky="nsew", padx=1, pady=1)
            self.fault_status_labels[name] = label

    def select_tab(self, name):
        """相容既有主頁入口；本頁已沒有分頁。"""
        if name == self.TAB_PARAMETER:
            self.load_parameters()
            next(iter(self.parameter_entries.values())).focus_set()
        elif name == self.TAB_MANUAL:
            self.hold_button.focus_set()
        self.refresh()

    def load_parameters(self):
        for entry, value in zip(self.parameter_entries.values(), self.app.snapshot["parameters"]):
            entry.delete(0, "end")
            entry.insert(0, str(value))
        self._parameter_loaded = True

    def _validated_parameters(self):
        values = []
        try:
            for name, entry in self.parameter_entries.items():
                value = int(entry.get())
                low, high = PARAMETER_LIMITS[name]
                if not low <= value <= high:
                    raise ValueError(f"{name} 必須介於 {low}～{high}")
                values.append(value)
            return values
        except ValueError as exc:
            messagebox.showerror("Parameter Error", str(exc))
            return None

    def _write_values(self, values):
        if self.app.machine_mode != "Manual":
            messagebox.showwarning("Manual Mode Required", "Switch to Manual mode before editing parameters.")
            return False
        if not self.app.snapshot["online"]:
            messagebox.showerror("Error", "PLC Offline")
            return False
        if not self.app.plc.write_d_block(CONVEYOR_SET_SPEED_WRITE, values):
            messagebox.showerror("Error", self.app.plc.last_error or "Parameter write failed")
            return False
        return True

    def write_parameters(self):
        if self.app.machine_mode != "Manual":
            messagebox.showwarning("Manual Mode Required", "Switch to Manual mode before editing parameters.")
            return
        values = self._validated_parameters()
        if values is None or not messagebox.askyesno("Confirm Write", "確定寫入 D108～D112？"):
            return
        if self._write_values(values):
            messagebox.showinfo("Success", "Parameters written successfully")

    def _manual_allowed(self):
        if self.app.machine_mode != "Manual":
            self.manual_message.configure(text="Switch to Manual mode first", fg=RED)
            return False
        if not self.app.snapshot["online"]:
            self.manual_message.configure(text="PLC Offline", fg=RED)
            return False
        return True

    def _run_speed(self):
        try:
            return int(self.parameter_entries["Speed RPM"].get())
        except ValueError:
            self.manual_message.configure(text="Invalid Speed RPM", fg=RED)
            return None

    def _hold_start(self, _event=None):
        if self._run_pressed or not self._manual_allowed():
            return
        if not self.app.begin_manual_action("Conveyor"):
            self.manual_message.configure(
                text=self.app.manual_action_reason("Conveyor"), fg=RED
            )
            return
        speed = self._run_speed()
        if speed is None:
            self.app.finish_manual_action("Conveyor")
            return
        # ButtonPress 只處理一次；按住期間忽略任何重複事件。
        self._run_pressed = True
        result = self.app.command.send_conveyor_run(speed)
        if result.ok:
            self.app.set_conveyor_run_requested(True)
        else:
            self._run_pressed = False
            self.app.finish_manual_action("Conveyor")
        self.manual_message.configure(text="RUNNING — release to stop" if result.ok else result.message,
                                      fg=BLUE if result.ok else RED)

    def _hold_stop(self, _event=None):
        if not self._run_pressed:
            return
        # ButtonRelease only sends one Stop command.
        self._run_pressed = False
        self.stop_conveyor()

    def stop_conveyor(self):
        if not self.app.snapshot["online"]:
            self.manual_message.configure(text="PLC Offline", fg=RED)
            return
        self._run_pressed = False
        result = self.app.command.send_conveyor_stop()
        if result.ok:
            self.app.set_conveyor_run_requested(False)
        self.manual_message.configure(text="STOPPED" if result.ok else result.message,
                                      fg=GREEN if result.ok else RED)

    def show_fault_detail(self):
        word = self.app.snapshot["conveyor"][0]
        faults = [name for bit, name in enumerate(FAULT_NAMES) if word & (1 << bit)]
        timeout_word = self.app.snapshot["conveyor_timeout_word"]
        if timeout_word & 0x0001:
            faults.append("Conveyor Communication Timeout")
        if timeout_word & 0x0002:
            faults.append("Conveyor Initialize Timeout")
        messagebox.showinfo("Conveyor Fault Detail", "\n".join(f"• {name}" for name in faults) if faults else "No active fault")

    def refresh(self):
        snapshot = self.app.snapshot
        data = snapshot["conveyor"]
        values = {
            "Actual Speed": data[1],
            "Actual Bus Current": f"{data[2] / 10:.1f}",
            "Set Speed": data[3], "Acceleration": data[4], "Deceleration": data[5],
            "Bus Current Setting": data[6], "Phase Current Setting": data[7],
        }
        for name, value in values.items():
            self.readback_labels[name].configure(text=str(value))
        conveyor_state = snapshot["conveyor_state"]
        self._global_controls.refresh()
        self._side_nav.refresh()
        manual_enabled = (self.app.machine_mode == "Manual" and snapshot["online"]
                          and snapshot["conveyor_timeout_word"] == 0
                          and self.app.manual_action_available("Conveyor"))
        self.hold_button.configure(state="normal" if manual_enabled else "disabled")
        parameter_state = "normal" if self.app.machine_mode == "Manual" else "disabled"
        for entry in self.parameter_entries.values():
            entry.configure(state=parameter_state)
        self.write_parameters_button.configure(state=parameter_state)
        word = data[0]
        faults = [name for bit, name in enumerate(FAULT_NAMES) if word & (1 << bit)]
        timeout_word = snapshot["conveyor_timeout_word"]
        if timeout_word & 0x0001:
            faults.append("Conveyor Communication Timeout")
        if timeout_word & 0x0002:
            faults.append("Conveyor Initialize Timeout")
        active_faults = {
            name for bit, name in enumerate(FAULT_NAMES) if word & (1 << bit)
        }
        if timeout_word & 0x0001:
            active_faults.add("Communication Timeout")
        if timeout_word & 0x0002:
            active_faults.add("Initialize Timeout")
        for name, label in self.fault_status_labels.items():
            active = name in active_faults
            label.configure(
                fg=RED if active else MUTED,
                bg="#4a1f27" if active else "#15232d",
            )
        alarm = bool(faults)
        color = RED if alarm else GREEN
        self.alm_lamp.configure(fg=color)
        self.alm_status.configure(text="ALM: Alarm" if alarm else "ALM: Normal", fg=color)
        self.alm_reason.configure(text=" • ".join(faults) if faults else "No active fault",
                                  fg=RED if alarm else MUTED)
        if not self._parameter_loaded:
            self.load_parameters()
    def update_global_status(self):
        self._global_controls.refresh()
        self._side_nav.refresh()
