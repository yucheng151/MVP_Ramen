"""PLC 與 IPC 之間的通訊狀態頁。"""
import tkinter as tk

from ui_common import BasePage, PANEL, TEXT, MUTED, status_color


class IPCCommunicationPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "PLC / IPC COMMUNICATION")
        body = tk.Frame(self, bg=PANEL, padx=35, pady=25)
        body.pack(fill="both", expand=True, padx=70, pady=20)
        self.labels = {}
        fields = (
            "PLC / IPC Link",
            "Connection Path",
            "Last Update",
            "Status Source",
            "Error",
        )
        for row, name in enumerate(fields):
            tk.Label(body, text=name, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 13)).grid(row=row, column=0, sticky="w", pady=12)
            label = tk.Label(body, text="--", bg=PANEL, fg=TEXT,
                             font=("Consolas", 14, "bold"))
            label.grid(row=row, column=1, sticky="w", padx=50)
            self.labels[name] = label

    def refresh(self):
        online = self.app.snapshot["ipc_online"]
        values = {
            "PLC / IPC Link": "Online" if online else "Offline",
            "Connection Path": "PLC ↔ IPC",
            "Last Update": "--",
            "Status Source": "PLC register not configured",
            "Error": "None" if online else "IPC status unavailable",
        }
        for name, value in values.items():
            self.labels[name].configure(text=value, fg=status_color(str(value)))
