import tkinter as tk
from tkinter import messagebox
from register_map import PARAMETER_LIMITS, CONVEYOR_SET_SPEED_WRITE
from ui_common import BasePage, PANEL, TEXT, MUTED, button_style


class ParameterPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "輸送帶參數設定")
        form = tk.Frame(self, bg=PANEL, padx=30, pady=24); form.pack(fill="x", padx=80, pady=20)
        self.entries = {}
        for row, name in enumerate(PARAMETER_LIMITS):
            tk.Label(form, text=name, bg=PANEL, fg=TEXT, font=("Segoe UI", 14)).grid(row=row, column=0, sticky="w", pady=8)
            entry = tk.Entry(form, bg="#0c141b", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 15), width=18)
            entry.grid(row=row, column=1, padx=25, pady=8); self.entries[name] = entry
            lo, hi = PARAMETER_LIMITS[name]
            tk.Label(form, text=f"{lo} ~ {hi}", bg=PANEL, fg=MUTED).grid(row=row, column=2)
        tk.Button(form, text="Apply 套用", command=self.apply, **button_style()).grid(row=6, column=0, columnspan=3, pady=20)
        self.loaded = False

    def refresh(self):
        if self.loaded: return
        for entry, value in zip(self.entries.values(), self.app.snapshot["parameters"]):
            entry.delete(0, "end"); entry.insert(0, str(value))
        self.loaded = True

    def apply(self):
        values = []
        try:
            for name, entry in self.entries.items():
                value = int(entry.get()); lo, hi = PARAMETER_LIMITS[name]
                if not lo <= value <= hi: raise ValueError(f"{name} 必須介於 {lo}～{hi}")
                values.append(value)
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc)); return
        if not messagebox.askyesno("確認寫入", "確定要將這些參數寫入 PLC？"): return
        ok = self.app.plc.write_d_block(CONVEYOR_SET_SPEED_WRITE, values)
        (messagebox.showinfo if ok else messagebox.showerror)("寫入結果", "參數寫入成功" if ok else f"寫入失敗：{self.app.plc.last_error}")
