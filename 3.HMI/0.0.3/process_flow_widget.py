"""Responsive top-to-bottom process diagram for the ramen production flow."""

from __future__ import annotations

import time
import tkinter as tk

from process_models import (
    PROCESS_ALARM,
    PROCESS_COMPLETE,
    PROCESS_RUNNING,
    PROCESS_STEPS,
    process_step_visual_role,
)
from ui_common import PANEL, PANEL_2, TEXT, MUTED, GREEN, RED, YELLOW, BLUE, GRAY


OFFLINE = "#343f47"
ARROW_PENDING = "#596975"
NODE_ORDER = tuple(step for step, _name in PROCESS_STEPS)
STEP_NAMES = dict(PROCESS_STEPS)
STEP_TO_SEMI_ID = {step: step // 10 for step in range(10, 90, 10)}


class ProcessFlowWidget(tk.Frame):
    """Canvas diagram; node selection never sends a PLC command."""

    def __init__(self, parent, on_semi_select=None):
        super().__init__(parent, bg=PANEL, height=390)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(
            self, bg=PANEL, bd=0, highlightthickness=0, height=390,
        )
        self.canvas.pack(fill="both", expand=True)
        self.on_semi_select = on_semi_select
        self.process = None
        self._process_signature = None
        self.mode = "Manual"
        self.online = False
        self.selected_semi_step = 1
        self.selected_steps = set()
        self.completed_steps = set()
        self.blocked_steps = set()
        self.semi_running = False
        self.suppress_process_alarm = False
        self.sensor_status_word = 0
        self._blink = True
        self._resize_job = None
        self._blink_job = self.after(450, self._toggle_blink)
        self.canvas.bind("<Configure>", self._schedule_redraw)

    def _schedule_redraw(self, _event=None):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(160, self._redraw_after_resize)

    def _redraw_after_resize(self):
        self._resize_job = None
        self.redraw()

    def set_state(
        self, process, mode: str, online: bool, selected_semi_step: int,
        selected_steps=None, completed_steps=None, semi_running=False,
        suppress_process_alarm=False, sensor_status_word=0, blocked_steps=None,
    ):
        alarm = getattr(process, "alarm", None)
        process_signature = (
            getattr(process, "step", None),
            getattr(process, "status", None),
            getattr(alarm, "latched", False),
            getattr(alarm, "step", None),
            getattr(alarm, "code", None),
        )
        changed = (
            process_signature != self._process_signature
            or mode != self.mode
            or bool(online) != self.online
            or selected_semi_step != self.selected_semi_step
            or set(selected_steps or ()) != self.selected_steps
            or set(completed_steps or ()) != self.completed_steps
            or set(blocked_steps or ()) != self.blocked_steps
            or bool(semi_running) != self.semi_running
            or bool(suppress_process_alarm) != self.suppress_process_alarm
            or int(sensor_status_word or 0) != self.sensor_status_word
        )
        self.process = process
        self._process_signature = process_signature
        self.mode = mode
        self.online = bool(online)
        self.selected_semi_step = selected_semi_step
        self.selected_steps = set(selected_steps or ())
        self.completed_steps = set(completed_steps or ())
        self.blocked_steps = set(blocked_steps or ())
        self.semi_running = bool(semi_running)
        self.suppress_process_alarm = bool(suppress_process_alarm)
        self.sensor_status_word = int(sensor_status_word or 0)
        if changed:
            self.redraw()

    def _toggle_blink(self):
        self._blink = not self._blink
        self.redraw()
        self._blink_job = self.after(450, self._toggle_blink)

    def _node_role(self, step: int) -> str:
        if not self.online or self.process is None:
            return "offline"
        if self.mode == "Semi Auto":
            if step in self.blocked_steps and not self.semi_running:
                return "blocked"
            if (
                self.process.status == PROCESS_ALARM
                and not self.suppress_process_alarm
                and self.semi_running
                and self.process.step == step
                and step in self.selected_steps
            ):
                return "alarm"
            if self.semi_running and self.process.step == step and step in self.selected_steps:
                return "running"
            if step in self.selected_steps and not self.semi_running:
                return "selected"
            if step in self.completed_steps:
                return "complete"
            return "pending"
        role = process_step_visual_role(self.process.step, self.process.status, step)
        if (
            self.mode == "Semi Auto"
            and self.process.status not in (PROCESS_RUNNING, PROCESS_ALARM)
            and STEP_TO_SEMI_ID.get(step) == self.selected_semi_step
        ):
            return "selected"
        return role

    def _role_colors(self, role: str):
        if role == "alarm":
            return (RED if self._blink else PANEL_2, RED, TEXT)
        if role == "running":
            return (BLUE if self._blink else PANEL_2, BLUE, TEXT)
        if role == "complete":
            return (GREEN, GREEN, TEXT)
        if role in ("waiting", "selected"):
            return (YELLOW if role == "waiting" else PANEL_2, YELLOW, TEXT)
        if role == "offline":
            return (OFFLINE, "#48545c", "#77838b")
        if role == "blocked":
            return (PANEL_2, RED, MUTED)
        return ("#43515c", GRAY, "#b2c0c9")

    def _arrow_color(self, source: int, target: int) -> str:
        if not self.online or self.process is None:
            return OFFLINE
        current = self.process.step
        status = self.process.status
        if self.mode == "Semi Auto":
            if (
                status == PROCESS_ALARM
                and not self.suppress_process_alarm
                and self.semi_running
                and current in self.selected_steps
                and current in (source, target)
            ):
                return RED if self._blink else ARROW_PENDING
            if self.semi_running and current in (source, target):
                return BLUE if self._blink else ARROW_PENDING
            if source in self.completed_steps and target in self.completed_steps:
                return GREEN
            return ARROW_PENDING
        if status == PROCESS_ALARM and current in (source, target):
            return RED if self._blink else ARROW_PENDING
        if status == PROCESS_RUNNING and current in (source, target):
            return BLUE if self._blink else ARROW_PENDING
        current_index = NODE_ORDER.index(current) if current in NODE_ORDER else 0
        target_index = NODE_ORDER.index(target)
        if target_index < current_index:
            return GREEN
        if status == PROCESS_COMPLETE and target_index <= current_index:
            return GREEN
        return ARROW_PENDING

    def redraw(self):
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 260)
        height = max(canvas.winfo_height(), 360)
        margin_y = 6
        arrow_gap = max(5, min(9, height * 0.018))
        node_height = max(
            28,
            min(38, (height - 2 * margin_y - 9 * arrow_gap) / 10),
        )
        node_width = max(190, min(width - 34, 360))
        node_x = (width - node_width) / 2
        positions = {
            step: (node_x, margin_y + index * (node_height + arrow_gap))
            for index, step in enumerate(NODE_ORDER)
        }

        # Draw arrows first so nodes remain visually dominant.
        for source, target in zip(NODE_ORDER, NODE_ORDER[1:]):
            sx, sy = positions[source]
            tx, ty = positions[target]
            points = (
                sx + node_width / 2, sy + node_height,
                tx + node_width / 2, ty,
            )
            canvas.create_line(
                *points, fill=self._arrow_color(source, target), width=4,
                arrow=tk.LAST, arrowshape=(12, 14, 6),
            )

        for step in NODE_ORDER:
            x, y = positions[step]
            role = self._node_role(step)
            fill, outline, foreground = self._role_colors(role)
            tag = f"step_{step}"
            canvas.create_rectangle(
                x, y, x + node_width, y + node_height,
                fill=fill, outline=outline,
                width=3 if role in ("selected", "blocked") else 2,
                tags=(tag, "process_node"),
            )
            status_text = {
                "offline": "PLC離線", "alarm": "ALARM", "running": "RUNNING",
                "complete": "COMPLETE", "waiting": "WAITING",
                "selected": "SELECTED", "pending": "PENDING",
                "blocked": "ALM LOCKED",
            }.get(role, role.upper())
            canvas.create_text(
                x + 10, y + node_height / 2,
                text=f"{step:02d}  {STEP_NAMES[step]}\n{status_text}",
                anchor="w", fill=foreground,
                font=("Microsoft JhengHei UI", 8, "bold"), tags=(tag,),
            )
            selectable = (
                self.online and self.mode == "Semi Auto"
                and step in STEP_TO_SEMI_ID
                and self.process is not None
                and not self.semi_running
                and step not in self.blocked_steps
            )
            if selectable:
                canvas.tag_bind(tag, "<Button-1>", lambda _e, s=step: self._select_step(s))
                canvas.tag_bind(tag, "<Enter>", lambda _e: canvas.configure(cursor="hand2"))
                canvas.tag_bind(tag, "<Leave>", lambda _e: canvas.configure(cursor=""))

        if not self.online:
            canvas.create_text(
                width / 2, height / 2, text="PLC OFFLINE",
                fill=RED, font=("Segoe UI", 18, "bold"),
            )

    def _select_step(self, process_step: int):
        step_id = STEP_TO_SEMI_ID[process_step]
        self.selected_semi_step = step_id
        if self.on_semi_select is not None:
            self.on_semi_select(process_step)
        self.redraw()

    def destroy(self):
        if self._blink_job is not None:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        super().destroy()
