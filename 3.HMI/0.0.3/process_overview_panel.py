"""Compact process controls embedded on the right side of MainPage."""

import tkinter as tk
from tkinter import messagebox

from process_flow_widget import ProcessFlowWidget
from process_models import (
    AUTO_DEFAULTS, PROCESS_ALARM, PROCESS_COMPLETE, PROCESS_IDLE,
    PROCESS_RUNNING, validate_auto_recipe,
)
from register_map import CONVEYOR_SET_SPEED_WRITE, SEMI_AUTO_TEST_STEP_BITS
from ui_common import (
    BG, PANEL, PANEL_2, INPUT_BG, TEXT, MUTED, GREEN, RED, BLUE, button_style,
)


SEMI_PARAMETER = {
    1: ("煮麵秒數 / Cook Time (s)", "cook_time_sec", 180),
    2: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
    5: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
    7: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
}


class ProcessOverviewPanel(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=PANEL, width=570,
                         highlightbackground="#40515e", highlightthickness=1)
        self.app = app
        self.pack_propagate(False)
        self.selected_step = tk.IntVar(value=1)
        self.auto_speed = tk.StringVar(value=str(AUTO_DEFAULTS["conveyor_speed_rpm"]))
        self.auto_cook_time = tk.StringVar(value=str(AUTO_DEFAULTS["cook_time_sec"]))
        self.semi_pending = False
        self.semi_running_seen = False
        self.semi_selected_steps = set()
        self.semi_completed_steps = set()
        self.semi_active_step = None
        self.semi_steps = [
            ("STEP 10  煮麵＋出碗", SEMI_AUTO_TEST_STEP_BITS[10], tk.BooleanVar(value=False)),
            ("STEP 20  暫停點一", SEMI_AUTO_TEST_STEP_BITS[20], tk.BooleanVar(value=False)),
            ("STEP 30  放麵", SEMI_AUTO_TEST_STEP_BITS[30], tk.BooleanVar(value=False)),
            ("STEP 40  前三料", SEMI_AUTO_TEST_STEP_BITS[40], tk.BooleanVar(value=False)),
            ("STEP 50  暫停點二", SEMI_AUTO_TEST_STEP_BITS[50], tk.BooleanVar(value=False)),
            ("STEP 60  後三料", SEMI_AUTO_TEST_STEP_BITS[60], tk.BooleanVar(value=False)),
            ("STEP 70  停止點", SEMI_AUTO_TEST_STEP_BITS[70], tk.BooleanVar(value=False)),
            ("STEP 80  加湯", SEMI_AUTO_TEST_STEP_BITS[80], tk.BooleanVar(value=False)),
        ]

        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(header, text="LIVE RAMEN PROCESS", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.status_label = tk.Label(header, text="IDLE", bg=PANEL, fg=MUTED,
                                     font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="right")

        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=8, pady=4)

        self.flow = ProcessFlowWidget(
            self.body, on_semi_select=self._toggle_flow_step,
        )
        self.flow.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.parameter_area = tk.Frame(self.body, bg=PANEL_2, width=205)
        self.parameter_area.pack(side="right", fill="y", padx=(6, 0))
        self.parameter_area.pack_propagate(False)
        self._render_parameters()

        self.alarm_label = tk.Label(
            self, text="No Active Process Alarm", bg=PANEL, fg=GREEN,
            anchor="w", justify="left", font=("Microsoft JhengHei UI", 9, "bold"),
        )
        self.alarm_label.pack(fill="x", padx=12, pady=(3, 8))

    def _entry_row(self, parent, row, label, variable):
        row_frame = tk.Frame(parent, bg=PANEL_2)
        row_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        tk.Label(row_frame, text=label, bg=PANEL_2, fg=MUTED, anchor="w",
                 font=("Microsoft JhengHei UI", 9)).pack(fill="x", pady=(0, 3))
        entry = tk.Entry(
            row_frame, textvariable=variable, bg=INPUT_BG, fg=TEXT,
            insertbackground=TEXT, selectbackground=BLUE,
            selectforeground="white", relief="flat", font=("Segoe UI", 10),
        )
        entry.pack(fill="x")
        parent.grid_columnconfigure(0, weight=1)
        return entry

    def _render_parameters(self):
        for child in self.parameter_area.winfo_children():
            child.destroy()
        self.parameter_entries = []
        mode = self.app.machine_mode
        self.action_buttons = []
        self.semi_step_buttons = []
        if mode == "Auto":
            tk.Label(self.parameter_area, text="AUTO PARAMETERS", bg=PANEL_2, fg=TEXT,
                     font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 1, "輸送帶轉速 / Conveyor Speed (RPM)", self.auto_speed,
            ))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 2, "煮麵秒數 / Cook Time (s)", self.auto_cook_time,
            ))
            self.action_button = tk.Button(
                self.parameter_area, text="WRITE PARAMETERS", command=self._write_parameters,
                **button_style(GREEN),
            )
            self.action_button.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=7)
            self.action_buttons.append(self.action_button)
        else:
            tk.Label(self.parameter_area, text="SELECT STEPS ON FLOW", bg=PANEL_2, fg=TEXT,
                     font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 1, "輸送帶轉速 / Speed RPM", self.auto_speed,
            ))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 2, "煮麵時間 / Cook Time (s)", self.auto_cook_time,
            ))
            execute = tk.Button(
                self.parameter_area, text="執行選取 STEPS",
                command=self._send_semi_test, **button_style(GREEN),
            )
            execute.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(12, 3))
            self.semi_result = tk.Label(
                self.parameter_area, text="", bg=PANEL_2, fg=MUTED,
                wraplength=185, justify="left", anchor="w",
                font=("Microsoft JhengHei UI", 9),
            )
            self.semi_result.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=6)
            self.action_buttons.append(execute)

    def _toggle_flow_step(self, process_step):
        """Toggle one CMD60 mask bit by clicking a process-flow node."""
        if self.semi_pending or self.app.snapshot.get("semi_auto_running", False):
            return
        bit = SEMI_AUTO_TEST_STEP_BITS.get(process_step)
        if bit is None:
            return
        if process_step in (40, 60) and self._ipc_alarm_active():
            return
        for _label, item_bit, variable in self.semi_steps:
            if item_bit == bit:
                variable.set(not variable.get())
                break
        self.after_idle(self.refresh)

    def _toggle_semi_step(self, variable):
        if self.semi_pending or self.app.snapshot.get("semi_auto_running", False):
            return
        variable.set(not variable.get())
        self._refresh_semi_step_styles()

    def _refresh_semi_step_styles(self):
        for button, variable, _bit, _label in self.semi_step_buttons:
            selected = variable.get()
            button.configure(
                bg=BLUE if selected else "#314a5c",
                fg="white",
                activebackground="#2389df" if selected else "#30495b",
                highlightbackground="#61b5ff" if selected else "#7693a5",
                highlightcolor="#61b5ff" if selected else "#7693a5",
                relief="sunken" if selected else "flat",
            )

    def _write_parameters(self):
        data = {
            "conveyor_speed_rpm": self.auto_speed.get(),
            "cook_time_sec": self.auto_cook_time.get(),
        }
        errors = validate_auto_recipe(data)
        if errors:
            messagebox.showerror("WRITE PARAMETERS", "\n".join(errors), parent=self)
            return
        ok, message = self.app.write_auto_parameters(data)
        (messagebox.showinfo if ok else messagebox.showwarning)("WRITE PARAMETERS", message, parent=self)

    def _send_semi_test(self):
        if self.semi_pending or self.app.snapshot.get("semi_auto_running", False):
            messagebox.showwarning(
                "SEMI-AUTO TEST", "半自動正在執行，請等待完成。", parent=self,
            )
            return
        mask = sum(1 << bit for _label, bit, value in self.semi_steps if value.get())
        if mask == 0:
            messagebox.showwarning("SEMI-AUTO TEST", "請至少勾選一個 Step。", parent=self)
            return
        ipc_alarm = self._ipc_alarm_active()
        ipc_step_mask = (1 << SEMI_AUTO_TEST_STEP_BITS[40]) | (1 << SEMI_AUTO_TEST_STEP_BITS[60])
        if ipc_alarm and mask & ipc_step_mask:
            messagebox.showwarning(
                "SEMI-AUTO TEST",
                "IPC異常中，不能執行Step40前三料或Step60後三料。\n請取消這兩個Step後再執行。",
                parent=self,
            )
            return
        data = {
            "conveyor_speed_rpm": self.auto_speed.get(),
            "cook_time_sec": self.auto_cook_time.get(),
        }
        errors = validate_auto_recipe(data)
        if errors:
            messagebox.showerror("SEMI-AUTO TEST", "\n".join(errors), parent=self)
            return
        speed = int(data["conveyor_speed_rpm"])
        if not self.app.command.write_d(CONVEYOR_SET_SPEED_WRITE, speed):
            messagebox.showerror(
                "SEMI-AUTO TEST", "輸送帶轉速寫入D108失敗。", parent=self,
            )
            return
        result = self.app.command.send_semi_auto_test(mask)
        if result.ok:
            self.semi_pending = True
            self.semi_running_seen = False
            self.semi_selected_steps = {
                step for step, bit in SEMI_AUTO_TEST_STEP_BITS.items()
                if mask & (1 << bit)
            }
            self.semi_completed_steps.clear()
            self.semi_active_step = None
        self.semi_result.configure(
            text=(
                f"CMD {result.command_code} · INDEX {result.command_index}\n"
                f"MASK {mask} · SPEED {speed} RPM · COOK {data['cook_time_sec']} s\n"
                f"{result.message}"
            ),
            fg=GREEN if result.ok else RED,
        )

    def refresh(self):
        process = self.app.snapshot.get("process")
        if process is None:
            return
        mode = self.app.machine_mode
        semi_running = bool(self.app.snapshot.get("semi_auto_running", False))
        if self.semi_pending:
            if semi_running:
                self.semi_running_seen = True
                current_step = process.step
                if current_step in self.semi_selected_steps:
                    if self.semi_active_step not in (None, current_step):
                        self.semi_completed_steps.add(self.semi_active_step)
                    self.semi_active_step = current_step
                if hasattr(self, "semi_result"):
                    self.semi_result.configure(text="SEMI-AUTO RUNNING", fg=BLUE)
            elif self.semi_running_seen:
                # D1110.5 returning OFF after it was observed ON means PLC
                # completed the requested CMD60 selection.  Mark exactly the
                # selected Steps complete; skipped Steps remain gray.
                self.semi_completed_steps.update(self.semi_selected_steps)
                # CMD60 shares D1000~D1002 with mode selection.  Release the
                # completed handshake before allowing CMD30/31/32.
                self.app.command.clear_command()
                self.semi_pending = False
                self.semi_running_seen = False
                self.semi_active_step = None
                # The PLC run is finished. Clear the edit-side selection so it
                # is ready for the next request, while semi_completed_steps
                # continues to show which Steps were actually executed.
                for _label, _bit, variable in self.semi_steps:
                    variable.set(False)
                if hasattr(self, "semi_result"):
                    self.semi_result.configure(text="SEMI-AUTO COMPLETED", fg=GREEN)
            elif hasattr(self, "semi_result"):
                # Command was sent but PLC Running has not turned ON yet.
                # Never leave stale RUNNING text on screen while Bit5 is OFF.
                self.semi_result.configure(text="WAITING FOR SEMI-AUTO RUNNING", fg=YELLOW)
        elif hasattr(self, "semi_result") and semi_running:
            # Reflect an externally active PLC semi-auto run even if this HMI
            # did not originate the command.
            self.semi_result.configure(text="SEMI-AUTO RUNNING", fg=BLUE)
        if not self.app.snapshot.get("online", False) and self.semi_pending:
            self.semi_pending = False
            self.semi_running_seen = False
            if hasattr(self, "semi_result"):
                self.semi_result.configure(text="PLC OFFLINE", fg=RED)
        expected_mode = getattr(self, "_rendered_mode", None)
        if expected_mode != mode:
            self._rendered_mode = mode
            self._render_parameters()
        ipc_alarm = self._ipc_alarm_active()
        non_ipc_alarms = [
            name for name in self.app.active_alarms
            if not self._is_ipc_alarm_name(name)
        ]
        ipc_only_alarm = ipc_alarm and not non_ipc_alarms
        blocked_steps = set()
        if mode == "Semi Auto" and not semi_running:
            if non_ipc_alarms:
                blocked_steps.update(SEMI_AUTO_TEST_STEP_BITS)
            elif ipc_alarm:
                blocked_steps.update((40, 60))
        for step, bit in SEMI_AUTO_TEST_STEP_BITS.items():
            if step in blocked_steps:
                for _label, item_bit, variable in self.semi_steps:
                    if item_bit == bit:
                        variable.set(False)
                        break
        self.flow.set_state(
            process, mode, self.app.snapshot.get("online", False),
            self.selected_step.get(),
            selected_steps=(
                self.semi_selected_steps
                if self.semi_pending or self.semi_running_seen
                else {
                    step for step, bit in SEMI_AUTO_TEST_STEP_BITS.items()
                    if any(
                        item_bit == bit and variable.get()
                        for _label, item_bit, variable in self.semi_steps
                    )
                }
            ),
            completed_steps=self.semi_completed_steps,
            semi_running=semi_running,
            suppress_process_alarm=ipc_only_alarm,
            sensor_status_word=self.app.snapshot.get("sensor_status_word", 0),
            blocked_steps=blocked_steps,
        )
        if mode == "Semi Auto" and ipc_only_alarm:
            # IPC communication alarms disable only IPC Steps. They must not
            # make a completed non-IPC Semi-Auto request appear stuck/alarming.
            display_status = (
                PROCESS_RUNNING if semi_running
                else PROCESS_COMPLETE if self.semi_completed_steps
                else PROCESS_IDLE
            )
        else:
            display_status = process.status
        self.status_label.configure(
            text=f"{process.step:02d} · {display_status}",
            fg=RED if display_status == PROCESS_ALARM else BLUE if display_status == PROCESS_RUNNING else GREEN,
        )
        ipc_alarm = self._ipc_alarm_active()
        non_ipc_alarms = [
            name for name in self.app.active_alarms
            if not self._is_ipc_alarm_name(name)
        ]
        process_alarm_blocks = (
            process.status == PROCESS_ALARM
            and not (ipc_alarm and not non_ipc_alarms)
        )
        process_running_blocks = (
            process.status == PROCESS_RUNNING and mode != "Semi Auto"
        )
        locked = (
            process_running_blocks
            or process_alarm_blocks
            or bool(non_ipc_alarms)
            or self.semi_pending
            or semi_running
        )
        for entry in self.parameter_entries:
            entry.configure(state="disabled" if locked else "normal")
        for button in self.action_buttons:
            button.configure(state="disabled" if locked else "normal")
        ipc_bits = {SEMI_AUTO_TEST_STEP_BITS[40], SEMI_AUTO_TEST_STEP_BITS[60]}
        self._refresh_semi_step_styles()
        for button, variable, bit, label in self.semi_step_buttons:
            ipc_step_disabled = ipc_alarm and bit in ipc_bits
            if ipc_step_disabled and variable.get():
                variable.set(False)
            step_locked = locked or ipc_step_disabled
            button.configure(
                state="disabled" if step_locked else "normal",
                text=f"{label}\nIPC OFFLINE" if ipc_step_disabled else label,
                disabledforeground="#71818b",
            )
            if locked:
                button.configure(
                    bg="#26343e" if not variable.get() else "#244c6a",
                    highlightbackground="#40515e",
                    highlightcolor="#40515e",
                    relief="flat",
                )
        if process.alarm.latched:
            self.alarm_label.configure(
                text=f"ALARM {process.alarm.code} · {process.alarm.source}\n{process.alarm.message}", fg=RED,
            )
        else:
            self.alarm_label.configure(text="No Active Process Alarm", fg=GREEN)

    @staticmethod
    def _is_ipc_alarm_name(name):
        text = str(name).lower()
        return "ipc" in text

    def _ipc_alarm_active(self):
        return any(self._is_ipc_alarm_name(name) for name in self.app.active_alarms)
