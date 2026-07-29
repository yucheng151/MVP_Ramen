"""MVP 拉麵機多頁式工業 HMI。"""
from __future__ import annotations

from datetime import datetime
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

from config import HEARTBEAT_INTERVAL, PLC_IP, RECONNECT_DELAY
from HMI_command import HMICommand
from HMI_heartbeat import HMIHeartbeat
from HMI_plc_client import HMIPlcClient
from HMI_status import HMIStatus
from mock_plc_client import MockHMIPlcClient
from register_map import CONVEYOR_TIMEOUT_WORD, FAULT_NAMES
from ui_common import BG
from ui_main_page import MainPage
from ui_alarm_page import AlarmPage
from ui_communication_page import CommunicationPage
from ui_ipc_page import IPCCommunicationPage
from ui_robot_page import RobotPage
from ui_conveyor_control_page import ConveyorControlPage

PLC_STARTUP_GRACE_SECONDS = 8.0


class HMIUI:
    def __init__(self, ip: str = PLC_IP, mock: bool = False) -> None:
        self.root = tk.Tk()
        self.root.title("MVP 拉麵機 HMI" + (" [MOCK]" if mock else ""))
        self.root.geometry("1366x768")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.mock_mode = mock

        self.plc = MockHMIPlcClient(ip="MOCK") if mock else HMIPlcClient(ip=ip)
        self.heartbeat = HMIHeartbeat(self.plc)
        self.command = HMICommand(self.plc)
        self.status = HMIStatus(self.plc)
        self.machine_mode = "Manual"  # 預留：未來改由 PLC 模式暫存器更新
        self.conveyor_run_requested: bool | None = None
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
        self.current_page = "MainPage"
        self.show_page(self.current_page)
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

    @staticmethod
    def _empty_snapshot():
        return {"online": False, "heartbeat_ok": False, "plc_index": "--", "return_index": "--",
                "hmi_comm": "--", "conveyor": [0] * 8, "parameters": [0] * 5,
                "conveyor_rtu_online": False, "conveyor_state": "Unknown", "system": "Starting",
                "conveyor_timeout_word": 0, "ack_index": "--", "response_code": "--",
                "ipc_online": False,
                "arm_online": None,
                "robot": None,
                "robot_manual": None,
                "bowl_dispenser_busy": False,
                "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                            "pause_point_2": False, "right_stop_point": False,
                            "bowl_dispenser_busy": False}}

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

    def toggle_mode(self) -> None:
        """切換尚未綁定 PLC 位址的暫存 Manual / Auto 模式。"""
        self.set_mode("Auto" if self.machine_mode == "Manual" else "Manual")

    def show_emergency_stop_unconfigured(self) -> None:
        """UI placeholder; no PLC command is sent until its mapping is confirmed."""
        messagebox.showwarning(
            "EMERGENCY STOP",
            "Emergency Stop PLC command is not configured yet.",
            parent=self.root,
        )

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
            conveyor = self.plc.read_d(100, 13)
            plc_status = self.status.read_status()
            timeout_data = self.plc.read_d(CONVEYOR_TIMEOUT_WORD, 1)
            if conveyor is None or timeout_data is None:
                if self._startup_grace_active():
                    self._publish_connecting()
                else:
                    self._publish_offline()
            else:
                fault_word = conveyor[0]
                timeout_word = timeout_data[0]
                comm_timeout = bool(timeout_word & 0x0001)
                initialize_timeout = bool(timeout_word & 0x0002)
                conveyor_rtu_online = not comm_timeout
                if not conveyor_rtu_online:
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
                if comm_timeout:
                    alarms.append("Conveyor Communication Timeout")
                if initialize_timeout:
                    alarms.append("Conveyor Initialize Timeout")
                if hb.ok and plc_status.ok:
                    self._startup_deadline = None
                startup_grace = self._startup_grace_active()
                if not hb.ok and not startup_grace:
                    alarms.append("PLC Communication Timeout")
                if not plc_status.ok and not startup_grace:
                    alarms.append("PLC Status Read Error")
                robot = plc_status.robot
                robot_manual = plc_status.robot_manual
                if robot_manual.read_ok and robot_manual.alarm_code:
                    alarms.append(f"Robot Manual Alarm Code: {robot_manual.alarm_code}")
                if (
                    robot_manual.read_ok
                    and robot_manual.result_code is not None
                    and 400 <= robot_manual.result_code <= 599
                ):
                    alarms.append(f"Robot Manual Result Code: {robot_manual.result_code}")
                self._update_alarms(alarms)
                self.snapshot = {
                    "online": True, "heartbeat_ok": hb.ok,
                    "plc_index": hb.plc_index, "return_index": hb.return_index,
                    "hmi_comm": hb.hmi_comm_status,
                    "conveyor": conveyor[:8], "parameters": conveyor[8:13],
                    "conveyor_rtu_online": conveyor_rtu_online,
                    "conveyor_timeout_word": timeout_word,
                    "conveyor_state": conveyor_state,
                    "ack_index": plc_status.ack_index if plc_status.ok else "--",
                    "response_code": plc_status.response_code if plc_status.ok else "--",
                    "ipc_online": self.snapshot.get("ipc_online", False),
                    # Display only. D12100.1 must not interlock CMD 40.
                    "arm_online": robot.status_output if robot.read_ok else None,
                    "robot": robot,
                    "robot_manual": plc_status.robot_manual,
                    "bowl_dispenser_busy": plc_status.sensors.bowl_dispenser_busy,
                    "sensors": {
                        "bowl_drop_confirm": plc_status.sensors.bowl_drop_confirm,
                        "pause_point_1": plc_status.sensors.pause_point_1,
                        "pause_point_2": plc_status.sensors.pause_point_2,
                        "right_stop_point": plc_status.sensors.right_stop_point,
                        "bowl_dispenser_busy": plc_status.sensors.bowl_dispenser_busy,
                    },
                    "system": "Alarm" if self.active_alarms else "Normal",
                }
            self._stop_event.wait(HEARTBEAT_INTERVAL)

    def _startup_grace_active(self) -> bool:
        return (
            self._startup_deadline is not None
            and time.monotonic() < self._startup_deadline
        )

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
            "conveyor_state": "Unknown",
            "system": "Starting",
        }

    def _publish_offline(self) -> None:
        old = self.snapshot
        self.snapshot = {**old, "online": False, "heartbeat_ok": False,
                         "conveyor_rtu_online": False,
                         "conveyor_timeout_word": 0,
                         "arm_online": None,
                         "robot": None,
                         "robot_manual": None,
                         "bowl_dispenser_busy": False,
                         "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                                     "pause_point_2": False, "right_stop_point": False,
                                     "bowl_dispenser_busy": False},
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
        page = self.pages[self.current_page]
        if hasattr(page, "update_global_status"):
            page.update_global_status()
        page.refresh()
        self.root.after(400, self._refresh_ui)

    def on_close(self) -> None:
        if self.plc.connected:
            self.command.send_conveyor_stop()
        self._stop_event.set()
        self._worker.join(timeout=2.0)
        self.plc.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
