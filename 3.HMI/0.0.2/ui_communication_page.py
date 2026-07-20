import tkinter as tk
from ui_common import BasePage, PANEL, TEXT, MUTED, status_color


class CommunicationPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "通訊監控")
        body = tk.Frame(self, bg=PANEL, padx=35, pady=25); body.pack(fill="both", expand=True, padx=70, pady=20)
        self.labels = {}
        for row, name in enumerate(("PLC TCP", "HMI Heartbeat", "PLC Heartbeat Index", "HMI Return Index", "HMI_CommStatus", "Conveyor RTU", "Last read time", "Last write time", "Error code")):
            tk.Label(body, text=name, bg=PANEL, fg=MUTED, font=("Segoe UI", 13)).grid(row=row, column=0, sticky="w", pady=8)
            label = tk.Label(body, text="--", bg=PANEL, fg=TEXT, font=("Consolas", 14, "bold")); label.grid(row=row, column=1, sticky="w", padx=50)
            self.labels[name] = label

    def refresh(self):
        s = self.app.snapshot; plc = self.app.plc
        values = {"PLC TCP": "Online" if s["online"] else "Offline", "HMI Heartbeat": "Normal" if s["heartbeat_ok"] else "Alarm",
                  "PLC Heartbeat Index": s["plc_index"], "HMI Return Index": s["return_index"], "HMI_CommStatus": s["hmi_comm"],
                  "Conveyor RTU": "Online" if s["conveyor_rtu_online"] else "Offline",
                  "Last read time": _time(plc.last_read_time), "Last write time": _time(plc.last_write_time),
                  "Error code": plc.last_error or "0 / None"}
        for name, value in values.items(): self.labels[name].configure(text=str(value), fg=status_color(str(value)))


def _time(value): return value.strftime("%Y-%m-%d %H:%M:%S") if value else "--"
