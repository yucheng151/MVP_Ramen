"""全自動訂單、麵櫃、麵篩與四站管理頁。"""

from __future__ import annotations

import os
from pathlib import Path
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageEnhance, ImageTk

from auto_plc_contract import AUTO_PLC_FIELDS, assigned_count
from ui_common import (
    BasePage, BG, PANEL, PANEL_2, DIVIDER, TEXT, MUTED,
    GREEN, RED, YELLOW, BLUE,
)


CABINET_IMAGE = Path(__file__).resolve().parent / "assets" / "noodle_cabinet.png"


class AutoSystemPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app, "AUTO ORDER & NOODLE SYSTEM")
        self._last_signature = None
        # PLC流程每次輪詢都會刷新，但麵櫃編輯框不能因此被舊值覆蓋。
        self._last_inventory_signature = None
        self._last_simulation_poll = 0.0
        self._last_stress_signature = None
        self._last_log_refresh = 0.0
        self._last_log_signature = None

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=(0, 24), pady=(6, 12))

        style = ttk.Style(self)
        style.configure(
            "Auto.TNotebook", background=BG, borderwidth=0,
            bordercolor=DIVIDER, lightcolor=DIVIDER, darkcolor=DIVIDER,
        )
        style.map(
            "Auto.TNotebook",
            bordercolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
            lightcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
            darkcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        )
        style.configure(
            "Auto.TNotebook.Tab", background=PANEL, foreground=MUTED,
            borderwidth=1, bordercolor=DIVIDER,
            lightcolor=DIVIDER, darkcolor=DIVIDER,
            font=("Microsoft JhengHei UI", 11, "bold"), padding=(18, 7),
        )
        style.map(
            "Auto.TNotebook.Tab",
            background=[("selected", PANEL_2), ("active", "#2d4151")],
            foreground=[("selected", TEXT), ("active", TEXT)],
            bordercolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
            lightcolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
            darkcolor=[("selected", DIVIDER), ("active", DIVIDER), ("!disabled", DIVIDER)],
        )
        style.configure(
            "Auto.Treeview", background=PANEL, foreground=TEXT,
            fieldbackground=PANEL, rowheight=28,
            bordercolor=DIVIDER, lightcolor=DIVIDER, darkcolor=DIVIDER,
            font=("Microsoft JhengHei UI", 10),
        )
        style.map(
            "Auto.Treeview",
            bordercolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
            lightcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
            darkcolor=[("disabled", DIVIDER), ("!disabled", DIVIDER)],
        )
        style.configure(
            "Auto.Treeview.Heading", bordercolor=DIVIDER,
            lightcolor=DIVIDER, darkcolor=DIVIDER,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        style.map(
            "Auto.Treeview.Heading",
            bordercolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
            lightcolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
            darkcolor=[("active", DIVIDER), ("!disabled", DIVIDER)],
        )

        self.tabs = ttk.Notebook(body, style="Auto.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.overview_tab = tk.Frame(self.tabs, bg=BG)
        self.orders_tab = tk.Frame(self.tabs, bg=BG)
        self.inventory_tab = tk.Frame(self.tabs, bg=BG)
        self.contract_tab = tk.Frame(self.tabs, bg=BG)
        self.simulation_tab = tk.Frame(self.tabs, bg=BG)
        self.stress_tab = tk.Frame(self.tabs, bg=BG)
        self.log_tab = tk.Frame(self.tabs, bg=BG)
        self.tabs.add(self.stress_tab, text="一鍵自動測試")
        self.tabs.add(self.overview_tab, text="流程總覽")
        self.tabs.add(self.orders_tab, text="訂單 FIFO")
        self.tabs.add(self.inventory_tab, text="麵櫃 / 空盒")
        self.tabs.add(self.contract_tab, text="PLC 通訊規劃")
        self.tabs.add(
            self.simulation_tab,
            text=("模擬控制" if app.runtime_profile == "simulation" else "模擬控制（鎖定）"),
        )
        self.tabs.add(self.log_tab, text="PLC Debug LOG")

        self._build_overview()
        self._build_orders()
        self._build_inventory()
        self._build_contract()
        self._build_simulation()
        self._build_stress()
        self._build_logs()
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")
        if app.runtime_profile == "simulation" and app.simulation_controller is not None:
            # 模擬版開啟AUTO SYSTEM後直接進入一鍵壓力測試。
            self.tabs.select(self.stress_tab)

    def _panel(self, parent, title):
        panel = tk.Frame(parent, bg=PANEL, highlightbackground="#334554", highlightthickness=1)
        tk.Label(panel, text=title, bg=PANEL, fg=TEXT,
                 font=("Microsoft JhengHei UI", 13, "bold")).pack(anchor="w", padx=14, pady=(10, 6))
        return panel

    def _build_stress(self):
        is_simulation = self.app.runtime_profile == "simulation"
        tk.Label(
            self.stress_tab,
            text=(
                "一鍵自動壓力測試｜自動送單、自動落碗、自動IPC／UR／Nachi、自動推進四站"
                if is_simulation
                else "FIELD現場版禁止自動模擬測試"
            ),
            bg="#173d32" if is_simulation else "#5a251f",
            fg=GREEN if is_simulation else YELLOW,
            padx=12, pady=10,
            font=("Microsoft JhengHei UI", 12, "bold"),
        ).pack(fill="x", pady=(8, 6))

        controls = tk.Frame(
            self.stress_tab, bg=PANEL, padx=14, pady=10,
            highlightbackground="#40515e", highlightthickness=1,
        )
        controls.pack(fill="x", pady=(0, 6))
        tk.Label(controls, text="測試碗數", bg=PANEL, fg=MUTED,
                 font=("Microsoft JhengHei UI", 10, "bold")).pack(side="left")
        self.stress_count_var = tk.StringVar(value="1000")
        self.stress_count_combo = ttk.Combobox(
            controls, textvariable=self.stress_count_var,
            values=("10", "100", "1000"), width=8,
            font=("Consolas", 13, "bold"),
        )
        self.stress_count_combo.pack(side="left", padx=8)
        self.stress_start_button = tk.Button(
            controls, text="一鍵開始自動狂送訂單",
            command=self._start_auto_stress,
            bg=GREEN, fg="white", relief="flat", bd=0,
            padx=28, pady=10,
            font=("Microsoft JhengHei UI", 13, "bold"),
        )
        self.stress_start_button.pack(side="left", padx=6)
        self.stress_stop_button = tk.Button(
            controls, text="停止測試", command=self._stop_auto_stress,
            bg=RED, fg="white", relief="flat", bd=0,
            padx=16, pady=10,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.stress_stop_button.pack(side="left", padx=6)
        self.stress_result_label = tk.Label(
            controls, text="尚未開始", bg=PANEL, fg=MUTED,
            font=("Microsoft JhengHei UI", 11, "bold"),
        )
        self.stress_result_label.pack(side="right")

        summary = tk.Frame(self.stress_tab, bg=BG)
        summary.pack(fill="x", pady=4)
        self.stress_summary_labels = {}
        for key, title in (
            ("submitted", "已送訂單"), ("completed", "已完成"),
            ("fifo", "PLC FIFO"), ("updated", "最後更新"),
        ):
            frame = tk.Frame(
                summary, bg=PANEL_2, padx=12, pady=7,
                highlightbackground="#40515e", highlightthickness=1,
            )
            frame.pack(side="left", fill="x", expand=True, padx=3)
            tk.Label(frame, text=title, bg=PANEL_2, fg=MUTED,
                     font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w")
            label = tk.Label(frame, text="--", bg=PANEL_2, fg=TEXT,
                             font=("Consolas", 12, "bold"))
            label.pack(anchor="w")
            self.stress_summary_labels[key] = label
        self.stress_progress = ttk.Progressbar(
            self.stress_tab, orient="horizontal", mode="determinate",
        )
        self.stress_progress.pack(fill="x", pady=(2, 6))

        locations = tk.Frame(self.stress_tab, bg=BG)
        locations.pack(fill="x", pady=(0, 6))
        self.stress_location_labels = {}
        for key, title in (
            ("FIFO等待", "FIFO等待"),
            ("落碗→放麵／UR1", "落碗→放麵／UR1"),
            ("放麵／UR1→UR2", "放麵／UR1→UR2"),
            ("UR2→注湯", "UR2→注湯"),
            ("完成", "已完成"),
        ):
            frame = tk.Frame(
                locations, bg=PANEL, padx=8, pady=5,
                highlightbackground="#40515e", highlightthickness=1,
            )
            frame.pack(side="left", fill="both", expand=True, padx=3)
            tk.Label(frame, text=title, bg=PANEL, fg=MUTED,
                     font=("Microsoft JhengHei UI", 8, "bold")).pack(anchor="w")
            label = tk.Label(
                frame, text="--", bg=PANEL, fg=TEXT, justify="left", anchor="w",
                font=("Consolas", 8, "bold"), wraplength=210,
            )
            label.pack(fill="x")
            self.stress_location_labels[key] = label

        table_frame = tk.Frame(self.stress_tab, bg=BG)
        table_frame.pack(fill="both", expand=True, pady=(0, 8))
        columns = ("sequence", "unit", "location")
        self.stress_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", style="Auto.Treeview",
        )
        for column, title, width in (
            ("sequence", "順序", 90),
            ("unit", "UnitID／碗編號", 250),
            ("location", "目前位置", 420),
        ):
            self.stress_tree.heading(column, text=title)
            self.stress_tree.column(column, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.stress_tree.yview,
        )
        self.stress_tree.configure(yscrollcommand=scrollbar.set)
        self.stress_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        if not is_simulation:
            self.stress_start_button.configure(state="disabled")
            self.stress_stop_button.configure(state="disabled")
            self.stress_count_combo.configure(state="disabled")

    def _start_auto_stress(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        try:
            total = int(self.stress_count_var.get())
            if not 3 <= total <= 100000:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "自動壓力測試", "測試碗數必須介於3到100000。", parent=self,
            )
            return
        if not controller.start_stress(total):
            messagebox.showwarning(
                "自動壓力測試", controller.last_message, parent=self,
            )
        self._last_stress_signature = None
        self._refresh_auto_stress()

    def _stop_auto_stress(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        controller.stop_stress()
        self._last_stress_signature = None
        self._refresh_auto_stress()

    def _refresh_auto_stress(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        state = controller.read_stress_status()
        signature = repr(state)
        if signature == self._last_stress_signature:
            return
        self._last_stress_signature = signature
        target = int(state.get("target", 0))
        submitted = int(state.get("submitted", 0))
        completed = int(state.get("completed", 0))
        status = str(state.get("status", "IDLE"))
        self.stress_summary_labels["submitted"].configure(
            text=f"{submitted} / {target or '--'}",
        )
        self.stress_summary_labels["completed"].configure(
            text=f"{completed} / {target or '--'}",
        )
        self.stress_summary_labels["fifo"].configure(text=str(state.get("fifo", 0)))
        self.stress_summary_labels["updated"].configure(text=str(state.get("updated_at", "--")))
        self.stress_progress.configure(maximum=max(target, 1), value=completed)
        colors = {"PASS": GREEN, "FAIL": RED, "RUNNING": YELLOW, "STARTING": YELLOW}
        result_text = {
            "IDLE": "尚未開始", "STARTING": "正在準備…",
            "RUNNING": "自動測試執行中", "PASS": "全部通過",
            "FAIL": f"測試失敗：{state.get('error', '')}",
        }.get(status, status)
        self.stress_result_label.configure(
            text=result_text, fg=colors.get(status, MUTED),
        )
        running = controller.stress_running
        self.stress_start_button.configure(state="disabled" if running else "normal")
        self.stress_stop_button.configure(state="normal" if running else "disabled")
        self.stress_count_combo.configure(state="disabled" if running else "normal")

        grouped = {key: [] for key in self.stress_location_labels}
        for row in state.get("units", []):
            location = row.get("location", "--")
            if location in grouped:
                grouped[location].append(str(row.get("unit_id", "--")))
        for key, label in self.stress_location_labels.items():
            values = grouped[key]
            preview = ", ".join(values[:4])
            if len(values) > 4:
                preview += f"\n…另有 {len(values) - 4} 碗"
            label.configure(text=preview or "--", fg=GREEN if key == "完成" else TEXT)

        for item in self.stress_tree.get_children():
            self.stress_tree.delete(item)
        for row in state.get("units", []):
            self.stress_tree.insert(
                "", "end",
                values=(row.get("sequence"), row.get("unit_id"), row.get("location")),
            )

    def _build_overview(self):
        top = tk.Frame(self.overview_tab, bg=BG)
        top.pack(fill="x", pady=(8, 6))
        self.mapping_banner = tk.Label(
            top, text="PLC即時流程：連線中...",
            bg="#4a3b18", fg=YELLOW, font=("Microsoft JhengHei UI", 11, "bold"),
            padx=12, pady=7,
        )
        self.mapping_banner.pack(side="left", fill="x", expand=True)
        self.demo_button = tk.Button(
            top, text="本機模擬推進（不寫PLC）", command=self._advance_demo,
            bg=BLUE, fg="white", activebackground=BLUE, activeforeground="white",
            relief="flat", bd=0, padx=14, pady=7,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.demo_button.pack(side="right", padx=(8, 0))

        live_summary = tk.Frame(self.overview_tab, bg=PANEL, padx=10, pady=7,
                                highlightbackground="#334554", highlightthickness=1)
        live_summary.pack(fill="x", pady=(0, 6))
        self.live_summary_labels = {}
        for key, title in (
            ("fifo", "PLC FIFO"),
            ("rightmost", "最右端狀態"),
            ("complete_unit", "最後完成 UnitID"),
            ("complete_index", "完成 Index"),
        ):
            group = tk.Frame(live_summary, bg=PANEL)
            group.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(group, text=title, bg=PANEL, fg=MUTED,
                     font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w")
            label = tk.Label(group, text="--", bg=PANEL, fg=TEXT,
                             font=("Consolas", 14, "bold"))
            label.pack(anchor="w")
            self.live_summary_labels[key] = label

        baskets_panel = self._panel(self.overview_tab, "三個麵篩 / Noodle Baskets")
        baskets_panel.pack(fill="x", pady=6)
        basket_row = tk.Frame(baskets_panel, bg=PANEL)
        basket_row.pack(fill="x", padx=10, pady=(0, 10))
        self.basket_labels = []
        for number in range(1, 4):
            box = tk.Frame(basket_row, bg=PANEL_2, highlightbackground="#40515e", highlightthickness=1)
            box.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(box, text=f"麵篩 {number}", bg=PANEL_2, fg=MUTED,
                     font=("Microsoft JhengHei UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
            label = tk.Label(box, text="Idle", bg=PANEL_2, fg=GREEN,
                             font=("Consolas", 12, "bold"), justify="left")
            label.pack(anchor="w", padx=12, pady=(0, 8))
            self.basket_labels.append(label)

        stations_panel = self._panel(self.overview_tab, "四站輸送流程（最後端優先）")
        stations_panel.pack(fill="both", expand=True, pady=6)
        station_row = tk.Frame(stations_panel, bg=PANEL)
        station_row.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.station_labels = []
        self.station_frames = []
        for number, name in enumerate(("落碗", "放麵 & UR1", "UR2", "注湯 & 完成"), 1):
            box = tk.Frame(station_row, bg=PANEL_2, highlightbackground="#40515e", highlightthickness=1)
            box.pack(side="left", fill="both", expand=True, padx=4)
            self.station_frames.append(box)
            tk.Label(box, text=f"站 {number}", bg=PANEL_2, fg=MUTED,
                     font=("Microsoft JhengHei UI", 10, "bold")).pack(pady=(12, 2))
            tk.Label(box, text=name, bg=PANEL_2, fg=TEXT,
                     font=("Microsoft JhengHei UI", 12, "bold")).pack()
            label = tk.Label(box, text="Idle", bg=PANEL_2, fg=GREEN,
                             font=("Consolas", 11, "bold"), justify="center")
            label.pack(pady=(8, 12))
            self.station_labels.append(label)

        resource_row = tk.Frame(stations_panel, bg=PANEL)
        resource_row.pack(fill="x", padx=10, pady=(0, 9))
        self.resource_labels = {}
        for key, title in (
            ("nachi", "Nachi"),
            ("ur1", "UR1"),
            ("ur2", "UR2"),
            ("conveyor", "輸送帶／站點"),
        ):
            group = tk.Frame(resource_row, bg="#1d2a33", padx=8, pady=5,
                             highlightbackground="#40515e", highlightthickness=1)
            group.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(group, text=title, bg="#1d2a33", fg=MUTED,
                     font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w")
            label = tk.Label(group, text="--", bg="#1d2a33", fg=TEXT,
                             font=("Microsoft JhengHei UI", 9, "bold"))
            label.pack(anchor="w")
            self.resource_labels[key] = label

    def _build_orders(self):
        form = tk.Frame(self.orders_tab, bg=PANEL, padx=15, pady=12)
        form.pack(fill="x", pady=(8, 6))
        tk.Label(form, text="麵櫃編號", bg=PANEL, fg=MUTED,
                 font=("Microsoft JhengHei UI", 10)).pack(side="left")
        self.cabinet_var = tk.StringVar(value="1")
        ttk.Combobox(form, textvariable=self.cabinet_var, values=tuple(range(1, 11)),
                     width=6, state="readonly").pack(side="left", padx=(6, 18))
        tk.Label(form, text="軟硬度", bg=PANEL, fg=MUTED,
                 font=("Microsoft JhengHei UI", 10)).pack(side="left")
        self.firmness_var = tk.StringVar(value="正常")
        ttk.Combobox(form, textvariable=self.firmness_var, values=("軟", "正常", "硬"),
                     width=8, state="readonly").pack(side="left", padx=(6, 18))
        self.add_order_button = tk.Button(
            form, text="新增本機訂單", command=self._add_order,
            bg=GREEN, fg="white", relief="flat", bd=0, padx=14, pady=6,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.add_order_button.pack(side="left")
        self.cancel_order_button = tk.Button(
            form, text="取消所選等待訂單", command=self._cancel_order,
            bg=RED, fg="white", relief="flat", bd=0, padx=14, pady=6,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.cancel_order_button.pack(side="left", padx=8)
        tk.Label(form, text="正式手機訂單API待後續串接", bg=PANEL, fg=YELLOW,
                 font=("Microsoft JhengHei UI", 9, "bold")).pack(side="right")

        columns = ("unit", "time", "cabinet", "firmness", "basket", "status")
        self.order_tree = ttk.Treeview(self.orders_tab, columns=columns, show="headings", style="Auto.Treeview")
        headings = ("UnitID", "建立時間", "麵櫃", "軟硬度", "麵篩", "狀態")
        widths = (110, 190, 80, 90, 80, 170)
        for column, heading, width in zip(columns, headings, widths):
            self.order_tree.heading(column, text=heading)
            self.order_tree.column(column, width=width, anchor="center")
        self.order_tree.pack(fill="both", expand=True, pady=(0, 8))

    def _build_inventory(self):
        content = tk.Frame(self.inventory_tab, bg=BG)
        content.pack(fill="both", expand=True, pady=8)

        summary = tk.Frame(content, bg=PANEL, padx=12, pady=7)
        summary.pack(fill="x", pady=(0, 6))
        tk.Label(summary, text="麵櫃實際排列 / 每格 BOX 數量設定", bg=PANEL, fg=TEXT,
                 font=("Microsoft JhengHei UI", 12, "bold")).pack(side="left")
        self.total_noodle_label = tk.Label(summary, text="生麵盒合計：0 BOX", bg=PANEL, fg=GREEN,
                                           font=("Microsoft JhengHei UI", 10, "bold"))
        self.total_noodle_label.pack(side="right", padx=(16, 0))
        self.total_empty_label = tk.Label(summary, text="空盒合計：0 BOX", bg=PANEL, fg=YELLOW,
                                          font=("Microsoft JhengHei UI", 10, "bold"))
        self.total_empty_label.pack(side="right")

        self.cabinet_vars = [(tk.StringVar(value="0"), tk.StringVar(value="20")) for _ in range(10)]
        self.bin_vars = [(tk.StringVar(value="0"), tk.StringVar(value="20")) for _ in range(2)]
        self._selected_inventory = ("empty", 0)
        self._cabinet_photo = None
        self._cabinet_render_job = None

        workspace = tk.Frame(content, bg=BG)
        workspace.pack(fill="both", expand=True)
        self.cabinet_canvas = tk.Canvas(
            workspace, bg="#090d10", bd=0, highlightbackground="#40515e", highlightthickness=1,
        )
        self.cabinet_canvas.pack(side="left", fill="both", expand=True)
        self.cabinet_canvas.bind("<Configure>", self._schedule_cabinet_render)

        if CABINET_IMAGE.exists():
            source = Image.open(CABINET_IMAGE).convert("RGB")
            # 去除右側大片空白，讓12個格位在HMI中更大、更容易點選。
            source = source.crop((160, 40, 900, 790))
            self._cabinet_source = ImageEnhance.Brightness(source).enhance(0.62)
        else:
            self._cabinet_source = None

        self._cabinet_hotspots = (
            ("empty", 0, "空盒 1", 0.18, 0.29),
            ("empty", 1, "空盒 2", 0.35, 0.29),
            ("noodle", 0, "麵櫃 1", 0.56, 0.34),
            ("noodle", 1, "麵櫃 2", 0.73, 0.34),
            ("noodle", 2, "麵櫃 3", 0.18, 0.57),
            ("noodle", 3, "麵櫃 4", 0.35, 0.57),
            ("noodle", 4, "麵櫃 5", 0.56, 0.57),
            ("noodle", 5, "麵櫃 6", 0.73, 0.57),
            ("noodle", 6, "麵櫃 7", 0.18, 0.82),
            ("noodle", 7, "麵櫃 8", 0.35, 0.82),
            ("noodle", 8, "麵櫃 9", 0.56, 0.82),
            ("noodle", 9, "麵櫃 10", 0.73, 0.82),
        )

        editor = tk.Frame(workspace, bg=PANEL, width=285, padx=18, pady=15,
                          highlightbackground="#40515e", highlightthickness=1)
        editor.pack(side="right", fill="y", padx=(8, 0))
        editor.pack_propagate(False)
        tk.Label(editor, text="所選格位", bg=PANEL, fg=MUTED,
                 font=("Microsoft JhengHei UI", 10)).pack(anchor="w")
        self.selected_slot_label = tk.Label(editor, text="空盒櫃 1", bg=PANEL, fg=YELLOW,
                                            font=("Microsoft JhengHei UI", 18, "bold"))
        self.selected_slot_label.pack(anchor="w", pady=(2, 16))
        self.selected_quantity_var = tk.StringVar(value="0")
        self.selected_capacity_var = tk.StringVar(value="20")
        for title, variable in (("目前有幾個 BOX", self.selected_quantity_var),
                                ("此格最多 BOX", self.selected_capacity_var)):
            tk.Label(editor, text=title, bg=PANEL, fg=MUTED,
                     font=("Microsoft JhengHei UI", 10, "bold")).pack(anchor="w", pady=(5, 3))
            tk.Entry(editor, textvariable=variable, justify="center",
                     font=("Consolas", 18, "bold")).pack(fill="x", ipady=4)
        self.selected_detail_label = tk.Label(editor, text="--", bg=PANEL, fg=TEXT,
                                              justify="left", font=("Microsoft JhengHei UI", 10))
        self.selected_detail_label.pack(anchor="w", pady=16)
        self.save_inventory_button = tk.Button(
            editor, text="儲存這一格 BOX 數量",
            command=self._save_selected_inventory,
            bg=BLUE, fg="white", relief="flat", bd=0, padx=10, pady=9,
            font=("Microsoft JhengHei UI", 10, "bold"), cursor="hand2",
        )
        self.save_inventory_button.pack(fill="x")
        tk.Label(editor, text="點左側麵櫃的任一格即可切換\nPLC位址尚未配置，目前保存在HMI本機",
                 bg=PANEL, fg=YELLOW, justify="left",
                 font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w", pady=(18, 0))

    def _schedule_cabinet_render(self, _event=None):
        if getattr(self.app, "current_page", None) != "AutoSystemPage":
            return
        if self.tabs.select() != str(self.inventory_tab):
            return
        if self._cabinet_render_job is not None:
            self.after_cancel(self._cabinet_render_job)
        self._cabinet_render_job = self.after(180, self._render_cabinet_image)

    def _on_tab_changed(self, _event=None):
        if self.tabs.select() == str(self.inventory_tab):
            self._schedule_cabinet_render()
        elif self.tabs.select() == str(self.log_tab):
            self._refresh_plc_debug_logs(force=True)

    def _render_cabinet_image(self):
        self._cabinet_render_job = None
        canvas = self.cabinet_canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 20:
            return
        canvas.delete("all")
        if self._cabinet_source is None:
            canvas.create_text(width / 2, height / 2, text="找不到麵櫃底圖", fill=RED,
                               font=("Microsoft JhengHei UI", 15, "bold"))
            return
        scale = min(width / self._cabinet_source.width, height / self._cabinet_source.height)
        image_width = max(1, int(self._cabinet_source.width * scale))
        image_height = max(1, int(self._cabinet_source.height * scale))
        image = self._cabinet_source.resize((image_width, image_height), Image.Resampling.LANCZOS)
        self._cabinet_photo = ImageTk.PhotoImage(image)
        left, top = (width - image_width) / 2, (height - image_height) / 2
        canvas.create_image(left, top, image=self._cabinet_photo, anchor="nw")

        for kind, index, label, nx, ny in self._cabinet_hotspots:
            variables = self.bin_vars[index] if kind == "empty" else self.cabinet_vars[index]
            quantity, capacity = variables[0].get(), variables[1].get()
            x, y = left + nx * image_width, top + ny * image_height
            selected = self._selected_inventory == (kind, index)
            color = YELLOW if kind == "empty" else BLUE
            outline = "#ffffff" if selected else color
            tag = f"slot_{kind}_{index}"
            canvas.create_rectangle(
                x - 53, y - 24, x + 53, y + 24,
                fill="#111d26", outline=outline, width=3 if selected else 2,
                tags=(tag, "cabinet-slot"),
            )
            canvas.create_text(x, y - 9, text=label, fill=color,
                               font=("Microsoft JhengHei UI", 9, "bold"), tags=(tag,))
            canvas.create_text(x, y + 10, text=f"{quantity} / {capacity} BOX", fill=TEXT,
                               font=("Consolas", 9, "bold"), tags=(tag,))
            canvas.tag_bind(tag, "<Button-1>",
                            lambda _event, k=kind, i=index: self._select_inventory_slot(k, i))
            canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
            canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))

    def _select_inventory_slot(self, kind, index):
        self._selected_inventory = (kind, index)
        self._load_selected_inventory()
        self._render_cabinet_image()

    def _load_selected_inventory(self):
        kind, index = self._selected_inventory
        variables = self.bin_vars[index] if kind == "empty" else self.cabinet_vars[index]
        self.selected_quantity_var.set(variables[0].get())
        self.selected_capacity_var.set(variables[1].get())
        if kind == "empty":
            self.selected_slot_label.configure(text=f"空盒櫃 {index + 1}", fg=YELLOW)
            quantity = int(variables[0].get() or 0)
            capacity = int(variables[1].get() or 0)
            self.selected_detail_label.configure(text=f"目前空盒：{quantity} BOX\n剩餘容量：{max(0, capacity - quantity)} BOX")
        else:
            self.selected_slot_label.configure(text=f"麵櫃 {index + 1}", fg=BLUE)
            reserved = self.app.auto_store.reserved(index + 1)
            quantity = int(variables[0].get() or 0)
            self.selected_detail_label.configure(
                text=f"訂單保留：{reserved} BOX\n目前可用：{max(0, quantity - reserved)} BOX"
            )

    def _save_selected_inventory(self):
        if self.app.runtime_profile == "field":
            messagebox.showwarning(
                "FIELD現場版", "正式麵櫃PLC位址尚未配置，禁止寫入HMI本機假資料。",
                parent=self,
            )
            return
        kind, index = self._selected_inventory
        try:
            quantity = int(self.selected_quantity_var.get())
            capacity = int(self.selected_capacity_var.get())
            if quantity < 0 or capacity < 1 or quantity > capacity:
                raise ValueError
        except ValueError:
            messagebox.showerror("BOX數量", "目前數量必須介於0與上限之間，上限至少為1。", parent=self)
            return
        variables = self.bin_vars[index] if kind == "empty" else self.cabinet_vars[index]
        variables[0].set(str(quantity))
        variables[1].set(str(capacity))
        self._save_inventory()

    def _build_contract(self):
        info = tk.Label(
            self.contract_tab,
            text="以下欄位已規劃，但 address=None；PLC完成後只在集中通訊契約填入位址。",
            bg="#4a3b18", fg=YELLOW, padx=12, pady=8,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        info.pack(fill="x", pady=(8, 6))
        columns = ("name", "direction", "type", "count", "address", "comment")
        tree = ttk.Treeview(self.contract_tab, columns=columns, show="headings", style="Auto.Treeview")
        headings = ("欄位", "方向", "型態", "數量", "PLC位址", "用途")
        widths = (230, 110, 100, 60, 100, 300)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, anchor="center" if column != "comment" else "w")
        for field in AUTO_PLC_FIELDS:
            tree.insert("", "end", values=(
                field.name, field.direction, field.data_type, field.count,
                "待PLC配置" if field.address is None else f"D{field.address}", field.comment,
            ))
        tree.pack(fill="both", expand=True, pady=(0, 8))

    def _build_logs(self):
        tk.Label(
            self.log_tab,
            text="PLC 自動模式 Debug 原始值｜唯讀 D8000–D8031、D8100–D8134，不回寫 PLC",
            bg="#173d32", fg=GREEN, padx=12, pady=9,
            font=("Microsoft JhengHei UI", 11, "bold"),
        ).pack(fill="x", pady=(8, 6))

        controls = tk.Frame(
            self.log_tab, bg=PANEL, padx=12, pady=8,
            highlightbackground=DIVIDER, highlightthickness=1,
        )
        controls.pack(fill="x", pady=(0, 6))
        tk.Button(
            controls, text="重新整理",
            command=lambda: self._refresh_plc_debug_logs(force=True),
            bg=BLUE, fg="white", relief="flat", bd=0, padx=18, pady=7,
            font=("Microsoft JhengHei UI", 10, "bold"),
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            controls, text="開啟 Debug LOG 資料夾",
            command=self._open_plc_debug_log_folder,
            bg=PANEL_2, fg=TEXT, relief="flat", bd=0, padx=18, pady=7,
            font=("Microsoft JhengHei UI", 10, "bold"),
        ).pack(side="left", padx=6)
        tk.Button(
            controls, text="開啟今日 CSV", command=self._open_plc_debug_log_csv,
            bg=PANEL_2, fg=TEXT, relief="flat", bd=0, padx=18, pady=7,
            font=("Microsoft JhengHei UI", 10, "bold"),
        ).pack(side="left", padx=6)
        tk.Button(
            controls, text="開啟 D 位址表", command=self._open_plc_debug_address_map,
            bg=PANEL_2, fg=TEXT, relief="flat", bd=0, padx=18, pady=7,
            font=("Microsoft JhengHei UI", 10, "bold"),
        ).pack(side="left", padx=6)
        self.plc_debug_log_status = tk.Label(
            controls, text="等待自動模式 PLC Debug 資料", bg=PANEL, fg=MUTED,
            anchor="e", justify="right",
            font=("Microsoft JhengHei UI", 9, "bold"),
        )
        self.plc_debug_log_status.pack(side="right", fill="x", expand=True)

        self.plc_debug_log_path = tk.Label(
            self.log_tab, text=str(self.app.plc_debug_log.log_dir),
            bg=BG, fg=MUTED, anchor="w", justify="left",
            font=("Consolas", 9),
        )
        self.plc_debug_log_path.pack(fill="x", padx=4, pady=(0, 6))

        table = tk.Frame(self.log_tab, bg=BG)
        table.pack(fill="both", expand=True, pady=(0, 8))
        columns = (
            "time", "reason", "changed", "D8002", "baskets", "rightmost",
            "noodle_step", "D8009", "D8010", "fifo", "complete_unit",
        )
        self.plc_debug_log_tree = ttk.Treeview(
            table, columns=columns, show="headings", style="Auto.Treeview",
        )
        for column, title, width, anchor in (
            ("time", "時間", 185, "center"),
            ("reason", "原因", 85, "center"),
            ("changed", "本筆變更 D 位址", 240, "w"),
            ("D8002", "D8002", 80, "center"),
            ("baskets", "麵篩 State 1/2/3", 145, "center"),
            ("rightmost", "最右端", 70, "center"),
            ("noodle_step", "Nachi Step", 90, "center"),
            ("D8009", "D8009", 80, "center"),
            ("D8010", "D8010", 80, "center"),
            ("fifo", "FIFO", 60, "center"),
            ("complete_unit", "完成 UnitID", 120, "center"),
        ):
            self.plc_debug_log_tree.heading(column, text=title)
            self.plc_debug_log_tree.column(column, width=width, anchor=anchor)
        y_scrollbar = ttk.Scrollbar(
            table, orient="vertical", command=self.plc_debug_log_tree.yview,
        )
        x_scrollbar = ttk.Scrollbar(
            table, orient="horizontal", command=self.plc_debug_log_tree.xview,
        )
        self.plc_debug_log_tree.configure(
            yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set,
        )
        self.plc_debug_log_tree.grid(row=0, column=0, sticky="nsew")
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)

    @staticmethod
    def _plc_debug_word(registers, address):
        try:
            return int(registers.get(f"D{address}", 0)) & 0xFFFF
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _plc_debug_dword(cls, registers, low_address):
        low = cls._plc_debug_word(registers, low_address)
        high = cls._plc_debug_word(registers, low_address + 1)
        return (high << 16) | low

    def _refresh_plc_debug_logs(self, force=False):
        if not hasattr(self, "plc_debug_log_tree"):
            return
        if not force and self.tabs.select() != str(self.log_tab):
            return
        now = time.monotonic()
        if not force and now - self._last_log_refresh < 2.0:
            return
        self._last_log_refresh = now
        rows = self.app.plc_debug_log.read_recent(250)
        signature = (
            len(rows),
            rows[-1].get("timestamp") if rows else None,
            rows[-1].get("sample_index") if rows else None,
            self.app.plc_debug_log.last_error,
        )
        if not force and signature == self._last_log_signature:
            return
        self._last_log_signature = signature
        for item in self.plc_debug_log_tree.get_children():
            self.plc_debug_log_tree.delete(item)
        for row in reversed(rows):
            registers = row.get("registers") or {}
            changed = ",".join(row.get("changed_addresses") or ()) or "--"
            self.plc_debug_log_tree.insert("", "end", values=(
                str(row.get("timestamp", "--")).replace("T", " "),
                row.get("reason", "--"),
                changed,
                f"0x{self._plc_debug_word(registers, 8002):04X}",
                "/".join(str(self._plc_debug_word(registers, address))
                         for address in (8003, 8004, 8005)),
                self._plc_debug_word(registers, 8006),
                self._plc_debug_word(registers, 8008),
                f"0x{self._plc_debug_word(registers, 8009):04X}",
                f"0x{self._plc_debug_word(registers, 8010):04X}",
                self._plc_debug_word(registers, 8130),
                self._plc_debug_dword(registers, 8131),
            ))
        error = self.app.plc_debug_log.last_error
        self.plc_debug_log_status.configure(
            text=(f"寫入錯誤：{error}" if error else
                  f"最近 {len(rows)} 筆｜PLC 原始 D 值｜保留 90 天"),
            fg=RED if error else GREEN,
        )
        self.plc_debug_log_path.configure(
            text=(f"JSONL：{self.app.plc_debug_log.current_jsonl_path}    "
                  f"CSV：{self.app.plc_debug_log.current_csv_path}"),
        )

    def _open_plc_debug_log_folder(self):
        try:
            os.startfile(str(self.app.plc_debug_log.log_dir))
        except (AttributeError, OSError) as exc:
            messagebox.showerror("PLC Debug LOG", f"無法開啟資料夾：{exc}", parent=self)

    def _open_plc_debug_log_csv(self):
        try:
            os.startfile(str(self.app.plc_debug_log.current_csv_path))
        except (AttributeError, OSError) as exc:
            messagebox.showerror("PLC Debug LOG", f"無法開啟今日 CSV：{exc}", parent=self)

    def _open_plc_debug_address_map(self):
        try:
            os.startfile(str(self.app.plc_debug_log.address_map_path))
        except (AttributeError, OSError) as exc:
            messagebox.showerror("PLC Debug LOG", f"無法開啟 D 位址表：{exc}", parent=self)

    def _build_simulation(self):
        is_simulation = self.app.runtime_profile == "simulation"
        banner = tk.Label(
            self.simulation_tab,
            text=(
                "SIMULATION｜這裡直接讀寫AS200模擬PLC，不是HMI本機動畫"
                if is_simulation
                else "FIELD｜現場版禁止所有模擬輸入與周邊假訊號"
            ),
            bg="#173d32" if is_simulation else "#5a251f",
            fg=GREEN if is_simulation else YELLOW,
            padx=12, pady=9,
            font=("Microsoft JhengHei UI", 11, "bold"),
        )
        banner.pack(fill="x", pady=(8, 6))

        quick = tk.Frame(
            self.simulation_tab, bg="#1d2a33", padx=12, pady=10,
            highlightbackground="#40515e", highlightthickness=1,
        )
        quick.pack(fill="x", pady=(0, 6))
        tk.Label(
            quick, text="只要照這三顆大按鈕操作",
            bg="#1d2a33", fg=TEXT,
            font=("Microsoft JhengHei UI", 13, "bold"),
        ).pack(side="left", padx=(0, 14))
        self.sim_prepare_button = tk.Button(
            quick, text="① 一鍵準備", command=self._prepare_simulation,
            bg=GREEN, fg="white", relief="flat", bd=0, padx=24, pady=10,
            font=("Microsoft JhengHei UI", 12, "bold"),
        )
        self.sim_prepare_button.pack(side="left", padx=4)
        self.sim_quick_order_button = tk.Button(
            quick, text="② 送出一碗", command=self._submit_sim_order,
            bg=BLUE, fg="white", relief="flat", bd=0, padx=24, pady=10,
            font=("Microsoft JhengHei UI", 12, "bold"),
        )
        self.sim_quick_order_button.pack(side="left", padx=4)
        self.sim_next_button = tk.Button(
            quick, text="③ 下一步：落碗到位", command=self._next_sim_station,
            bg=YELLOW, fg="#17212b", relief="flat", bd=0, padx=24, pady=10,
            font=("Microsoft JhengHei UI", 12, "bold"),
        )
        self.sim_next_button.pack(side="left", fill="x", expand=True, padx=4)
        self.sim_stop_button = tk.Button(
            quick, text="停止／清除", command=self._stop_simulation,
            bg=RED, fg="white", relief="flat", bd=0, padx=16, pady=10,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.sim_stop_button.pack(side="right", padx=(8, 0))

        status = self._panel(self.simulation_tab, "模擬狀態")
        status.pack(fill="x", pady=6)
        status_row = tk.Frame(status, bg=PANEL)
        status_row.pack(fill="x", padx=12, pady=(0, 10))
        self.sim_status_labels = {}
        for key, title in (
            ("plc", "AS200 PLC"), ("mode", "D8000模擬模式"),
            ("peripheral", "IPC／UR／Nachi"), ("fifo", "PLC FIFO"),
            ("ack", "訂單ACK"),
        ):
            group = tk.Frame(status_row, bg=PANEL_2, padx=10, pady=7)
            group.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(group, text=title, bg=PANEL_2, fg=MUTED,
                     font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w")
            label = tk.Label(group, text="--", bg=PANEL_2, fg=TEXT,
                             font=("Consolas", 10, "bold"))
            label.pack(anchor="w")
            self.sim_status_labels[key] = label

        live = self._panel(self.simulation_tab, "現在碗走到哪裡（不用切回流程總覽）")
        live.pack(fill="x", pady=6)
        station_row = tk.Frame(live, bg=PANEL)
        station_row.pack(fill="x", padx=10, pady=(0, 6))
        self.sim_live_station_frames = []
        self.sim_live_station_labels = []
        for number, name in enumerate(("落碗", "放麵／UR1", "UR2", "注湯／完成"), 1):
            frame = tk.Frame(
                station_row, bg=PANEL_2,
                highlightbackground="#40515e", highlightthickness=1,
            )
            frame.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(frame, text=f"{number}. {name}", bg=PANEL_2, fg=MUTED,
                     font=("Microsoft JhengHei UI", 10, "bold")).pack(pady=(7, 2))
            label = tk.Label(frame, text="空閒", bg=PANEL_2, fg=GREEN,
                             font=("Consolas", 10, "bold"))
            label.pack(pady=(0, 7))
            self.sim_live_station_frames.append(frame)
            self.sim_live_station_labels.append(label)
        self.sim_basket_summary = tk.Label(
            live, text="麵篩1：--　　麵篩2：--　　麵篩3：--",
            bg=PANEL, fg=TEXT, anchor="w",
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.sim_basket_summary.pack(fill="x", padx=14, pady=(0, 8))

        control_row = tk.Frame(self.simulation_tab, bg=BG)
        control_row.pack(fill="both", expand=True, pady=6)

        setup = self._panel(control_row, "1. 啟動模擬環境")
        setup.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.sim_mode_button = tk.Button(
            setup, text="開啟D8000.0模擬模式", command=self._toggle_simulation_mode,
            bg=BLUE, fg="white", relief="flat", bd=0, pady=8,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.sim_mode_button.pack(fill="x", padx=12, pady=5)
        self.peripheral_button = tk.Button(
            setup, text="啟動IPC／UR／Nachi模擬", command=self._toggle_peripheral,
            bg=BLUE, fg="white", relief="flat", bd=0, pady=8,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.peripheral_button.pack(fill="x", padx=12, pady=5)
        self.auto_mode_button = tk.Button(
            setup, text="PLC切換Auto模式", command=self._request_sim_auto_mode,
            bg=GREEN, fg="white", relief="flat", bd=0, pady=8,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.auto_mode_button.pack(fill="x", padx=12, pady=(5, 12))

        order = self._panel(control_row, "2. 送一筆PLC測試訂單")
        order.pack(side="left", fill="both", expand=True, padx=4)
        order_form = tk.Frame(order, bg=PANEL)
        order_form.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.sim_unit_id_var = tk.StringVar(value=str(30000000 + int(time.time()) % 999999))
        self.sim_cabinet_var = tk.StringVar(value="1")
        self.sim_firmness_var = tk.StringVar(value="正常 2")
        for row, (title, variable, values) in enumerate((
            ("UnitID", self.sim_unit_id_var, None),
            ("麵櫃", self.sim_cabinet_var, tuple(str(i) for i in range(1, 11))),
            # PLC FB_AutoScheduler定義：1=硬、2=正常、3=軟。
            # 顯示順序維持「軟、正常、硬」，但送入D1023的代碼必須依PLC定義。
            ("軟硬度", self.sim_firmness_var, ("軟 3", "正常 2", "硬 1")),
        )):
            tk.Label(order_form, text=title, bg=PANEL, fg=MUTED,
                     font=("Microsoft JhengHei UI", 9, "bold")).grid(
                         row=row, column=0, sticky="w", pady=4,
                     )
            if values is None:
                widget = tk.Entry(order_form, textvariable=variable,
                                  font=("Consolas", 11, "bold"))
            else:
                widget = ttk.Combobox(order_form, textvariable=variable,
                                      values=values, state="readonly")
            widget.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=4)
            if title == "麵櫃":
                self.sim_cabinet_combo = widget
                widget.bind("<<ComboboxSelected>>", lambda _event: self._refresh_quick_stock())
        order_form.grid_columnconfigure(1, weight=1)

        stock_row = tk.Frame(order_form, bg=PANEL)
        stock_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 2))
        tk.Label(stock_row, text="剩餘麵盒", bg=PANEL, fg=MUTED,
                 font=("Microsoft JhengHei UI", 9, "bold")).pack(side="left")
        self.sim_stock_label = tk.Label(
            stock_row, text="0 BOX", bg=PANEL, fg=YELLOW,
            font=("Consolas", 12, "bold"),
        )
        self.sim_stock_label.pack(side="left", padx=8)
        tk.Button(stock_row, text="－", command=lambda: self._adjust_quick_stock(-1),
                  bg="#40515e", fg="white", relief="flat", bd=0,
                  width=3, font=("Microsoft JhengHei UI", 10, "bold")).pack(side="right", padx=2)
        tk.Button(stock_row, text="＋", command=lambda: self._adjust_quick_stock(1),
                  bg="#40515e", fg="white", relief="flat", bd=0,
                  width=3, font=("Microsoft JhengHei UI", 10, "bold")).pack(side="right", padx=2)
        self.sim_order_button = tk.Button(
            order_form, text="送到PLC D1020～D1025", command=self._submit_sim_order,
            bg=GREEN, fg="white", relief="flat", bd=0, pady=8,
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.sim_order_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        station = self._panel(control_row, "3. 碗到站時依序按")
        station.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.sim_station_buttons = []
        for number, text in (
            (1, "① X0.1 落碗到位"),
            (2, "② X0.2 放麵／UR1"),
            (3, "③ X0.3 UR2"),
            (4, "④ X0.4 注湯／完成"),
            (0, "清除所有站點感測器"),
        ):
            button = tk.Button(
                station, text=text,
                command=lambda value=number: self._set_sim_station(value),
                bg=BLUE if number else RED, fg="white", relief="flat", bd=0,
                pady=6, font=("Microsoft JhengHei UI", 9, "bold"),
            )
            button.pack(fill="x", padx=12, pady=3)
            self.sim_station_buttons.append(button)

        self.sim_message_label = tk.Label(
            self.simulation_tab,
            text="操作順序：開模擬 → 啟動周邊 → 送訂單 → Auto → X0.1 → X0.2 → X0.3 → X0.4",
            bg="#1d2a33", fg=YELLOW, padx=12, pady=8, anchor="w",
            font=("Microsoft JhengHei UI", 10, "bold"),
        )
        self.sim_message_label.pack(fill="x", pady=(2, 8))

        if not is_simulation:
            for button in (
                self.sim_mode_button, self.peripheral_button,
                self.auto_mode_button, self.sim_order_button,
                self.sim_prepare_button, self.sim_quick_order_button,
                self.sim_next_button, self.sim_stop_button,
                *self.sim_station_buttons,
            ):
                button.configure(state="disabled", cursor="arrow")

        self._refresh_quick_stock()

    def _prepare_simulation(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        enabled = controller.set_enabled(True)
        peripheral = controller.start_peripheral()
        auto_requested = self.app.request_machine_mode(2)
        if enabled and peripheral and auto_requested:
            controller.last_message = "準備完成：現在按「送出一碗」"
        else:
            controller.last_message = "準備尚未完成，請查看上方紅色狀態"
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control(force=True)

    def _next_sim_station(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        status = controller.read_status()
        current = int(status["station"]) if status else 0
        controller.set_station(current + 1 if current < 4 else 0)
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control(force=True)

    def _stop_simulation(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        controller.set_station(0)
        controller.set_enabled(False)
        controller.stop_peripheral()
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control(force=True)

    def _refresh_quick_stock(self):
        try:
            cabinet_no = int(self.sim_cabinet_var.get())
            cabinet = self.app.auto_store.snapshot()["cabinets"][cabinet_no - 1]
            self.sim_stock_label.configure(
                text=f"{cabinet['quantity']} / {cabinet['capacity']} BOX",
                fg=GREEN if cabinet["quantity"] > 0 else RED,
            )
        except (ValueError, IndexError, AttributeError):
            return

    def _adjust_quick_stock(self, delta: int):
        try:
            cabinet_no = int(self.sim_cabinet_var.get())
        except ValueError:
            return
        state = self.app.auto_store.snapshot()
        cabinets = [(row["quantity"], row["capacity"]) for row in state["cabinets"]]
        bins = [(row["quantity"], row["capacity"]) for row in state["empty_box_bins"]]
        quantity, capacity = cabinets[cabinet_no - 1]
        cabinets[cabinet_no - 1] = (max(0, min(capacity, quantity + delta)), capacity)
        self.app.auto_store.update_inventory(cabinets, bins)
        self._last_signature = None
        self._refresh_quick_stock()

    def _toggle_simulation_mode(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        status = controller.read_status()
        controller.set_enabled(not bool(status and status["enabled"]))
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control()

    def _toggle_peripheral(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        if controller.peripheral_running:
            controller.stop_peripheral()
        else:
            controller.start_peripheral()
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control()

    def _request_sim_auto_mode(self):
        if self.app.simulation_controller is None:
            return
        if not self.app.request_machine_mode(2):
            self.app.simulation_controller.last_message = "Auto模式命令尚未接受，請查看PLC回覆"
        else:
            self.app.simulation_controller.last_message = "已要求PLC切換Auto模式"
        self._refresh_simulation_control(force=True)

    def _submit_sim_order(self):
        controller = self.app.simulation_controller
        if controller is None:
            return
        try:
            unit_id = int(self.sim_unit_id_var.get())
            cabinet_no = int(self.sim_cabinet_var.get())
            firmness_no = int(self.sim_firmness_var.get().rsplit(" ", 1)[-1])
            if unit_id <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("PLC測試訂單", "UnitID、麵櫃或軟硬度格式錯誤。", parent=self)
            return
        if controller.submit_order(unit_id, cabinet_no, firmness_no):
            self.sim_unit_id_var.set(str(unit_id + 1))
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control()

    def _set_sim_station(self, station: int):
        controller = self.app.simulation_controller
        if controller is None:
            return
        controller.set_station(station)
        self._last_simulation_poll = 0.0
        self._refresh_simulation_control()

    def _refresh_simulation_control(self, force: bool = False):
        controller = self.app.simulation_controller
        if controller is None:
            for label in self.sim_status_labels.values():
                label.configure(text="LOCKED", fg=RED)
            return
        now = time.monotonic()
        if not force and now - self._last_simulation_poll < 0.8:
            return
        self._last_simulation_poll = now
        status = controller.read_status()
        if status is None:
            self.sim_status_labels["plc"].configure(text="OFFLINE", fg=RED)
            self.sim_message_label.configure(text=controller.last_message, fg=RED)
            return
        self.sim_status_labels["plc"].configure(text="ONLINE", fg=GREEN)
        self.sim_status_labels["mode"].configure(
            text=f"{'ON' if status['enabled'] else 'OFF'} / 0x{status['simulation_word']:04X}",
            fg=GREEN if status["enabled"] else YELLOW,
        )
        self.sim_status_labels["peripheral"].configure(
            text="RUNNING" if status["peripheral_running"] else "STOPPED",
            fg=GREEN if status["peripheral_running"] else YELLOW,
        )
        self.sim_status_labels["fifo"].configure(text=str(status["fifo_count"]), fg=TEXT)
        self.sim_status_labels["ack"].configure(
            text=f"#{status['ack_index']} / {status['response_code']}", fg=TEXT,
        )
        self.sim_mode_button.configure(
            text="關閉模擬模式" if status["enabled"] else "開啟D8000.0模擬模式",
        )
        self.peripheral_button.configure(
            text=("停止IPC／UR／Nachi模擬"
                  if status["peripheral_running"] else "啟動IPC／UR／Nachi模擬"),
        )
        next_text = {
            0: "③ 下一步：落碗到位",
            1: "③ 下一步：放麵／UR1",
            2: "③ 下一步：UR2",
            3: "③ 下一步：注湯／完成",
            4: "③ 完成後清除站點",
        }
        self.sim_next_button.configure(text=next_text.get(status["station"], "③ 下一步"))
        self.sim_message_label.configure(text=controller.last_message, fg=YELLOW)

    def _refresh_simulation_flow(self, baskets, stations):
        if not hasattr(self, "sim_live_station_labels"):
            return
        for frame, label, station in zip(
            self.sim_live_station_frames, self.sim_live_station_labels, stations,
        ):
            unit_id = station.get("unit_id")
            active = unit_id is not None
            label.configure(
                text=(f"{station.get('state', '--')}\nUnit {unit_id}"
                      if active else "空閒"),
                fg=YELLOW if active else GREEN,
            )
            frame.configure(
                highlightbackground=YELLOW if active else "#40515e",
                highlightthickness=2 if active else 1,
            )
        parts = []
        for number, basket in enumerate(baskets, 1):
            unit_id = basket.get("unit_id")
            text = basket.get("state", "--")
            parts.append(
                f"麵篩{number}：{text}"
                + (f" / Unit {unit_id}" if unit_id is not None else "")
            )
        self.sim_basket_summary.configure(text="　　".join(parts))

    def _add_order(self):
        if self.app.runtime_profile == "field":
            messagebox.showwarning(
                "FIELD現場版", "現場訂單必須由手機／PLC正式通訊送入。",
                parent=self,
            )
            return
        try:
            unit_id = self.app.auto_store.add_order(int(self.cabinet_var.get()), self.firmness_var.get())
        except ValueError as exc:
            messagebox.showwarning("新增訂單", str(exc), parent=self)
            return
        messagebox.showinfo("新增訂單", f"已建立 UnitID {unit_id}\n目前保存在HMI本機FIFO。", parent=self)
        self._last_signature = None
        self.refresh()

    def _cancel_order(self):
        if self.app.runtime_profile == "field":
            messagebox.showwarning(
                "FIELD現場版", "現場版禁止操作HMI本機測試訂單。",
                parent=self,
            )
            return
        selected = self.order_tree.selection()
        if not selected:
            messagebox.showwarning("取消訂單", "請先選擇一筆等待中的訂單。", parent=self)
            return
        unit_id = int(self.order_tree.item(selected[0], "values")[0])
        if not self.app.auto_store.cancel_order(unit_id):
            messagebox.showwarning("取消訂單", "只有 Queued 訂單可以取消。", parent=self)
            return
        self._last_signature = None
        self.refresh()

    def _save_inventory(self):
        try:
            cabinets = [(int(q.get()), int(c.get())) for q, c in self.cabinet_vars]
            bins = [(int(q.get()), int(c.get())) for q, c in self.bin_vars]
            if any(q < 0 or c < 1 or q > c for q, c in cabinets + bins):
                raise ValueError
        except ValueError:
            messagebox.showerror("數量設定", "數量必須為0以上、容量至少1，且目前數量不可超過容量。", parent=self)
            return
        self.app.auto_store.update_inventory(cabinets, bins)
        self._last_signature = None
        self.refresh()
        messagebox.showinfo("數量設定", "麵櫃與空盒櫃資料已儲存在HMI本機。", parent=self)

    def _advance_demo(self):
        if self.app.runtime_profile == "field":
            messagebox.showwarning(
                "FIELD現場版", "現場版已鎖定，不能啟動本機模擬流程。",
                parent=self,
            )
            return
        message = self.app.auto_store.advance_demo()
        self._last_signature = None
        self.refresh()
        messagebox.showinfo("本機流程模擬", message, parent=self)

    def refresh(self):
        self._refresh_plc_debug_logs()
        self._refresh_auto_stress()
        self._refresh_simulation_control()
        state = self.app.auto_store.snapshot()
        is_field = self.app.runtime_profile == "field"
        live = self.app.snapshot.get("auto_live") if self.app.snapshot.get("online") else None
        signature = repr((state, live, self.app.snapshot.get("online"), is_field))
        if signature == self._last_signature:
            return
        self._last_signature = signature

        if live:
            display_baskets = live["baskets"]
            display_stations = live["stations"]
        elif is_field:
            display_baskets = [
                {"unit_id": None, "cabinet_no": None, "state": "PLC離線",
                 "state_no": 0, "exact": False}
                for _ in range(3)
            ]
            display_stations = [
                {"unit_id": None, "state": "PLC離線", "exact": False}
                for _ in range(4)
            ]
        else:
            display_baskets = state["baskets"]
            display_stations = state["stations"]

        self._refresh_simulation_flow(display_baskets, display_stations)

        for label, basket in zip(self.basket_labels, display_baskets):
            unit = "--" if basket["unit_id"] is None else basket["unit_id"]
            cabinet = "--" if basket["cabinet_no"] is None else basket["cabinet_no"]
            state_text = basket["state"]
            state_no = basket.get("state_no")
            state_prefix = f"State {state_no}  " if state_no is not None else ""
            label.configure(
                text=f"{state_prefix}{state_text}\nUnit: {unit}  Cabinet: {cabinet}",
                fg=GREEN if state_no == 0 or state_text in ("Idle", "空閒") else YELLOW,
            )
        for frame, label, station in zip(self.station_frames, self.station_labels, display_stations):
            unit = "--" if station["unit_id"] is None else station["unit_id"]
            active = station["unit_id"] is not None
            color = YELLOW if active else GREEN
            exact_mark = (
                "  約略"
                if station["unit_id"] is not None and not station.get("exact", True)
                else ""
            )
            label.configure(
                text=f"{station['state']}\nUnit: {unit}{exact_mark}", fg=color,
            )
            frame.configure(highlightbackground=YELLOW if active else "#40515e",
                            highlightthickness=2 if active else 1)

        if live:
            self.live_summary_labels["fifo"].configure(text=str(live["fifo_count"]))
            self.live_summary_labels["rightmost"].configure(
                text=str(live["rightmost_station"]),
            )
            self.live_summary_labels["complete_unit"].configure(
                text=str(live["complete_unit_id"] or "--"),
            )
            self.live_summary_labels["complete_index"].configure(
                text=str(live["complete_index"]),
            )
            active = live.get("active", {})
            robot = self.app.snapshot.get("robot")
            nachi_action = getattr(robot, "action_no", 0) if robot is not None else 0
            if active.get("noodle_busy"):
                nachi_text = f"執行中／Action {nachi_action or '--'}"
            elif active.get("robot_idle"):
                nachi_text = "Idle"
            else:
                nachi_text = "等待回原點"
            ur1_text = "動作中" if active.get("ur1_active") else "等待／完成"
            ur2_text = "動作中" if active.get("ur2_active") else "等待／完成"
            conveyor_text = f"最右端 State {live['rightmost_station']}"
            for key, text in (
                ("nachi", nachi_text), ("ur1", ur1_text),
                ("ur2", ur2_text), ("conveyor", conveyor_text),
            ):
                self.resource_labels[key].configure(
                    text=text,
                    fg=YELLOW if "動作中" in text or "執行中" in text else TEXT,
                )
            source_note = (
                "四站與三麵篩 UnitID 皆為PLC精確值"
                if live["precise"]
                else "目前精確顯示FIFO最前端碗；加入D8100監看區後可同時顯示所有碗"
            )
            if live.get("available", True):
                edition = "FIELD" if is_field else "SIMULATION"
                self.mapping_banner.configure(
                    text=(f"{edition} PLC LIVE｜{live['source']}｜"
                          f"更新 {live['read_at']}｜{source_note}"),
                    bg="#173d32", fg=GREEN,
                )
            else:
                self.mapping_banner.configure(
                    text="FIELD｜PLC已連線，但D8100正式監看區尚未配置；不顯示模擬資料",
                    bg="#5a251f", fg=YELLOW,
                )
            self.demo_button.configure(
                text=("FIELD｜禁止模擬" if is_field else "SIMULATION PLC 即時監看"),
                state="disabled", cursor="arrow",
            )
        else:
            for label in self.live_summary_labels.values():
                label.configure(text="--")
            for label in self.resource_labels.values():
                label.configure(text="--", fg=MUTED)
            if is_field:
                self.mapping_banner.configure(
                    text="FIELD｜PLC離線；不顯示、不寫入任何模擬資料",
                    bg="#5a251f", fg=YELLOW,
                )
                self.demo_button.configure(
                    text="FIELD｜禁止模擬", state="disabled", cursor="arrow",
                )
            else:
                self.mapping_banner.configure(
                    text="SIMULATION｜PLC離線／Mock：目前顯示HMI本機資料",
                    bg="#4a3b18", fg=YELLOW,
                )
                self.demo_button.configure(
                    text="本機模擬推進（不寫PLC）", state="normal", cursor="hand2",
                )

        field_button_state = "disabled" if is_field else "normal"
        field_cursor = "arrow" if is_field else "hand2"
        self.add_order_button.configure(state=field_button_state, cursor=field_cursor)
        self.cancel_order_button.configure(state=field_button_state, cursor=field_cursor)
        self.save_inventory_button.configure(state=field_button_state, cursor=field_cursor)

        for item in self.order_tree.get_children():
            self.order_tree.delete(item)
        for order in state["orders"]:
            self.order_tree.insert("", "end", values=(
                order["unit_id"], order["created_at"].replace("T", " "),
                order["cabinet_no"], order["firmness"], order.get("basket_no", "--"), order["status"],
            ))

        inventory_signature = repr((state["cabinets"], state["empty_box_bins"]))
        inventory_changed = inventory_signature != self._last_inventory_signature
        if inventory_changed:
            self._last_inventory_signature = inventory_signature
            for index, cabinet in enumerate(state["cabinets"]):
                self.cabinet_vars[index][0].set(str(cabinet["quantity"]))
                self.cabinet_vars[index][1].set(str(cabinet["capacity"]))
            for index, row in enumerate(state["empty_box_bins"]):
                self.bin_vars[index][0].set(str(row["quantity"]))
                self.bin_vars[index][1].set(str(row["capacity"]))
        self.total_noodle_label.configure(
            text=f"生麵盒合計：{sum(row['quantity'] for row in state['cabinets'])} BOX"
        )
        self.total_empty_label.configure(
            text=f"空盒合計：{sum(row['quantity'] for row in state['empty_box_bins'])} BOX"
        )
        if inventory_changed:
            self._load_selected_inventory()
            self._refresh_quick_stock()
        self._schedule_cabinet_render()

        if not live and not is_field:
            mapped = assigned_count()
            self.mapping_banner.configure(
                text=(
                    f"PLC離線／Mock｜通訊契約已配置 {mapped}/{len(AUTO_PLC_FIELDS)}；"
                    "目前使用HMI本機資料"
                )
            )
