"""MVP 拉麵機多頁式工業 HMI。"""
from __future__ import annotations

from datetime import datetime
import threading
import tkinter as tk

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
from ui_conveyor_control_page import ConveyorControlPage


class HMIUI:
    def __init__(self, ip: str = PLC_IP, mock: bool = False) -> None:
        self.root = tk.Tk()
        self.root.title("MVP 拉麵機 HMI" + (" [MOCK]" if mock else ""))
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
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
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._poll_loop, name="hmi-poll", daemon=True)

        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for page_class in (MainPage, ConveyorControlPage, AlarmPage, CommunicationPage):
            page = page_class(container, self)
            self.pages[page_class.__name__] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.current_page = "MainPage"
        self.show_page(self.current_page)
        self._worker.start()
        self.root.after(200, self._refresh_ui)

    @staticmethod
    def _empty_snapshot():
        return {"online": False, "heartbeat_ok": False, "plc_index": "--", "return_index": "--",
                "hmi_comm": "--", "conveyor": [0] * 8, "parameters": [0] * 5,
                "conveyor_rtu_online": False, "conveyor_state": "Unknown", "system": "Alarm",
                "conveyor_timeout_word": 0, "ack_index": "--", "response_code": "--",
                "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                            "pause_point_2": False, "right_stop_point": False}}

    def show_page(self, name: str) -> None:
        self.current_page = name
        self.pages[name].tkraise()
        self.pages[name].refresh()

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
            self.snapshot = {**self.snapshot, "conveyor_state": "Running" if running else "Ready"}

    def toggle_mode(self) -> None:
        """切換尚未綁定 PLC 位址的暫存 Manual / Auto 模式。"""
        self.set_mode("Auto" if self.machine_mode == "Manual" else "Manual")

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
                self._publish_offline()
                self._stop_event.wait(RECONNECT_DELAY)
                continue

            hb = self.heartbeat.tick()
            conveyor = self.plc.read_d(100, 13)
            plc_status = self.status.read_status()
            timeout_data = self.plc.read_d(CONVEYOR_TIMEOUT_WORD, 1)
            if conveyor is None or timeout_data is None:
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
                elif self.conveyor_run_requested is False:
                    conveyor_state = "Ready"
                elif conveyor[1] > 0:
                    conveyor_state = "Running"
                else:
                    conveyor_state = "Ready"
                alarms = [FAULT_NAMES[bit] for bit in range(9) if fault_word & (1 << bit)]
                if comm_timeout:
                    alarms.append("Conveyor Communication Timeout")
                if initialize_timeout:
                    alarms.append("Conveyor Initialize Timeout")
                if not hb.ok:
                    alarms.append("PLC Communication Timeout")
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
                    "sensors": {
                        "bowl_drop_confirm": plc_status.sensors.bowl_drop_confirm,
                        "pause_point_1": plc_status.sensors.pause_point_1,
                        "pause_point_2": plc_status.sensors.pause_point_2,
                        "right_stop_point": plc_status.sensors.right_stop_point,
                    },
                    "system": "Alarm" if alarms or not plc_status.ok else "Normal",
                }
            self._stop_event.wait(HEARTBEAT_INTERVAL)

    def _publish_offline(self) -> None:
        old = self.snapshot
        self.snapshot = {**old, "online": False, "heartbeat_ok": False,
                         "conveyor_rtu_online": False,
                         "conveyor_timeout_word": 0,
                         "sensors": {"bowl_drop_confirm": False, "pause_point_1": False,
                                     "pause_point_2": False, "right_stop_point": False},
                         "conveyor_state": "Unknown", "system": "Alarm"}
        self._update_alarms(["PLC Communication Timeout", "Conveyor Driver Offline"])

    def _update_alarms(self, names: list[str]) -> None:
        now = datetime.now()
        active = set(names)
        for name in names:
            self._alarm_started.setdefault(name, now)
            record = self.alarm_history.setdefault(name, {"time": now, "active": True, "recovered": None})
            record["active"] = True
            record["recovered"] = None
        for name, record in self.alarm_history.items():
            if name not in active and record["active"]:
                record["active"] = False
                record["recovered"] = now
        self.active_alarms = {name: self._alarm_started[name] for name in names}

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
