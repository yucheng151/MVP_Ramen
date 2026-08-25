import tkinter as tk
from register_map import FAULT_NAMES
from ui_common import BasePage, BG, PANEL, TEXT, GREEN, RED, button_style, value_card


class ConveyorDetailPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "輸送帶詳細狀態")
        grid = tk.Frame(self, bg=BG); grid.pack(fill="x", padx=24)
        self.values = {}
        names = ("目前速度 RPM", "母線電流 A", "設定速度 RPM", "加速度", "減速度", "母線電流設定", "相電流設定")
        for i, name in enumerate(names):
            card, label = value_card(grid, name); card.grid(row=i//4, column=i%4, padx=5, pady=5, sticky="nsew")
            grid.columnconfigure(i%4, weight=1); self.values[name] = label
        fault_frame = tk.LabelFrame(self, text=" Fault Status ", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold"))
        fault_frame.pack(fill="both", expand=True, padx=29, pady=16)
        self.fault_labels = []
        for i, name in enumerate(FAULT_NAMES):
            label = tk.Label(fault_frame, text=f"●  {name}", bg=PANEL, fg=GREEN, font=("Segoe UI", 12), anchor="w")
            label.grid(row=i//3, column=i%3, padx=18, pady=12, sticky="w"); self.fault_labels.append(label)
        tk.Button(self, text="Edit Parameters", command=lambda: app.show_page("ParameterPage"),
                  **button_style()).pack(pady=(0, 16))

    def refresh(self):
        d = self.app.snapshot["conveyor"]
        vals = (d[1], f"{d[2]/10:.1f}", d[3], d[4], d[5], d[6], d[7])
        for label, value in zip(self.values.values(), vals): label.configure(text=str(value))
        word = d[0]
        for bit, label in enumerate(self.fault_labels):
            active = bool(word & (1 << bit)); label.configure(fg=RED if active else GREEN, text=f"●  {FAULT_NAMES[bit]}")
