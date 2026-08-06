"""Compact process controls embedded on the right side of MainPage."""

import tkinter as tk
from tkinter import messagebox

from process_flow_widget import ProcessFlowWidget
from process_models import AUTO_DEFAULTS, PROCESS_ALARM, PROCESS_RUNNING, validate_auto_recipe
from ui_common import BG, PANEL, PANEL_2, TEXT, MUTED, GREEN, RED, BLUE, button_style


SEMI_PARAMETER = {
    1: ("煮麵秒數 / Cook Time (s)", "cook_time_sec", 180),
    2: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
    5: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
    7: ("輸送帶轉速 / Conveyor Speed (RPM)", "conveyor_speed_rpm", 150),
}


class ProcessOverviewPanel(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=PANEL, width=570,
                         highlightbackground="#40515e", highlightthickness=1)
        self.app = app
        self.pack_propagate(False)
        self.selected_step = tk.IntVar(value=1)
        self.auto_speed = tk.StringVar(value=str(AUTO_DEFAULTS["conveyor_speed_rpm"]))
        self.auto_cook_time = tk.StringVar(value=str(AUTO_DEFAULTS["cook_time_sec"]))

        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(header, text="LIVE RAMEN PROCESS", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.status_label = tk.Label(header, text="IDLE", bg=PANEL, fg=MUTED,
                                     font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="right")

        self.body = tk.Frame(self, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=8, pady=4)

        self.flow = ProcessFlowWidget(self.body)
        self.flow.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.parameter_area = tk.Frame(self.body, bg=PANEL_2, width=205)
        self.parameter_area.pack(side="right", fill="y", padx=(6, 0))
        self.parameter_area.pack_propagate(False)
        self._render_parameters()

        self.alarm_label = tk.Label(
            self, text="No Active Process Alarm", bg=PANEL, fg=GREEN,
            anchor="w", justify="left", font=("Microsoft JhengHei UI", 9, "bold"),
        )
        self.alarm_label.pack(fill="x", padx=12, pady=(3, 8))

    def _entry_row(self, parent, row, label, variable):
        row_frame = tk.Frame(parent, bg=PANEL_2)
        row_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        tk.Label(row_frame, text=label, bg=PANEL_2, fg=MUTED, anchor="w",
                 font=("Microsoft JhengHei UI", 9)).pack(fill="x", pady=(0, 3))
        entry = tk.Entry(row_frame, textvariable=variable, bg="#edf1f4", fg="#17232d",
                         relief="flat", font=("Segoe UI", 10))
        entry.pack(fill="x")
        parent.grid_columnconfigure(0, weight=1)
        return entry

    def _render_parameters(self):
        for child in self.parameter_area.winfo_children():
            child.destroy()
        self.parameter_entries = []
        mode = self.app.machine_mode
        if True:  # This panel is exposed only in Auto mode.
            tk.Label(self.parameter_area, text="AUTO PARAMETERS", bg=PANEL_2, fg=TEXT,
                     font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 1, "輸送帶轉速 / Conveyor Speed (RPM)", self.auto_speed,
            ))
            self.parameter_entries.append(self._entry_row(
                self.parameter_area, 2, "煮麵秒數 / Cook Time (s)", self.auto_cook_time,
            ))
            self.action_button = tk.Button(
                self.parameter_area, text="WRITE PARAMETERS", command=self._write_parameters,
                **button_style(GREEN),
            )
            self.action_button.grid(row=3, column=0, columnspan=2, sticky="e", padx=8, pady=7)
        else:
            tk.Label(self.parameter_area, text="SEMI-AUTO STEP", bg=PANEL_2, fg=TEXT,
                     font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(7, 2))
            definition = SEMI_PARAMETER.get(self.selected_step.get())
            if definition:
                label, _key, default = definition
                if not self.semi_value.get():
                    self.semi_value.set(str(default))
                self.parameter_entries.append(self._entry_row(
                    self.parameter_area, 1, label, self.semi_value,
                ))
                button_row = 2
            else:
                tk.Label(self.parameter_area, text="No parameters required for this step",
                         bg=PANEL_2, fg=MUTED, font=("Microsoft JhengHei UI", 9)).grid(
                    row=1, column=0, columnspan=2, padx=10, pady=12,
                )
                button_row = 2
            self.action_button = tk.Button(
                self.parameter_area, text="EXECUTE SELECTED STEP",
                command=self._execute_semi, **button_style(BLUE),
            )
            self.action_button.grid(row=button_row, column=0, columnspan=2, sticky="e", padx=8, pady=7)

    def _select_step(self, step_id):
        self.selected_step.set(step_id)
        definition = SEMI_PARAMETER.get(step_id)
        self.semi_value.set(str(definition[2]) if definition else "")
        self._render_parameters()

    def _write_parameters(self):
        data = {
            "conveyor_speed_rpm": self.auto_speed.get(),
            "cook_time_sec": self.auto_cook_time.get(),
        }
        errors = validate_auto_recipe(data)
        if errors:
            messagebox.showerror("WRITE PARAMETERS", "\n".join(errors), parent=self)
            return
        ok, message = self.app.write_auto_parameters(data)
        (messagebox.showinfo if ok else messagebox.showwarning)("WRITE PARAMETERS", message, parent=self)

    def _execute_semi(self):
        step = self.selected_step.get()
        definition = SEMI_PARAMETER.get(step)
        params = {definition[1]: self.semi_value.get()} if definition else {}
        errors = validate_semi_parameters(step, params)
        if errors:
            messagebox.showerror("SEMI AUTO", "\n".join(errors), parent=self)
            return
        ok, message = self.app.start_semi_process(step, params)
        (messagebox.showinfo if ok else messagebox.showwarning)("SEMI AUTO", message, parent=self)

    def refresh(self):
        process = self.app.snapshot.get("process")
        if process is None:
            return
        mode = self.app.machine_mode
        expected_mode = getattr(self, "_rendered_mode", None)
        if expected_mode != mode:
            self._rendered_mode = mode
            self._render_parameters()
        self.flow.set_state(
            process, mode, self.app.snapshot.get("online", False),
            self.selected_step.get(),
        )
        self.status_label.configure(
            text=f"{process.step:02d} · {process.status}",
            fg=RED if process.status == PROCESS_ALARM else BLUE if process.status == PROCESS_RUNNING else GREEN,
        )
        locked = process.status in (PROCESS_RUNNING, PROCESS_ALARM) or bool(self.app.active_alarms)
        for entry in self.parameter_entries:
            entry.configure(state="disabled" if locked else "normal")
        self.action_button.configure(state="disabled" if locked else "normal")
        if process.alarm.latched:
            self.alarm_label.configure(
                text=f"ALARM {process.alarm.code} · {process.alarm.source}\n{process.alarm.message}", fg=RED,
            )
        else:
            self.alarm_label.configure(text="No Active Process Alarm", fg=GREEN)
