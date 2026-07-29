import tkinter as tk
from tkinter import messagebox
from ui_common import BasePage, PANEL, TEXT, MUTED, GREEN, RED, button_style


class ManualPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "手動操作")
        body = tk.Frame(self, bg=PANEL, padx=35, pady=30); body.pack(fill="both", expand=True, padx=60, pady=20)
        self.mode_label = tk.Label(body, bg=PANEL, fg=TEXT, font=("Segoe UI", 18, "bold")); self.mode_label.pack(pady=8)
        tk.Button(body, text="切換 Manual 模式", command=self.switch_manual, **button_style()).pack(pady=6)
        speed = tk.Frame(body, bg=PANEL); speed.pack(pady=12)
        tk.Label(speed, text="Conveyor Speed RPM", bg=PANEL, fg=MUTED, font=("Segoe UI", 13)).pack(side="left", padx=10)
        self.speed = tk.Entry(speed, width=8, font=("Segoe UI", 16), justify="center"); self.speed.insert(0, "150"); self.speed.pack(side="left")
        self.run_btn = tk.Button(body, text="按住 Conveyor Run", **button_style(GREEN)); self.run_btn.pack(fill="x", pady=8)
        self.run_btn.bind("<ButtonPress-1>", self.run); self.run_btn.bind("<ButtonRelease-1>", self.stop)
        tk.Button(body, text="Set Conveyor Speed", command=self.set_speed, **button_style()).pack(fill="x", pady=8)
        tk.Button(body, text="Alarm Reset", command=self.reset, **button_style(RED)).pack(fill="x", pady=8)
        tk.Label(body, text="Robot Manual Action（Reserved）", bg="#34414b", fg=MUTED, font=("Segoe UI", 14), pady=15).pack(fill="x", pady=8)
        self.command_label = tk.Label(body, text="Command: Idle", bg=PANEL, fg=TEXT, font=("Segoe UI", 13)); self.command_label.pack(pady=8)

    def refresh(self):
        manual = self.app.machine_mode == "Manual"
        self.mode_label.configure(text=f"Mode: {self.app.machine_mode}")
        self.run_btn.configure(state="normal" if manual else "disabled")

    def switch_manual(self):
        if self.app.machine_mode == "Manual" or messagebox.askyesno("模式切換", "確定切換為 Manual 模式？"):
            self.app.set_mode("Manual")

    def run(self, _event=None):
        if self.app.machine_mode != "Manual": return
        try: speed = int(self.speed.get())
        except ValueError: messagebox.showerror("錯誤", "速度必須是整數"); return
        result = self.app.command.send_conveyor_run(speed); self.command_label.configure(text=f"Command: Run - {result.message}")

    def stop(self, _event=None):
        if self.app.machine_mode != "Manual": return
        result = self.app.command.send_conveyor_stop(); self.command_label.configure(text=f"Command: Stop - {result.message}")

    def set_speed(self):
        if self.app.machine_mode != "Manual":
            messagebox.showwarning("模式錯誤", "請先切換為 Manual 模式"); return
        try: speed = int(self.speed.get())
        except ValueError: messagebox.showerror("錯誤", "速度必須是整數"); return
        if not 0 <= speed <= 3000:
            messagebox.showerror("錯誤", "速度必須介於 0～3000 RPM"); return
        if messagebox.askyesno("確認", f"確定設定輸送帶速度為 {speed} RPM？"):
            result = self.app.command.send_set_conveyor_speed(speed)
            self.command_label.configure(text=f"Command: Set Speed - {result.message}")

    def reset(self):
        if messagebox.askyesno("確認", "確定送出 Alarm Reset？"):
            result = self.app.send_alarm_reset(); self.command_label.configure(text=f"Command: {result.message}")
