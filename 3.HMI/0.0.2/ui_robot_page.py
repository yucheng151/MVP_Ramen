"""Read-only Robot status and PLC command monitor page."""
import time
import tkinter as tk
from tkinter import messagebox, ttk

from ui_common import (
    BasePage, BG, PANEL, PANEL_2, TEXT, MUTED, GREEN, RED, GRAY, BLUE, YELLOW,
    button_style,
)


BASIC_STATUS_FIELDS = (
    ("busy", "手臂動作中", "D12100.0", False),
    ("status_output", "狀態輸出／通訊", "D12100.1", False),
    ("home_signal", "原點訊號", "D12100.2", False),
    ("error_signal", "錯誤訊號", "D12100.3", True),
    ("alarm_signal", "異常訊號", "D12100.4", True),
    ("estop_active", "緊急停止中", "D12100.5", True),
    ("program_running", "程式動作中", "D12100.6", False),
    ("sub_start", "Sub Start", "D12100.7", False),
    ("external_control_start", "外控開始", "D12100.9", False),
    ("remote_control_available", "可外控", "D12100.12", False),
)

ROBOT_DATA_FIELDS = (
    ("read_complete", "手臂讀取完成", "D12101"),
    ("error_code", "手臂異常代碼", "D12102"),
    ("action_complete", "手臂動作完成旗標", "D12103"),
    ("index", "定址編號", "D12104"),
)

COMMAND_STATUS_FIELDS = (
    ("external_stop", "外部停止", "D12150.0"),
    ("external_start", "外部啟動", "D12150.1"),
    ("servo_power_on", "給電投入", "D12150.2"),
    ("external_reset", "外部復位", "D12150.3"),
    ("program_select_bit1", "程序選擇位 1", "D12150.4"),
    ("program_select_pulse", "程序選擇脈衝", "D12150.5"),
    ("program_start_enable", "程序啟動可", "D12150.6"),
    ("intermittent", "間歇", "D12150.7"),
    ("plc_data_ready", "手臂讀取 PLC 數據旗標", "D12150.8"),
    ("interval_motion_enable", "間隔動作可動", "D12150.9"),
    ("shutdown", "關機", "D12150.13"),
)

COMMAND_DATA_FIELDS = (
    ("command_index", "定址編號", "D12151"),
    ("action_no", "動作編號", "D12152"),
    ("noodle_cabinet_no", "麵櫃編號", "D12153"),
    ("cut_no", "麵切編號", "D12154"),
    ("output_cabinet_no", "出麵櫃編號", "D12155"),
    ("noodle_type_no", "麵種編號", "D12156"),
)

ROBOT_COMMAND_TIMEOUT_SECONDS = 30.0
ROBOT_EXECUTE_DEBOUNCE_SECONDS = 0.8


