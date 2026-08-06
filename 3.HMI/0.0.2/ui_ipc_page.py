"""PLC 與 IPC 之間的通訊狀態頁。"""
import tkinter as tk

from ui_common import BasePage, PANEL, TEXT, MUTED, GREEN, BLUE, status_color


class IPCCommunicationPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "PLC / IPC COMMUNICATION")
        body = tk.Frame(self, bg=PANEL, padx=35, pady=25)
        body.pack(fill="both", expand=True, padx=70, pady=20)
        self.labels = {}
        fields = (
            "IPC Link",
            "IPC Heartbeat",
            "IPC Status",
            "Last Result",
            "PLC Heartbeat Index (D1200)",
            "IPC Return Index (D1300)",
            "PLC IPC Comm Status (D1209.0)",
            "Connection Path",
            "Last read time",
            "Status Source",
            "Error code",
        )
        for row, name in enumerate(fields):
            tk.Label(body, text=name, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 13)).grid(row=row, column=0, sticky="w", pady=8)
            label = tk.Label(body, text="--", bg=PANEL, fg=TEXT,
                             font=("Consolas", 14, "bold"))
            label.grid(row=row, column=1, sticky="w", padx=50)
            self.labels[name] = label

        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.first_button = tk.Button(
            buttons, text="前三料", command=self.app.command.send_small_material_first,
            bg=GREEN, fg="white", activebackground=GREEN, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=6,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.first_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.last_button = tk.Button(
            buttons, text="後三料", command=self.app.command.send_small_material_last,
            bg=BLUE, fg="white", activebackground=BLUE, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=6,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.last_button.pack(side="left", expand=True, fill="x", padx=(5, 0))

    def refresh(self):
        snapshot = self.app.snapshot
        online = snapshot["ipc_online"]
        button_state = "normal" if online else "disabled"
        self.first_button.configure(state=button_state)
        self.last_button.configure(state=button_state)
        values = {
            "IPC Link": "Online" if online else "Offline",
            "IPC Heartbeat": "Normal" if online else "Alarm",
            "IPC Status": snapshot.get("ipc_execution_status", "Offline"),
            "Last Result": snapshot.get("ipc_last_result", "--"),
            "PLC Heartbeat Index (D1200)": snapshot.get("ipc_plc_index", "--"),
            "IPC Return Index (D1300)": snapshot.get("ipc_return_index", "--"),
            "PLC IPC Comm Status (D1209.0)": "Normal" if snapshot.get("ipc_plc_comm_normal") else "Alarm",
            "Connection Path": "PLC ↔ Small-Material IPC (HMI monitor only)",
            "Last read time": _time(self.app.plc.last_read_time),
            "Status Source": "Read-only: D1200 / D1300 / D1209",
            "Error code": "0 / None" if online else snapshot.get("ipc_status_message", "--"),
        }
        for name, value in values.items():
            self.labels[name].configure(text=str(value), fg=status_color(str(value)))


def _time(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "--"
