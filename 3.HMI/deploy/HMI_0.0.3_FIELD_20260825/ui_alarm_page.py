import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from register_map import FAULT_NAMES
from ui_common import BasePage, PANEL, TEXT, RED, GREEN, button_style


class AlarmPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "ERROR / ALARM")
        content = tk.Frame(self, bg="#101820")
        content.pack(side="left", fill="both", expand=True, padx=(0, 24), pady=(6, 12))
        alarm_area = tk.Frame(content, bg=PANEL)
        alarm_area.pack(fill="both", expand=True, pady=(0, 12))
        self.alarm_text = tk.Text(
            alarm_area, bg=PANEL, fg=TEXT, relief="flat", bd=0,
            wrap="word", padx=12, pady=8,
            font=("Microsoft JhengHei UI", 12),
            selectbackground=PANEL, selectforeground=TEXT,
            cursor="arrow", takefocus=0, state="disabled",
        )
        self.alarm_text.bind("<Button-1>", lambda _event: "break")
        self.alarm_text.bind("<B1-Motion>", lambda _event: "break")
        scrollbar = tk.Scrollbar(alarm_area, command=self.alarm_text.yview)
        self.alarm_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.alarm_text.pack(side="left", fill="both", expand=True)
        self.alarm_text.tag_configure("active", foreground=RED, spacing1=3, spacing3=5)
        self.alarm_text.tag_configure("latched", foreground="#f2bd42", spacing1=3, spacing3=5)
        self.alarm_text.tag_configure("recovered", foreground=GREEN, spacing1=3, spacing3=5)
        self.alarm_text.tag_configure("normal", foreground=GREEN, spacing1=3, spacing3=5)
        tk.Button(content, text="Alarm Reset", command=self.reset, **button_style(RED)).pack(pady=(0, 2))

    def refresh(self):
        self.alarm_text.configure(state="normal")
        self.alarm_text.delete("1.0", "end")
        history = self.app.alarm_history
        if not history:
            self.alarm_text.insert("end", "✓ No Active Alarm\n", "normal")
        for name, record in sorted(history.items(), key=lambda item: item[1]["time"], reverse=True):
            if record["active"] and record.get("condition_active", True):
                state, marker, tag = "Active", "●", "active"
            elif record["active"]:
                state, marker, tag = "Latched — Reset Required", "◆", "latched"
            else:
                state, marker, tag = "Recovered", "✓", "recovered"
            self.alarm_text.insert(
                "end",
                f"{marker} {record['time']:%Y-%m-%d %H:%M:%S}  {state}\n    {name}\n",
                tag,
            )
        self.alarm_text.configure(state="disabled")

    def reset(self):
        if messagebox.askyesno("Alarm Reset", "Send the alarm reset command?"):
            result = self.app.send_alarm_reset()
            (messagebox.showinfo if result.ok else messagebox.showerror)("Alarm Reset", result.message)