class RobotPage(BasePage):
    """Robot monitor and PLC-mediated manual operation page."""

    def __init__(self, parent, app):
        super().__init__(parent, app, "ROBOT STATUS")
        self._bit_values = {}
        self._value_labels = {}
        self._robot_action_buttons = []
        self._robot_route_selectors = []
        self._pending_command_index = None
        self._command_sent_at = None
        self._command_state = "Idle"
        self._last_execute_at = 0.0
        self._timeout_latched = False
        self._cleanup_required = False
        self._last_result_text = "No command"

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1, uniform="robot-column")
        body.grid_columnconfigure(1, weight=1, uniform="robot-column")
        body.grid_rowconfigure(2, weight=1)
        body.grid_rowconfigure(3, weight=1)

        summary = tk.Frame(body, bg=PANEL, height=48)
        summary.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        summary.grid_propagate(False)
        tk.Label(
            summary, text="ROBOT COMM", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(16, 8))
        self._comm_value = tk.Label(
            summary, text="UNKNOWN", bg=PANEL, fg=GRAY,
            font=("Segoe UI", 13, "bold"),
        )
        self._comm_value.pack(side="left")
        tk.Label(
            summary, text="STATUS READ-ONLY · MANUAL CONTROL VIA PLC CMD 40",
            bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold"),
        ).pack(side="right", padx=16)

        self._build_route_panel(body)

        self._build_bit_panel(
            body, 2, 0, "ROBOT BASIC STATUS", BASIC_STATUS_FIELDS, padx=(0, 4)
        )
        self._build_value_panel(
            body, 2, 1, "ROBOT DATA", ROBOT_DATA_FIELDS, padx=(4, 0)
        )
        self._build_bit_panel(
            body, 3, 0, "PLC COMMAND MONITOR", COMMAND_STATUS_FIELDS,
            padx=(0, 4), pady=(8, 0),
        )
        self._build_value_panel(
            body, 3, 1, "PLC COMMAND DATA MONITOR", COMMAND_DATA_FIELDS,
            padx=(4, 0), pady=(8, 0),
        )

    def _build_route_panel(self, parent):
        """Restore the original From A / To B operation layout."""
        panel = tk.Frame(parent, bg=PANEL, height=154)
        panel.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        panel.grid_propagate(False)

        heading = tk.Frame(panel, bg=PANEL)
        heading.pack(fill="x", padx=14, pady=(7, 3))
        tk.Label(
            heading, text="手臂操作 · FROM A → TO B",
            bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        self._pending_label = tk.Label(
            heading, text="PENDING INDEX: --", bg=PANEL, fg=MUTED,
            font=("Consolas", 9, "bold"),
        )
        self._pending_label.pack(side="right")
        self._robot_idle_label = tk.Label(
            heading, text="ROBOT IDLE: --", bg=PANEL, fg=MUTED,
            font=("Consolas", 9, "bold"),
        )
        self._robot_idle_label.pack(side="right", padx=(0, 18))

        status_strip = tk.Frame(panel, bg=PANEL)
        status_strip.pack(fill="x", padx=14, side="bottom", pady=(0, 5))
        status_strip.grid_columnconfigure(1, weight=1)
        self._command_state_label = tk.Label(
            status_strip, text="IDLE", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self._command_state_label.grid(row=0, column=0, sticky="w")
        self._manual_reply = tk.Label(
            status_strip, text="No command", bg=PANEL, fg=MUTED,
            font=("Consolas", 8, "bold"), anchor="w",
        )
        self._manual_reply.grid(row=0, column=1, sticky="ew", padx=(14, 0))
        self._interlock_reason = tk.Label(
            status_strip, text="", bg=PANEL, fg=YELLOW,
            font=("Segoe UI", 8, "bold"), anchor="w",
        )
        self._interlock_reason.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0)
        )

        routes = tk.Frame(panel, bg=PANEL_2)
        routes.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        routes.grid_columnconfigure(0, weight=3, uniform="robot-action")
        routes.grid_columnconfigure(1, weight=2, uniform="robot-action")

        cook = tk.Frame(routes, bg=PANEL_2)
        cook.grid(row=0, column=0, sticky="nsew", padx=(6, 4), pady=6)
        cook_button = tk.Button(
            cook, text="取生麵", command=lambda: self._execute_robot_manual(1),
            **button_style(GREEN),
        )
        cook_button.pack(side="left", fill="y", padx=(0, 7))
        self._robot_action_buttons.append(cook_button)
        self._action_1_selectors = self._add_route(
            cook,
            (
                ("麵櫃 Noodle Cabinet", tuple(str(value) for value in range(1, 11))),
                ("麵切 Cut", tuple(str(value) for value in range(1, 7))),
                ("出麵櫃 Output", tuple(str(value) for value in range(1, 3))),
            ),
        )

        drain = tk.Frame(routes, bg=PANEL_2)
        drain.grid(row=0, column=1, sticky="nsew", padx=(4, 6), pady=6)
        drain_button = tk.Button(
            drain, text="倒熟麵", command=lambda: self._execute_robot_manual(2),
            **button_style(BLUE),
        )
        drain_button.pack(side="left", fill="y", padx=(0, 7))
        self._robot_action_buttons.append(drain_button)
        self._action_2_selectors = self._add_route(
            drain,
            (
                ("麵切 Cut", tuple(str(value) for value in range(1, 7))),
            ),
        )
    def _add_route(self, parent, fields):
        route = tk.Frame(parent, bg=PANEL_2)
        route.pack(side="left", fill="both", expand=True)
        selectors = []
        for column, (label, values) in enumerate(fields):
            field = tk.Frame(route, bg=PANEL_2)
            field.grid(row=0, column=column, sticky="nsew", padx=3)
            route.grid_columnconfigure(column, weight=1)
            tk.Label(
                field, text=label, bg=PANEL_2, fg=MUTED,
                font=("Segoe UI", 8), anchor="w",
            ).pack(fill="x")
            selector = ttk.Combobox(
                field, values=values, state="readonly",
                justify="center", width=7, font=("Segoe UI", 10),
            )
            selector.current(0)
            selector.pack(fill="x", pady=(2, 0))
            self._robot_route_selectors.append(selector)
            selectors.append(selector)
        return selectors

    def _execute_robot_manual(self, action_no):
        reasons = self._robot_interlock_reasons()
        if reasons:
            messagebox.showwarning("Robot Manual Interlock", reasons[0], parent=self)
            return
        now = time.monotonic()
        if now - self._last_execute_at < ROBOT_EXECUTE_DEBOUNCE_SECONDS:
            return

        try:
            if action_no == 1:
                cabinet, cut_no, output = (
                    int(selector.get()) for selector in self._action_1_selectors
                )
                valid_parameters = (
                    1 <= cabinet <= 10
                    and 1 <= cut_no <= 6
                    and 1 <= output <= 2
                )
            else:
                cabinet = 0
                cut_no = int(self._action_2_selectors[0].get())
                output = 0
                valid_parameters = 1 <= cut_no <= 6
        except (TypeError, ValueError):
            valid_parameters = False
        if not valid_parameters:
            messagebox.showerror(
                "Robot Manual", "Robot 手動參數超出允許範圍。", parent=self
            )
            return
        action_name = "取生麵" if action_no == 1 else "倒熟麵"
        if not messagebox.askyesno(
            "Robot Manual Execute",
            f"{action_name}\nActionNo: {action_no}\n"
            f"NoodleCabinetNo: {cabinet}\nCutNo: {cut_no}\n"
            f"OutputCabinetNo: {output}\n\n確定送出 CMD 40？",
            parent=self,
        ):
            return
        if not self.app.begin_manual_action("Robot"):
            messagebox.showwarning(
                "Robot Manual Interlock",
                self.app.manual_action_reason("Robot"),
                parent=self,
            )
            return
        self._last_execute_at = time.monotonic()
        result = self.app.command.send_robot_manual(
            action_no, cabinet, cut_no, output
        )
        if not result.ok:
            self.app.finish_manual_action("Robot")
            messagebox.showerror("Robot Manual", result.message, parent=self)
            return
        self._pending_command_index = result.command_index
        self._command_sent_at = time.monotonic()
        self._command_state = "Pending"
        self._last_result_text = f"CMD 40 / Index #{result.command_index} pending"
        self._pending_label.configure(
            text=f"PENDING INDEX: #{result.command_index}", fg=BLUE
        )
        self._command_state_label.configure(text="PENDING", fg=BLUE)
        self._manual_reply.configure(
            text=f"PENDING · CMD 40 · INDEX #{result.command_index} · WAIT ACK",
            fg=BLUE,
        )

    def _motion_signals_clear(self):
        manual_reply = self.app.snapshot.get("robot_manual")
        return bool(
            manual_reply is not None
            and manual_reply.read_ok
            and manual_reply.status not in (1, 2)
            and manual_reply.result_code != 240
        )

    def _robot_interlock_reasons(self):
        snapshot = self.app.snapshot
        robot = snapshot.get("robot")
        manual_reply = snapshot.get("robot_manual")
        reasons = []
        if not snapshot.get("online"):
            reasons.append("PLC is offline")
        if not snapshot.get("heartbeat_ok"):
            reasons.append("Heartbeat timeout")
        if self.app.machine_mode != "Manual":
            reasons.append("Please switch to Manual Mode")
        if robot is None or not robot.read_ok or not robot.busy:
            reasons.append("Robot is Offline")
        if manual_reply is None or not manual_reply.read_ok:
            reasons.append("Robot manual status communication is offline")
        elif manual_reply.robot_idle is not True:
            reasons.append("Robot is not Idle (D1124.0 = OFF)")
        if (
            manual_reply is not None
            and manual_reply.read_ok
            and (
                manual_reply.status in (1, 2)
                or manual_reply.result_code == 240
            )
        ):
            if self._pending_command_index is None:
                reasons.append(
                    "PLC reports Robot Manual Waiting/Running without HMI Pending"
                )
            else:
                reasons.append("Previous Robot command is Waiting or Running")
        if (
            manual_reply is not None
            and manual_reply.read_ok
            and manual_reply.alarm_code not in (None, 0)
        ):
            reasons.append("Robot manual alarm is active")
        if self._pending_command_index is not None:
            reasons.append("Previous command is still running")
        action_reason = self.app.manual_action_reason("Robot")
        if action_reason:
            reasons.append(action_reason)
        if self._cleanup_required:
            reasons.append("Robot command cleanup is pending")
        if self._timeout_latched:
            reasons.append("Robot command timeout; wait for all motion signals to reset")
        return reasons

    def _finish_robot_command(self, state, message, error=False, timeout=False):
        self._pending_command_index = None
        self._command_sent_at = None
        self._command_state = state
        self._last_result_text = message
        self._timeout_latched = self._timeout_latched or timeout
        self._cleanup_required = True
        if self.app.snapshot.get("online"):
            self._cleanup_required = not self.app.command.clear_robot_manual_command()
        if not self._cleanup_required:
            self.app.finish_manual_action("Robot")
        self._pending_label.configure(text="PENDING INDEX: --", fg=MUTED)
        color = RED if error or timeout else GREEN
        self._command_state_label.configure(text=state.upper(), fg=color)
        self._manual_reply.configure(text=message, fg=color)
        if self._cleanup_required:
            messagebox.showerror(
                "Robot Manual",
                f"{message}\n\nD1002 / D1000 cleanup failed or PLC is offline.",
                parent=self,
            )
        elif error or timeout:
            messagebox.showerror("Robot Manual", message, parent=self)
        else:
            messagebox.showinfo("Robot Manual", message, parent=self)

    def _update_robot_command_state(self):
        snapshot = self.app.snapshot
        if self._cleanup_required and snapshot.get("online"):
            self._cleanup_required = not self.app.command.clear_robot_manual_command()
            if not self._cleanup_required:
                self.app.finish_manual_action("Robot")
        if (
            self._timeout_latched
            and self._pending_command_index is None
            and self._motion_signals_clear()
        ):
            self._timeout_latched = False

        if self._pending_command_index is None:
            return
        if not snapshot.get("online"):
            self._finish_robot_command(
                "Error", "Robot command failed: PLC Offline", error=True
            )
            return
        if not snapshot.get("heartbeat_ok"):
            self._finish_robot_command(
                "Error", "Robot command failed: Heartbeat Timeout", error=True
            )
            return
        robot = snapshot.get("robot")
        if robot is None or not robot.read_ok or not robot.busy:
            self._finish_robot_command(
                "Error", "Robot command failed: Robot Offline", error=True
            )
            return
        if (
            self._command_sent_at is not None
            and time.monotonic() - self._command_sent_at
            >= ROBOT_COMMAND_TIMEOUT_SECONDS
        ):
            self._finish_robot_command(
                "Timeout", "Robot command timeout", error=True, timeout=True
            )
            return

        reply = snapshot.get("robot_manual")
        if reply is None or not reply.read_ok:
            self._command_state = "Pending"
            return
        ack_matches = reply.ack_index == self._pending_command_index
        if not ack_matches:
            self._command_state = "Pending"
            self._command_state_label.configure(text="PENDING", fg=BLUE)
            return
        if reply.alarm_code not in (None, 0):
            self._finish_robot_command(
                "Error",
                f"Robot Alarm · CMD 40 / Index #{reply.ack_index} · "
                f"Alarm Code {reply.alarm_code}",
                error=True,
            )
            return
        if (
            reply.result_code is not None
            and 400 <= reply.result_code <= 599
        ):
            self._finish_robot_command(
                "Error",
                f"Robot command failed · CMD 40 / Index #{reply.ack_index} · "
                f"Result {reply.result_code}",
                error=True,
            )
            return
        if reply.result_code == 200 and reply.alarm_code == 0:
            self._finish_robot_command(
                "Complete",
                f"Robot 手動操作完成 · CMD 40 / Index #{reply.ack_index}",
            )
            return
        if reply.status == 2:
            self._command_state = "Running"
            self._command_state_label.configure(text="RUNNING", fg=BLUE)
        elif reply.status == 1 or reply.result_code == 240:
            self._command_state = "Waiting"
            self._command_state_label.configure(text="WAITING", fg=BLUE)
        else:
            self._command_state = "Pending"
            self._command_state_label.configure(text="PENDING", fg=BLUE)

    def _panel(self, parent, row, column, title, padx, pady=(0, 0)):
        panel = tk.Frame(parent, bg=PANEL)
        panel.grid(
            row=row, column=column, sticky="nsew",
            padx=padx, pady=pady,
        )
        tk.Label(
            panel, text=title, bg=PANEL, fg=TEXT,
            font=("Segoe UI", 11, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(9, 6))
        content = tk.Frame(panel, bg=PANEL_2)
        content.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        content.grid_columnconfigure(1, weight=1)
        return content

    def _build_bit_panel(self, parent, row, column, title, fields, padx, pady=(0, 0)):
        content = self._panel(parent, row, column, title, padx, pady)
        # These monitor groups contain up to eleven signals.  A single vertical
        # list is taller than the usable area on 1366x768/remote-desktop
        # windows, so keep every signal visible in two compact columns.
        split_at = (len(fields) + 1) // 2
        content.grid_columnconfigure(1, weight=1, uniform="robot-bit-label")
        content.grid_columnconfigure(5, weight=1, uniform="robot-bit-label")
        for row_index, field in enumerate(fields):
            if len(field) == 4:
                key, label, address, warning = field
            else:
                key, label, address = field
                warning = False
            display_row = row_index % split_at
            column_offset = 0 if row_index < split_at else 4
            tk.Label(
                content, text="●", bg=PANEL_2, fg=GRAY,
                font=("Segoe UI", 9),
            ).grid(
                row=display_row, column=column_offset,
                padx=((8 if column_offset == 0 else 5), 3), pady=1,
            )
            tk.Label(
                content, text=label, bg=PANEL_2, fg=TEXT,
                font=("Segoe UI", 8), anchor="w",
            ).grid(
                row=display_row, column=column_offset + 1,
                sticky="ew", pady=1,
            )
            tk.Label(
                content, text=address, bg=PANEL_2, fg=MUTED,
                font=("Consolas", 7), anchor="e",
            ).grid(
                row=display_row, column=column_offset + 2,
                padx=(3, 3), pady=1,
            )
            value = tk.Label(
                content, text="--", width=3, bg=PANEL_2, fg=GRAY,
                font=("Segoe UI", 8, "bold"),
            )
            value.grid(
                row=display_row, column=column_offset + 3,
                padx=(0, (7 if column_offset else 4)), pady=1,
            )
            self._bit_values[key] = (value, warning)

    def _build_value_panel(self, parent, row, column, title, fields, padx, pady=(0, 0)):
        content = self._panel(parent, row, column, title, padx, pady)
        for row_index, (key, label, address) in enumerate(fields):
            tk.Label(
                content, text=label, bg=PANEL_2, fg=TEXT,
                font=("Segoe UI", 10), anchor="w",
            ).grid(row=row_index, column=0, sticky="ew", padx=(12, 8), pady=5)
            value = tk.Label(
                content, text="--", width=9, bg=PANEL_2, fg=TEXT,
                font=("Consolas", 11, "bold"), anchor="e",
            )
            value.grid(row=row_index, column=1, sticky="e", pady=5)
            tk.Label(
                content, text=address, width=8, bg=PANEL_2, fg=MUTED,
                font=("Consolas", 8), anchor="e",
            ).grid(row=row_index, column=2, padx=(8, 12), pady=5)
            self._value_labels[key] = value

    def refresh(self):
        self._update_robot_command_state()
        reasons = self._robot_interlock_reasons()
        controls_enabled = not reasons
        for button in self._robot_action_buttons:
            button.configure(state="normal" if controls_enabled else "disabled")
        for selector in self._robot_route_selectors:
            selector.configure(state="readonly" if controls_enabled else "disabled")
        snapshot = self.app.snapshot
        robot = snapshot.get("robot")
        manual_reply = snapshot.get("robot_manual")
        robot_alarm = bool(
            robot is not None
            and robot.read_ok
            and (
                robot.error_signal
                or robot.alarm_signal
                or robot.estop_active
                or robot.error_code not in (None, 0)
            )
        ) or bool(
            manual_reply is not None
            and manual_reply.read_ok
            and (
                manual_reply.alarm_code not in (None, 0)
                or (
                    manual_reply.result_code is not None
                    and 400 <= manual_reply.result_code <= 599
                )
            )
        )
        self._interlock_reason.configure(
            text="ALM" if robot_alarm else ("" if controls_enabled else reasons[0]),
            fg=RED if robot_alarm or not snapshot.get("online") else YELLOW,
        )
        self._pending_label.configure(
            text=(
                f"PENDING INDEX: #{self._pending_command_index}"
                if self._pending_command_index is not None
                else "PENDING INDEX: --"
            ),
            fg=BLUE if self._pending_command_index is not None else MUTED,
        )

        idle = (
            manual_reply.robot_idle
            if manual_reply is not None and manual_reply.read_ok
            else None
        )
        self._robot_idle_label.configure(
            text=(
                "ROBOT IDLE: ON" if idle is True
                else "ROBOT IDLE: OFF" if idle is False
                else "ROBOT IDLE: --"
            ),
            fg=GREEN if idle is True else RED if idle is False else MUTED,
        )
        if manual_reply is not None and manual_reply.read_ok:
            status = manual_reply.status
            ack = manual_reply.ack_index
            result = manual_reply.result_code
            alarm = manual_reply.alarm_code
            failed = bool(alarm) or (result is not None and 400 <= result <= 599)
            success = result == 200 and alarm == 0
            accepted = result == 240
            current_pending_reply = (
                self._pending_command_index is not None
                and ack == self._pending_command_index
            )
            running = current_pending_reply and status == 2
            waiting = current_pending_reply and (status == 1 or accepted)
            orphan_running = (
                self._pending_command_index is None
                and (status in (1, 2) or accepted)
            )
            if failed:
                reply_text = (
                    f"ROBOT ALARM · CMD 40 · INDEX #{ack} · "
                    f"RESULT {result} · ALM {alarm}"
                )
                reply_color = RED
            elif success:
                reply_text = f"SUCCESS · CMD 40 · INDEX #{ack} · RESULT 200"
                reply_color = GREEN
            elif running:
                reply_text = (
                    f"PLC RUNNING (D1120=2) · CMD 40 · "
                    f"INDEX #{ack} · RESULT {result}"
                )
                reply_color = BLUE
            elif waiting:
                reply_text = f"WAITING · CMD 40 · INDEX #{ack} · RESULT {result}"
                reply_color = BLUE
            elif orphan_running:
                reply_text = (
                    f"PLC STATUS {status} · NO HMI PENDING · "
                    f"ACK INDEX #{ack}"
                )
                reply_color = YELLOW
            elif status == 3:
                reply_text = (
                    f"PLC COMPLETED STATUS (D1120=3) · "
                    f"INDEX #{ack} · RESULT {result}"
                )
                reply_color = GREEN
            elif status == 4:
                reply_text = (
                    f"PLC ERROR STATUS (D1120=4) · "
                    f"INDEX #{ack} · RESULT {result} · ALM {alarm}"
                )
                reply_color = RED
            else:
                reply_text = (
                    f"IDLE · CMD 40 · INDEX #{ack} · "
                    f"STS {status} · RESULT {result}"
                )
                reply_color = MUTED
            if (
                self._pending_command_index is not None
                and ack != self._pending_command_index
            ):
                reply_text = (
                    f"PENDING · CMD 40 · INDEX #{self._pending_command_index} "
                    "· WAIT ACK"
                )
                reply_color = BLUE
            elif (
                self._pending_command_index is not None
                and ack == self._pending_command_index
                and status == 0
            ):
                reply_text = (
                    f"PENDING · CMD 40 · INDEX #{self._pending_command_index} "
                    f"· STATUS 0 · RESULT {result}"
                )
                reply_color = BLUE
            if self._command_state not in ("Complete", "Error", "Timeout"):
                self._manual_reply.configure(text=reply_text, fg=reply_color)
                if self._pending_command_index is None:
                    if running:
                        self._command_state_label.configure(text="RUNNING", fg=BLUE)
                    elif waiting:
                        self._command_state_label.configure(text="WAITING", fg=BLUE)
                    elif orphan_running:
                        self._command_state_label.configure(
                            text="PLC STATUS", fg=YELLOW
                        )
                    else:
                        self._command_state_label.configure(text="IDLE", fg=MUTED)

        robot = self.app.snapshot.get("robot")
        if robot is None or not robot.read_ok:
            self._comm_value.configure(text="UNKNOWN", fg=GRAY)
            for value, _warning in self._bit_values.values():
                value.configure(text="--", fg=GRAY)
            for value in self._value_labels.values():
                value.configure(text="--", fg=GRAY)
            return

        self._comm_value.configure(
            text="ONLINE" if robot.busy else "OFFLINE",
            fg=GREEN if robot.busy else GRAY,
        )

        for key, (value, warning) in self._bit_values.items():
            enabled = bool(getattr(robot, key))
            color = RED if enabled and warning else GREEN if enabled else GRAY
            value.configure(text="ON" if enabled else "OFF", fg=color)

        for key, value in self._value_labels.items():
            raw_value = getattr(robot, key)
            warning = key == "error_code" and raw_value not in (None, 0)
            value.configure(
                text="--" if raw_value is None else str(raw_value),
                fg=RED if warning else TEXT,
            )
