"""Process UI models and validation. No PLC addresses are defined here."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


PROCESS_STEPS = (
    (0, "等待點餐"),
    (10, "煮麵＋出碗"),
    (20, "暫停點一"),
    (30, "放麵"),
    (40, "UR1小料"),
    (50, "暫停點二"),
    (60, "UR2小料"),
    (70, "停止點"),
    (80, "注湯"),
    (90, "完成"),
)

SEMI_AUTO_STEPS = (
    (1, "煮麵＋出碗"),
    (2, "輸送帶到暫停點一"),
    (3, "放麵"),
    (4, "UR1放小料"),
    (5, "輸送帶到暫停點二"),
    (6, "UR2放小料"),
    (7, "輸送帶到停止點"),
    (8, "注湯"),
)

PROCESS_IDLE = "Idle"
PROCESS_WAITING = "Waiting"
PROCESS_RUNNING = "Running"
PROCESS_COMPLETE = "Complete"
PROCESS_REJECTED = "Rejected"
PROCESS_ALARM = "Alarm"


@dataclass
class ProcessAlarm:
    step: int = 0
    source: str = "--"
    message: str = "No Active Process Alarm"
    code: int = 0
    suggestion: str = "--"
    occurred_at: datetime | None = None
    latched: bool = False


@dataclass
class ProcessSnapshot:
    step: int = 0
    status: str = PROCESS_IDLE
    recipe_name: str = "--"
    mode: int = 0
    recipe_snapshot: dict[str, Any] | None = None
    alarm: ProcessAlarm = field(default_factory=ProcessAlarm)
    mapping_ready: bool = False


AUTO_DEFAULTS = {
    "conveyor_speed_rpm": 300,
    "cook_time_sec": 180,
}


def _integer(data: dict, key: str, low: int, high: int, label: str, errors: list[str]):
    try:
        value = int(data[key])
    except (KeyError, TypeError, ValueError):
        errors.append(f"{label} must be an integer")
        return
    if not low <= value <= high:
        errors.append(f"{label} range: {low}–{high}")


def validate_auto_recipe(data: dict) -> list[str]:
    errors: list[str] = []
    for key, low, high, label in (
        ("conveyor_speed_rpm", 1, 65535, "Conveyor speed"),
        ("cook_time_sec", 1, 65535, "Cook time"),
    ):
        _integer(data, key, low, high, label, errors)
    return errors


def validate_semi_parameters(step_id: int, data: dict) -> list[str]:
    errors: list[str] = []
    fields = {
        1: (("cook_time_sec", 1, 65535, "Cook time"),),
        2: (("conveyor_speed_rpm", 1, 65535, "Conveyor speed"),),
        3: (),
        4: (),
        5: (("conveyor_speed_rpm", 1, 65535, "Conveyor speed"),),
        6: (),
        7: (("conveyor_speed_rpm", 1, 65535, "Conveyor speed"),),
        8: (),
    }
    if step_id not in fields:
        return ["Invalid semi-auto step"]
    for key, low, high, label in fields[step_id]:
        _integer(data, key, low, high, label, errors)
    return errors


def lock_recipe(data: dict) -> dict:
    """Return a detached recipe for the current bowl."""
    return deepcopy(data)


def process_step_visual_role(current_step: int, status: str, step: int) -> str:
    """Return the color role used by the live process diagram."""
    ordered = [number for number, _name in PROCESS_STEPS]
    current_index = ordered.index(current_step) if current_step in ordered else 0
    index = ordered.index(step)
    if status == PROCESS_ALARM and step == current_step:
        return "alarm"
    if status == PROCESS_RUNNING and step == current_step:
        return "running"
    if index < current_index or (status == PROCESS_COMPLETE and index <= current_index):
        return "complete"
    if step == current_step and status in (PROCESS_IDLE, PROCESS_WAITING, PROCESS_REJECTED):
        return "waiting"
    return "pending"
