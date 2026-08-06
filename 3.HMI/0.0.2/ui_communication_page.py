import tkinter as tk
from ui_common import BasePage, PANEL, TEXT, MUTED, status_color


class CommunicationPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "PLC / HMI COMMUNICATION")
        body = tk.Frame(self, bg=PANEL, padx=35, pady=25); body.pack(fill="both", expand=True, padx=70, pady=20)
        self.labels = {}
        for row, name in enumerate((
            "PLC / HMI Link",
            "HMI Heartbeat",
            "PLC Heartbeat Index (D1100)",
            "HMI Return Index (D1005)",
            "PLC HMI Comm Status (D1105)",
            "Conveyor RTU Timeout (D1107.0)",
            "Last read time",
            "Last write time",
            "Error code",
        )):
            tk.Label(body, text=name, bg=PANEL, fg=MUTED, font=("Segoe UI", 13)).grid(row=row, column=0, sticky="w", pady=8)
            label = tk.Label(body, text="--", bg=PANEL, fg=TEXT, font=("Consolas", 14, "bold")); label.grid(row=row, column=1, sticky="w", padx=50)
            self.labels[name] = label

    def refresh(self):
        s = self.app.snapshot; plc = self.app.plc
        values = {"PLC / HMI Link": "Online" if s["online"] else "Offline", "HMI Heartbeat": "Normal" if s["heartbeat_ok"] else "Alarm",
                  "PLC Heartbeat Index (D1100)": s["plc_index"], "HMI Return Index (D1005)": s["return_index"],
                  "PLC HMI Comm Status (D1105)": s["hmi_comm"],
                  "Conveyor RTU Timeout (D1107.0)": "Normal" if s["conveyor_rtu_online"] else "Alarm",
                  "Last read time": _time(plc.last_read_time), "Last write time": _time(plc.last_write_time),
                  "Error code": plc.last_error or "0 / None"}
        for name, value in values.items(): self.labels[name].configure(text=str(value), fg=status_color(str(value)))


def _time(value): return value.strftime("%Y-%m-%d %H:%M:%S") if value else "--"
