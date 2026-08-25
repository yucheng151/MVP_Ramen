"""MVP 拉麵機多頁式工業 HMI。"""
from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from config import HEARTBEAT_INTERVAL, PLC_IP, PLC_PORT, RECONNECT_DELAY
from HMI_command import HMICommand
from HMI_heartbeat import HMIHeartbeat
from HMI_ipc_heartbeat import IPCHeartbeat
from HMI_plc_client import HMIPlcClient
from HMI_status import HMIStatus
from auto_live_monitor import AutoLiveMonitor
from auto_models import AutoHMIStore
from mock_plc_client import MockHMIPlcClient
from process_models import (
    PROCESS_ALARM, PROCESS_COMPLETE, PROCESS_IDLE, PROCESS_RUNNING,
    PROCESS_STEPS, ProcessAlarm, ProcessSnapshot, lock_recipe,
)
from simulation_control import SimulationController
from register_map import (
    CONVEYOR_SET_SPEED_WRITE,
    CONVEYOR_TIMEOUT_WORD,
    FAULT_NAMES,
    HMI_EMC_BIT,
    HMI_EMC_WORD,
    PLC_EMC_ACTIVE_BIT,
    PLC_EMC_STATUS_WORD,
    PLC_MACHINE_MODE,
    PLC_MAIN_PROCESS_STEP,
    MACHINE_MODE_MANUAL,
    MACHINE_MODE_SEMI_AUTO,
    MACHINE_MODE_AUTO,
)
from ui_common import BG
from ui_main_page import MainPage
from ui_alarm_page import AlarmPage
from ui_communication_page import CommunicationPage
from ui_ipc_page import IPCCommunicationPage
from ui_robot_page import RobotPage
from ui_auto_page import AutoSystemPage
from ui_conveyor_control_page import ConveyorControlPage

PLC_STARTUP_GRACE_SECONDS = 8.0
MODE_COMMAND_TIMEOUT_SECONDS = 8.0
MODE_VALUE_TO_TEXT = {
    MACHINE_MODE_MANUAL: "Manual",
    MACHINE_MODE_SEMI_AUTO: "Semi Auto",
    MACHINE_MODE_AUTO: "Auto",
}
MODE_TEXT_TO_VALUE = {text: value for value, text in MODE_VALUE_TO_TEXT.items()}
MODE_SUCCESS_RESPONSE = {
    MACHINE_MODE_MANUAL: 300,
    MACHINE_MODE_SEMI_AUTO: 301,
    MACHINE_MODE_AUTO: 302,
}
LOGGER = logging.getLogger(__name__)


