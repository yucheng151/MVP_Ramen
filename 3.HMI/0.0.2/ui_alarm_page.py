import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from register_map import FAULT_NAMES
from ui_common import BasePage, PANEL, TEXT, RED, GREEN, button_style


class AlarmPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "ERROR / ALARM")
        self.listbox = tk.Listbox(self, bg=PANEL, fg=TEXT, selectbackground=RED, relief="flat", font=("Consolas", 13))
        self.listbox.pack(fill="both", expand=True, padx=24, pady=12)
        tk.Button(self, text="Alarm Reset", command=self.reset, **button_style(RED)).pack(pady=(0, 20))

    def refresh(self):
        self.listbox.delete(0, "end"); history = self.app.alarm_history
        if not history: self.listbox.insert("end", "✓ No Active Alarm")
        for name, record in sorted(history.items(), key=lambda item: item[1]["time"], reverse=True):
            state = "Active" if record["active"] else "Recovered"
            marker = "●" if record["active"] else "✓"
            self.listbox.insert("end", f"{marker} {record['time']:%Y-%m-%d %H:%M:%S}  {state}  {name}")

    def reset(self):
        if messagebox.askyesno("Alarm Reset", "Send the alarm reset command?"):
            result = self.app.command.send_alarm_reset()
            (messagebox.showinfo if result.ok else messagebox.showerror)("Alarm Reset", result.message)