class HMIUI:
    def __init__(
        self,
        ip: str = PLC_IP,
        port: int = PLC_PORT,
        mock: bool = False,
        start_page: str = "MainPage",
        runtime_profile: str = "simulation",
    ) -> None:
        if runtime_profile not in ("simulation", "field"):
            raise ValueError("runtime_profile must be 'simulation' or 'field'")
        if runtime_profile == "field" and mock:
            raise ValueError("FIELD現場版禁止使用Mock PLC")
        self.runtime_profile = runtime_profile
        self.simulation_profile = runtime_profile == "simulation"
        self.root = tk.Tk()
        edition = "SIMULATION" if self.simulation_profile else "FIELD"
        mock_suffix = " / MOCK" if mock else ""
        self.root.title(f"MVP 拉麵機 HMI v0.0.3 [{edition}{mock_suffix}]")
        self.root.geometry("1366x768")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.mock_mode = mock

        self.plc = MockHMIPlcClient(ip="MOCK") if mock else HMIPlcClient(ip=ip, port=port)
        self.heartbeat = HMIHeartbeat(self.plc)
        self.ipc_heartbeat = IPCHeartbeat(self.plc)
        self.command = HMICommand(self.plc)
        self.status = HMIStatus(self.plc)
        self.auto_live_monitor = AutoLiveMonitor(
            self.plc, allow_debug_fallback=self.simulation_profile,
        )
        self.simulation_controller = (
            SimulationController(self.plc) if self.simulation_profile and not mock
            else None
        )
        self.auto_store = AutoHMIStore(Path(__file__).resolve().parent / "data" / "auto_hmi_state.json")
        # The display mode is updated only from PLC D1109 after startup.
        self._last_valid_machine_mode = MACHINE_MODE_MANUAL
        self._last_valid_process_step = 0
        self._mode_step_direction = 1
        self._mode_lock = threading.RLock()
        self.mode_change_pending_index: int | None = None
        self.mode_change_target: int | None = None
        self._mode_change_started = 0.0
        self._mode_acknowledged = False
        self._mode_notice: tuple[str, str] | None = None
        self.machine_mode = "Manual"
        self._manual_action_lock = threading.RLock()
        self.manual_action_owner: str | None = None
        self._bowl_busy_seen = False
        self.conveyor_run_requested: bool | None = None
        self.hmi_emc_requested = False
        self.recipe_snapshot = None
        self.snapshot = self._empty_snapshot()
        self.active_alarms: dict[str, datetime] = {}
        self._alarm_started: dict[str, datetime] = {}
        self.alarm_history: dict[str, dict] = {}
        self._current_alarm_names: set[str] = set()
        self._reset_clear_authorized: set[str] = set()
        self._startup_deadline = time.monotonic() + PLC_STARTUP_GRACE_SECONDS
        self._responsive_fonts = {}
        self._font_resize_job = None
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._poll_loop, name="hmi-poll", daemon=True)

        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for page_class in (
            MainPage,
            AutoSystemPage,
            ConveyorControlPage,
            AlarmPage,
            CommunicationPage,
            IPCCommunicationPage,
            RobotPage,
        ):
            page = page_class(container, self)
            self.pages[page_class.__name__] = page
            page.grid(row=0, column=0, sticky="nsew")

        self._capture_responsive_fonts(container)
        self.root.bind("<Configure>", self._schedule_font_resize, add="+")
        self.current_page = (
            start_page if start_page in self.pages else "MainPage"
        )
        self.show_page(self.current_page)
        # Raise the requested page again after Tk has completed initial layout;
        # this avoids a later-created frame covering the selected start page.
        self.root.after_idle(
            lambda page_name=self.current_page: self.show_page(page_name)
        )
        self._worker.start()
        self.root.after(200, self._refresh_ui)

    def _capture_responsive_fonts(self, parent) -> None:
        """Remember each widget's designed font so resizing never compounds."""
        try:
            font_name = parent.cget("font")
            if font_name:
                actual = tkfont.Font(root=self.root, font=font_name).actual()
                size = abs(int(actual.get("size", 0)))
                if size:
                    self._responsive_fonts[str(parent)] = (
                        parent,
                        actual["family"],
                        size,
                        actual["weight"],
                        actual["slant"],
                        actual["underline"],
                        actual["overstrike"],
                    )
        except (tk.TclError, KeyError, ValueError):
            pass
        for child in parent.winfo_children():
            self._capture_responsive_fonts(child)

    def _schedule_font_resize(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._font_resize_job is not None:
            self.root.after_cancel(self._font_resize_job)
        self._font_resize_job = self.root.after(120, self._apply_responsive_fonts)

    def _apply_responsive_fonts(self) -> None:
        self._font_resize_job = None
        width = max(self.root.winfo_width(), 1)
        height = max(self.root.winfo_height(), 1)
        window_ratio = min(width / 1366, height / 768)
        scale = (
            max(0.78, window_ratio)
            if window_ratio <= 1.0
            else min(1.9, 1.0 + ((window_ratio - 1.0) * 1.8))
        )
        for key, font_data in list(self._responsive_fonts.items()):
            widget, family, base_size, weight, slant, underline, overstrike = font_data
            try:
                if not widget.winfo_exists():
                    self._responsive_fonts.pop(key, None)
                    continue
                widget.configure(font=(
                    family,
                    max(7, round(base_size * scale)),
                    weight,
                    slant,
                ))
            except tk.TclError:
                continue

    def _empty_snapshot(self):
        return {"online": False, "heartbeat_ok": False, "plc_index": "--", "return_index": "--",
                "runtime_profile": self.runtime_profile,
                "external_devices_bypassed": self.simulation_profile,
                "hmi_comm": "--", "conveyor": [0] * 8, "parameters": [0] * 5,
                "conveyor_rtu_online": False, "conveyor_state": "Unknown", "system": "Starting",
                "conveyor_timeout_word": 0, "ack_index": "--", "response_code": "--",
                "machine_mode": MACHINE_MODE_MANUAL, "machine_mode_error": "",
                "process": ProcessSnapshot(),
                "ipc_online": False,
                "ipc_plc_index": None,
                "ipc_return_index": None,
                "ipc_plc_comm_normal": False,
                "ipc_status_word": None,
                "ipc_status_message": "--",
                "ipc_execution_status": "Offline",
                "ipc_last_result": "--",
                "plc_emc_active": False,
                "hmi_emc_requested": False,
                "alarm_condition_active": False,
                "arm_online": None,
                "robot": None,
                "robot_manual": None,
                "auto_live": None,
                "bowl_dispenser_busy": False,
                "semi_auto_running": False,
                "sensor_status_word": 0,
                "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                            "pause_point_2": False, "right_stop_point": False,
                            "bowl_dispenser_busy": False,
                            "semi_auto_running": False}}

    def show_page(self, name: str) -> None:
        # Keep the outer window exactly the same size while pages with different
        # requested content dimensions are raised.
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        geometry = (
            f"{width}x{height}+{x}+{y}"
            if self.root.state() == "normal" and width > 1 and height > 1
            else None
        )
        self.current_page = name
        self.pages[name].tkraise()
        self.pages[name].refresh()
        if geometry is not None:
            self.root.geometry(geometry)
            self.root.after_idle(lambda value=geometry: self.root.geometry(value))

    def toggle_page(self, name: str) -> None:
        """第一次開啟指定頁面，再按同一入口時返回首頁。"""
        self.show_page("MainPage" if self.current_page == name else name)

    def show_conveyor_tab(self, tab_name: str) -> None:
        page = self.pages["ConveyorControlPage"]
        self.current_page = "ConveyorControlPage"
        page.tkraise()
        page.select_tab(tab_name)

    def set_mode(self, mode: str) -> None:
        """暫存操作模式；未來 PLC 提供模式位址後由輪詢值取代。"""
        self.machine_mode = mode
        if mode == "Auto":
            self.conveyor_run_requested = None
        self.pages[self.current_page].refresh()

    def set_conveyor_run_requested(self, running: bool) -> None:
        """記錄最後一次手動 Run/Stop，避免 PLC 速度舊值造成主頁狀態延遲。"""
        self.conveyor_run_requested = running
        if (self.snapshot["online"]
                and not (self.snapshot["conveyor"][0] & 0x1FF)
                and not self.snapshot["conveyor_timeout_word"]):
            if running:
                state = "Running"
            else:
                state = "Stopping" if self.snapshot["conveyor"][1] > 0 else "Ready"
            self.snapshot = {**self.snapshot, "conveyor_state": state}

    def begin_manual_action(self, owner: str) -> bool:
        """Acquire the one-at-a-time machine manual action interlock."""
        with self._manual_action_lock:
            if self.manual_action_owner is not None:
                return False
            self.manual_action_owner = owner
            if owner == "Bowl":
                self._bowl_busy_seen = False
            return True

    def finish_manual_action(self, owner: str) -> None:
        with self._manual_action_lock:
            if self.manual_action_owner == owner:
                self.manual_action_owner = None
                if owner == "Bowl":
                    self._bowl_busy_seen = False

    def manual_action_available(self, owner: str | None = None) -> bool:
        with self._manual_action_lock:
            action_available = self.manual_action_owner in (None, owner)
        with self._mode_lock:
            return action_available and self.mode_change_pending_index is None

    def manual_action_reason(self, owner: str) -> str:
        with self._mode_lock:
            if self.mode_change_pending_index is not None:
                return "Machine mode change is in progress"
        with self._manual_action_lock:
            active = self.manual_action_owner
        if active is None or active == owner:
            return ""
        names = {
            "Conveyor": "Conveyor manual action is not complete",
            "Robot": "Robot manual action is not complete",
            "Bowl": "Bowl dispense action is not complete",
        }
        return names.get(active, f"{active} manual action is not complete")

    def _update_manual_action_completion(self, snapshot: dict) -> None:
        """Release non-Robot actions only after their PLC feedback completes."""
        with self._manual_action_lock:
            owner = self.manual_action_owner
            if owner == "Conveyor":
                if self.conveyor_run_requested is False and snapshot["conveyor"][1] == 0:
                    self.manual_action_owner = None
            elif owner == "Bowl":
                busy = bool(snapshot.get("bowl_dispenser_busy", False))
                if busy:
                    self._bowl_busy_seen = True
                elif self._bowl_busy_seen:
                    self.manual_action_owner = None
                    self._bowl_busy_seen = False

    def toggle_mode(self) -> None:
        """Move the UI-only three-position selector back and forth."""
        self.set_mode("Auto" if self.machine_mode == "Manual" else "Manual")

    def set_mode(self, mode: str) -> None:
        value = MODE_TEXT_TO_VALUE.get(mode)
        if value is not None:
            self.request_machine_mode(value)

    def request_machine_mode(self, mode: int) -> bool:
        """Start one D1000~D1002 mode handshake and lock the selector."""
        if mode not in MODE_VALUE_TO_TEXT:
            return False
        with self._mode_lock:
            if self.mode_change_pending_index is not None:
                return False
            if not self.snapshot.get("online", False) or not self.plc.connected:
                self._mode_notice = ("error", "PLC 通訊中斷，無法切換模式")
                return False
            # D1110.5 is the sole PLC condition allowed to block a mode
            # change during Semi-Auto. Main Step, alarms and other PLC bits
            # are display-only for this decision.
            if self.snapshot.get("semi_auto_running", False):
                self._mode_notice = (
                    "warning", "Semi-Auto is running (D1110.5 ON).",
                )
                return False
            if mode == self._last_valid_machine_mode:
                return True
            result = self.command.send_machine_mode(mode)
            if not result.ok:
                self._mode_notice = ("error", result.message or "模式切換命令送出失敗")
                return False
            self.mode_change_pending_index = result.command_index
            self.mode_change_target = mode
            self._mode_change_started = time.monotonic()
            self._mode_acknowledged = False
            return True

    def start_auto_process(self, recipe: dict) -> tuple[bool, str]:
        """Start Mock auto flow; real PLC remains blocked until mapping is assigned."""
        process = self.snapshot.get("process")
        if self.machine_mode != "Auto":
            return False, "Please switch to AUTO mode"
        if self.active_alarms or (process and process.status == PROCESS_ALARM):
            return False, "Active alarm must be reset before automatic start"
        if process and process.status == PROCESS_RUNNING:
            return False, "A process is already running"
        self.recipe_snapshot = lock_recipe(recipe)
        if not self.mock_mode:
            return False, "PLC register mapping is not assigned; no command was written"
        return self.plc.start_auto_process(self.recipe_snapshot)

    def write_auto_parameters(self, recipe: dict) -> tuple[bool, str]:
        """Write the assigned Auto parameter registers without starting production."""
        if self.machine_mode != "Auto":
            return False, "Please switch to AUTO mode"
        process = self.snapshot.get("process")
        if self.active_alarms or (process and process.status == PROCESS_ALARM):
            return False, "Active alarm must be reset before writing parameters"
        if process and process.status == PROCESS_RUNNING:
            return False, "Cannot change parameters while a process is running"
        try:
            conveyor_speed = int(recipe["conveyor_speed_rpm"])
            cook_time = int(recipe["cook_time_sec"])
        except (KeyError, TypeError, ValueError):
            return False, "Parameters must be valid integers"
        if conveyor_speed <= 0 or cook_time <= 0:
            return False, "Conveyor Speed and Cook Time must be greater than 0"

        if self.mock_mode:
            ok, message = self.plc.write_auto_parameters(recipe)
        else:
            ok = self.command.write_d(CONVEYOR_SET_SPEED_WRITE, conveyor_speed)
            message = (
                f"Conveyor Speed {conveyor_speed} RPM written to D108. "
                "Cook Time is HMI-only until PLC assigns its register."
                if ok else "Failed to write Conveyor Speed to D108"
            )
        if ok:
            self.recipe_snapshot = lock_recipe(recipe)
        return ok, message

    def toggle_mode(self) -> None:
        """Request the next selector position through the PLC."""
        with self._mode_lock:
            if self.mode_change_pending_index is not None:
                return
        modes = ("Manual", "Semi Auto", "Auto")
        current = modes.index(self.machine_mode) if self.machine_mode in modes else 0
        if current == 0:
            self._mode_step_direction = 1
        elif current == len(modes) - 1:
            self._mode_step_direction = -1
        self.request_machine_mode(
            MODE_TEXT_TO_VALUE[modes[current + self._mode_step_direction]]
        )

    def _finish_mode_change(self, notice: tuple[str, str] | None = None) -> None:
        self.command.clear_machine_mode_command()
        self.mode_change_pending_index = None
        self.mode_change_target = None
        self._mode_change_started = 0.0
        self._mode_acknowledged = False
        if notice is not None:
            self._mode_notice = notice

    def _update_machine_mode(self, raw_mode: int) -> str:
        if raw_mode in MODE_VALUE_TO_TEXT:
            # A matched mode ACK/response is authoritative on the current PLC
            # build because D1109 is not following Machine_Mode yet.  Keep the
            # last PLC-confirmed command result instead of immediately being
            # pulled back by stale D1109 data.
            if self.mode_change_pending_index is None:
                return ""
            return ""
        error = f"Invalid PLC Machine_Mode D1109 value: {raw_mode}"
        LOGGER.warning(error)
        return error

    def _handle_mode_reply(self, ack_index, response_code) -> None:
        with self._mode_lock:
            pending = self.mode_change_pending_index
            target = self.mode_change_target
            if pending is None or target is None:
                return

            if ack_index == pending:
                if response_code == 430:
                    self._finish_mode_change((
                        "warning", "機台運轉中或安全條件不符，無法切換模式",
                    ))
                    return
                if response_code == MODE_SUCCESS_RESPONSE[target]:
                    self._last_valid_machine_mode = target
                    self.machine_mode = MODE_VALUE_TO_TEXT[target]
                    if target != MACHINE_MODE_MANUAL:
                        self.conveyor_run_requested = None
                    self._finish_mode_change()
                    return
                elif response_code not in (None, 0):
                    self._finish_mode_change((
                        "error", f"模式切換失敗（Response {response_code}）",
                    ))
                    return
            if time.monotonic() - self._mode_change_started >= MODE_COMMAND_TIMEOUT_SECONDS:
                self._finish_mode_change(("error", "模式切換逾時，已恢復 PLC 實際模式"))

    def set_hmi_emc(self, active: bool) -> bool:
        """Write the HMI IPC emergency-stop request to D1004.0."""
        if not self.plc.connected or not self.snapshot.get("online", False):
            return False
        value = (1 << HMI_EMC_BIT) if active else 0
        if not self.command.write_d(HMI_EMC_WORD, value):
            return False
        self.hmi_emc_requested = bool(active)
        self.snapshot = {
            **self.snapshot,
            "hmi_emc_requested": self.hmi_emc_requested,
        }
        return True

    def toggle_mock_alarm(self) -> None:
        """Mock 模式切換 D100.0，展示 Normal/Alarm 視覺效果。"""
        if not self.mock_mode:
            return
        with self.plc.lock:
            current = self.plc.registers.get(100, 0)
            self.plc.registers[100] = current ^ 0x0001

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self.plc.connected and not self.plc.connect():
                if self._startup_grace_active():
                    self._publish_connecting()
                else:
                    self._publish_offline()
                self._stop_event.wait(RECONNECT_DELAY)
                continue

            hb = self.heartbeat.tick()
            ipc_hb = self.ipc_heartbeat.tick()
            conveyor = self.plc.read_d(100, 13)
            plc_status = self.status.read_status()
            timeout_data = self.plc.read_d(CONVEYOR_TIMEOUT_WORD, 1)
            emc_data = self.plc.read_d(PLC_EMC_STATUS_WORD, 1)
            mode_data = self.plc.read_d(PLC_MACHINE_MODE, 1)
            process_step_data = (
                [0] if self.mock_mode else self.plc.read_d(PLC_MAIN_PROCESS_STEP, 1)
            )
            auto_live = (
                None if self.mock_mode else self.auto_live_monitor.read_snapshot()
            )
            if (conveyor is None or timeout_data is None or emc_data is None
                    or mode_data is None
                    or process_step_data is None):
                if self._startup_grace_active():
                    self._publish_connecting()
                else:
                    self._publish_offline()
            else:
                machine_mode_error = self._update_machine_mode(mode_data[0])
                self._handle_mode_reply(
                    plc_status.ack_index if plc_status.ok else None,
                    plc_status.response_code if plc_status.ok else None,
                )
                raw_fault_word = conveyor[0]
                timeout_word = timeout_data[0]
                plc_emc_active = bool(emc_data[0] & (1 << PLC_EMC_ACTIVE_BIT))
                # SIMULATION版只驗證PLC流程。沒有接上的輸送帶、IPC與
                # 三支手臂一律旁路，不把實體設備斷線誤判成流程失敗。
                fault_word = 0 if self.simulation_profile else raw_fault_word
                comm_timeout = (
                    False if self.simulation_profile
                    else bool(timeout_word & 0x0001)
                )
                initialize_timeout = (
                    False if self.simulation_profile
                    else bool(timeout_word & 0x0002)
                )
                conveyor_rtu_online = not comm_timeout
                if self.simulation_profile:
                    conveyor_state = "SIMULATION PASS"
                elif not conveyor_rtu_online:
                    conveyor_state = "Driver Offline"
                elif initialize_timeout or fault_word & 0x1FF:
                    conveyor_state = "Alarm"
                elif self.conveyor_run_requested is True:
                    conveyor_state = "Running"
                elif conveyor[1] > 0:
                    conveyor_state = (
                        "Stopping"
                        if self.conveyor_run_requested is False
                        else "Running"
                    )
                else:
                    conveyor_state = "Ready"
                alarms = [FAULT_NAMES[bit] for bit in range(9) if fault_word & (1 << bit)]
                process = (
                    self.plc.get_process_snapshot()
                    if self.mock_mode
                    else self.snapshot.get("process", ProcessSnapshot())
                )
                if not self.mock_mode:
                    raw_step = process_step_data[0]
                    valid_steps = {step for step, _name in PROCESS_STEPS}
                    if raw_step in valid_steps:
                        self._last_valid_process_step = raw_step
                    process.step = self._last_valid_process_step
                    process.mapping_ready = True
                    if process.step == 0:
                        process.status = PROCESS_IDLE
                    elif process.step == 90:
                        process.status = PROCESS_COMPLETE
                    else:
                        process.status = PROCESS_RUNNING
                process.mode = self._last_valid_machine_mode
                # Mock owns a native process alarm. On a real PLC the process
                # alarm below is derived from active alarms, so feeding it back
                # here would recursively create "Process ... Process ..." text.
                if self.mock_mode and process.alarm.latched:
                    alarms.append(
                        f"Process {process.alarm.source}: {process.alarm.message} "
                        f"(Code {process.alarm.code})"
                    )
                if comm_timeout:
                    alarms.append("Conveyor Communication Timeout")
                if initialize_timeout:
                    alarms.append("Conveyor Initialize Timeout")
                if plc_emc_active:
                    alarms.append("PLC Emergency Stop")
                if hb.ok and plc_status.ok:
                    self._startup_deadline = None
                startup_grace = self._startup_grace_active()
                if not hb.ok and not startup_grace:
                    alarms.append("PLC Communication Timeout")
                if not plc_status.ok and not startup_grace:
                    alarms.append("PLC Status Read Error")
                if (not self.simulation_profile and not ipc_hb.ok
                        and not startup_grace):
                    alarms.append("IPC Communication Timeout")
                robot = plc_status.robot
                robot_manual = plc_status.robot_manual
                # D12100/D12102 are display/alarm sources only; they never
                # interlock or decide whether CMD 40 may be sent.
                if not self.simulation_profile and robot.read_ok:
                    if robot.error_signal:
                        alarms.append("Robot Error Signal")
                    if robot.alarm_signal:
                        alarms.append("Robot Alarm Signal")
                    if robot.estop_active:
                        alarms.append("Robot Emergency Stop")
                    if robot.error_code not in (None, 0):
                        alarms.append(f"Robot Error Code: {robot.error_code}")
                if (not self.simulation_profile and robot_manual.read_ok
                        and robot_manual.alarm_code):
                    alarms.append(f"Robot Manual Alarm Code: {robot_manual.alarm_code}")
                if (
                    not self.simulation_profile
                    and robot_manual.read_ok
                    and robot_manual.result_code is not None
                    and 400 <= robot_manual.result_code <= 599
                ):
                    alarms.append(f"Robot Manual Result Code: {robot_manual.result_code}")
                self._update_alarms(alarms)
                if not self.mock_mode:
                    if self.active_alarms:
                        alarm_name, occurred_at = next(iter(self.active_alarms.items()))
                        source = self._alarm_source(alarm_name)
                        process.status = PROCESS_ALARM
                        process.alarm = ProcessAlarm(
                            step=process.step, source=source, message=alarm_name,
                            code=0, suggestion="Clear the device condition, then press ALM RST",
                            occurred_at=occurred_at, latched=True,
                        )
                    elif process.alarm.latched:
                        process.alarm = ProcessAlarm()
                        process.status = PROCESS_IDLE
                self.snapshot = {
                    "online": True, "heartbeat_ok": hb.ok,
                    "runtime_profile": self.runtime_profile,
                    "external_devices_bypassed": self.simulation_profile,
                    "plc_index": hb.plc_index, "return_index": hb.return_index,
                    "hmi_comm": hb.hmi_comm_status,
                    "conveyor": [fault_word, *conveyor[1:8]],
                    "parameters": conveyor[8:13],
                    "conveyor_rtu_online": conveyor_rtu_online,
                    "conveyor_timeout_word": (
                        0 if self.simulation_profile else timeout_word
                    ),
                    "conveyor_state": conveyor_state,
                    "ack_index": plc_status.ack_index if plc_status.ok else "--",
                    "response_code": plc_status.response_code if plc_status.ok else "--",
                    "machine_mode": self._last_valid_machine_mode,
                    "machine_mode_error": machine_mode_error,
                    "process": process,
                    "ipc_online": True if self.simulation_profile else ipc_hb.ok,
                    "ipc_plc_index": ipc_hb.plc_index,
                    "ipc_return_index": ipc_hb.return_index,
                    "ipc_plc_comm_normal": (
                        True if self.simulation_profile else ipc_hb.plc_comm_normal
                    ),
                    "ipc_status_word": ipc_hb.status_word,
                    "ipc_status_message": (
                        "SIMULATION PASS（外部IPC連線已旁路）"
                        if self.simulation_profile else ipc_hb.message
                    ),
                    "ipc_execution_status": (
                        "Simulation Pass"
                        if self.simulation_profile else ipc_hb.execution_status
                    ),
                    "ipc_last_result": ipc_hb.last_result,
                    "plc_emc_active": plc_emc_active,
                    "hmi_emc_requested": self.hmi_emc_requested,
                    # Current PLC/device conditions are separate from the HMI
                    # alarm history latch that remains until CMD 6.
                    "alarm_condition_active": bool(alarms),
                    # D12100.0 is the approved Robot Online interlock/display.
                    "arm_online": (
                        True if self.simulation_profile
                        else (robot.busy if robot.read_ok else None)
                    ),
                    "robot": robot,
                    "robot_manual": plc_status.robot_manual,
                    "auto_live": auto_live,
                    "bowl_dispenser_busy": plc_status.sensors.bowl_dispenser_busy,
                    "semi_auto_running": plc_status.sensors.semi_auto_running,
                    "sensor_status_word": plc_status.sensors.raw_word,
                    "sensors": {
                        "bowl_drop_confirm": plc_status.sensors.bowl_drop_confirm,
                        "pause_point_1": plc_status.sensors.pause_point_1,
                        "pause_point_2": plc_status.sensors.pause_point_2,
                        "right_stop_point": plc_status.sensors.right_stop_point,
                        "bowl_dispenser_busy": plc_status.sensors.bowl_dispenser_busy,
                        "semi_auto_running": plc_status.sensors.semi_auto_running,
                    },
                    "system": "Alarm" if self.active_alarms else "Normal",
                }
                self._update_manual_action_completion(self.snapshot)
            self._stop_event.wait(HEARTBEAT_INTERVAL)

    def _startup_grace_active(self) -> bool:
        return (
            self._startup_deadline is not None
            and time.monotonic() < self._startup_deadline
        )

    @staticmethod
    def _alarm_source(name: str) -> str:
        text = name.lower()
        if "emergency" in text or "emc" in text:
            return "EMC"
        if "conveyor" in text or any(item.lower() in text for item in FAULT_NAMES):
            return "Conveyor"
        if "robot" in text:
            return "Nashi Robot"
        if "ipc" in text:
            return "Robot IPC Communication"
        if "communication" in text or "plc" in text:
            return "HMI Communication"
        return "Machine"

    def _publish_connecting(self) -> None:
        """Show startup connection progress without creating a latched alarm."""
        old = self.snapshot
        self.snapshot = {
            **old,
            "online": False,
            "heartbeat_ok": False,
            "conveyor_rtu_online": False,
            "arm_online": None,
            "robot": None,
            "robot_manual": None,
            "auto_live": None,
            "plc_emc_active": False,
            "hmi_emc_requested": self.hmi_emc_requested,
            "alarm_condition_active": False,
            "conveyor_state": "Unknown",
            "system": "Starting",
        }

    def _publish_offline(self) -> None:
        with self._mode_lock:
            if self.mode_change_pending_index is not None:
                self.mode_change_pending_index = None
                self.mode_change_target = None
                self._mode_acknowledged = False
                self._mode_notice = ("error", "PLC 通訊中斷，模式未切換")
        old = self.snapshot
        self.snapshot = {**old, "online": False, "heartbeat_ok": False,
                         "conveyor_rtu_online": False,
                         "conveyor_timeout_word": 0,
                         "arm_online": None,
                         "robot": None,
                         "robot_manual": None,
                         "auto_live": None,
                         "plc_emc_active": False,
                         "hmi_emc_requested": self.hmi_emc_requested,
                         "alarm_condition_active": True,
                         "bowl_dispenser_busy": False,
                         "semi_auto_running": False,
                         "sensor_status_word": 0,
                         "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                                     "pause_point_2": False, "right_stop_point": False,
                                     "bowl_dispenser_busy": False,
                                     "semi_auto_running": False},
                         "conveyor_state": "Unknown", "system": "Alarm"}
        self._update_alarms(["PLC Communication Timeout", "Conveyor Driver Offline"])

    def _update_alarms(self, names: list[str]) -> None:
        now = datetime.now()
        active = set(names)
        self._current_alarm_names = active
        for name in names:
            record = self.alarm_history.setdefault(name, {"time": now, "active": True, "recovered": None})
            if not record["active"]:
                record["time"] = now
            self._alarm_started.setdefault(name, now)
            record["active"] = True
            record["recovered"] = None
            record["condition_active"] = True

        for name, record in self.alarm_history.items():
            record["condition_active"] = name in active

        # Alarm conditions never clear their own HMI latch. Only a successful
        # CMD 6 authorizes the alarms that existed at that moment to clear.
        for name in tuple(self._reset_clear_authorized):
            if name not in active:
                record = self.alarm_history.get(name)
                if record is not None and record["active"]:
                    record["active"] = False
                    record["recovered"] = now
                self._alarm_started.pop(name, None)
                self._reset_clear_authorized.discard(name)

        self.active_alarms = {
            name: self._alarm_started[name]
            for name, record in self.alarm_history.items()
            if record["active"] and name in self._alarm_started
        }

    def send_alarm_reset(self):
        """Send CMD 6 and authorize only currently latched alarms to clear."""
        result = self.command.send_alarm_reset()
        if result.ok:
            self._reset_clear_authorized.update(self.active_alarms)
            # Immediately clear alarms whose source condition already recovered.
            self._update_alarms(list(self._current_alarm_names))
            self.snapshot = {
                **self.snapshot,
                "system": "Alarm" if self.active_alarms else "Normal",
            }
        return result

    def _refresh_ui(self) -> None:
        if self._stop_event.is_set():
            return
        try:
            page = self.pages[self.current_page]
            # Refresh the shared header/navigation and the visible page from the
            # same latest PLC snapshot on every UI cycle.
            if hasattr(page, "update_global_status"):
                page.update_global_status()
            page.refresh()
            if getattr(self, "_last_ui_refresh_error", None) is not None:
                LOGGER.info("UI refresh recovered on %s", self.current_page)
                self._last_ui_refresh_error = None
        except Exception as exc:
            # A widget/page error must never kill Tk's repeating refresh loop.
            # Log only when the error changes to avoid flooding hmi.log.
            error_key = (self.current_page, type(exc).__name__, str(exc))
            if getattr(self, "_last_ui_refresh_error", None) != error_key:
                LOGGER.exception("UI refresh failed on %s", self.current_page)
                self._last_ui_refresh_error = error_key

        try:
            with self._mode_lock:
                notice = self._mode_notice
                self._mode_notice = None
            if notice is not None:
                level, text = notice
                if level == "warning":
                    messagebox.showwarning("MODE", text, parent=self.root)
                else:
                    messagebox.showerror("MODE", text, parent=self.root)
        finally:
            # Always schedule the next cycle, including after a page exception.
            if not self._stop_event.is_set():
                self.root.after(400, self._refresh_ui)

    def on_close(self) -> None:
        if self.simulation_controller is not None:
            self.simulation_controller.close()
        if self.plc.connected:
            self.command.send_conveyor_stop()
        self._stop_event.set()
        self._worker.join(timeout=2.0)
        self.plc.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
