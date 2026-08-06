"""無 PLC 時用於 UI 測試的記憶體 client。"""
from __future__ import annotations

from datetime import datetime
import threading
import time

from process_models import (
    PROCESS_ALARM,
    PROCESS_COMPLETE,
    PROCESS_IDLE,
    PROCESS_RUNNING,
    PROCESS_STEPS,
    ProcessAlarm,
    ProcessSnapshot,
    lock_recipe,
)

from register_map import (
    CMD_MODE_AUTO,
    CMD_MODE_MANUAL,
    CMD_SMALL_MATERIAL_FIRST,
    CMD_SMALL_MATERIAL_LAST,
    MACHINE_MODE_AUTO,
    MACHINE_MODE_MANUAL,
    PLC_CMD_ACK_INDEX,
    PLC_CMD_RESPONSE_CODE,
    PLC_MACHINE_MODE,
    UR_IPC_HEARTBEAT_RETURN,
    PLC_IPC_COMM_NORMAL,
    PLC_IPC_HEARTBEAT_INDEX,
    ROBOT_MANUAL_INTERNAL_END,
    ROBOT_MANUAL_INTERNAL_START,
    ROBOT_READ_ONLY_END,
    ROBOT_READ_ONLY_START,
)


class MockHMIPlcClient:
    def __init__(self, ip: str = "MOCK", **_kwargs) -> None:
        self.ip = ip
        self.port = 502
        self.slave_id = 1
        self.connected = False
        self.last_error = None
        self.lock = threading.RLock()
        self.last_read_time = None
        self.last_write_time = None
        self.reject_mode_changes = False
        self.reject_process_commands = False
        self.staged_auto_recipe = None
        self.process = ProcessSnapshot(mapping_ready=True)
        self._process_started_at = 0.0
        self._process_kind = None
        self._semi_step = 0
        self.registers = {101: 0, 102: 24, 103: 150, 104: 10, 105: 10,
                          106: 50, 107: 50, 108: 150, 109: 10, 110: 10,
                          111: 50, 112: 50, 1105: 1, 1107: 0, 1110: 0,
                          1004: 0, 1108: 0, PLC_MACHINE_MODE: MACHINE_MODE_MANUAL,
                          1120: 0, 1121: 0, 1122: 0, 1123: 0, 1124: 1,
                          12100: 0x0006, 12150: 0}
        self.registers.update({
            PLC_IPC_HEARTBEAT_INDEX: 0,
            PLC_IPC_COMM_NORMAL: 1,
            UR_IPC_HEARTBEAT_RETURN: 1,
        })

    def connect(self) -> bool:
        self.connected = True
        self.last_error = None
        return True

    def reconnect(self) -> bool:
        return self.connect()

    def close(self) -> None:
        self.connected = False

    def read_d(self, address: int, count: int = 1):
        if not self.connected:
            self.last_error = "Mock PLC 尚未連線"
            return None
        if address == 1100:
            self.registers[1100] = (self.registers.get(1100, 0) + 1) & 0xFFFF
        self.last_read_time = datetime.now()
        return [self.registers.get(address + i, 0) for i in range(count)]

    def get_process_snapshot(self) -> ProcessSnapshot:
        """Advance and return the Mock-only process simulation."""
        if self.process.status == PROCESS_RUNNING:
            elapsed = time.monotonic() - self._process_started_at
            if self._process_kind == "auto":
                index = min(int(elapsed / 1.0) + 1, len(PROCESS_STEPS) - 1)
                self.process.step = PROCESS_STEPS[index][0]
                if index == len(PROCESS_STEPS) - 1:
                    self.process.status = PROCESS_COMPLETE
                    self._process_kind = None
            elif self._process_kind == "semi" and elapsed >= 1.5:
                self.process.status = PROCESS_COMPLETE
                self._process_kind = None
        return self.process

    def start_auto_process(self, recipe: dict) -> tuple[bool, str]:
        if self.reject_process_commands:
            self.process.status = "Rejected"
            return False, "PLC rejected automatic start"
        if self.process.status in (PROCESS_RUNNING, PROCESS_ALARM):
            return False, "Process is busy or alarmed"
        self.process = ProcessSnapshot(
            step=10, status=PROCESS_RUNNING, recipe_name="Auto Ramen",
            mode=MACHINE_MODE_AUTO, recipe_snapshot=lock_recipe(recipe),
            mapping_ready=True,
        )
        self._process_started_at = time.monotonic()
        self._process_kind = "auto"
        return True, "Automatic process accepted"

    def write_auto_parameters(self, recipe: dict) -> tuple[bool, str]:
        """Mock parameter acceptance only; this does not start production."""
        if self.reject_process_commands:
            return False, "PLC rejected automatic parameters"
        self.staged_auto_recipe = lock_recipe(recipe)
        self.registers[108] = int(recipe["conveyor_speed_rpm"]) & 0xFFFF
        return True, "Automatic parameters accepted"

    def start_semi_process(self, step_id: int, params: dict) -> tuple[bool, str]:
        if self.reject_process_commands:
            self.process.status = "Rejected"
            return False, "PLC rejected semi-auto step"
        if self.process.status in (PROCESS_RUNNING, PROCESS_ALARM):
            return False, "Process is busy or alarmed"
        self.process = ProcessSnapshot(
            step=step_id * 10, status=PROCESS_RUNNING,
            recipe_name=f"Semi Step {step_id}", mode=MACHINE_MODE_SEMI_AUTO,
            recipe_snapshot=lock_recipe(params), mapping_ready=True,
        )
        self._semi_step = step_id
        self._process_started_at = time.monotonic()
        self._process_kind = "semi"
        return True, "Semi-auto step accepted"

    def inject_process_alarm(self, source="Conveyor", code=501):
        self.process.status = PROCESS_ALARM
        self.process.alarm = ProcessAlarm(
            step=self.process.step, source=source,
            message="Mock device fault", code=code,
            suggestion="Check device condition, then press ALM RST",
            occurred_at=datetime.now(), latched=True,
        )
        self._process_kind = None

    def reset_process_alarm(self):
        if self.process.alarm.latched:
            self.process.status = PROCESS_IDLE
            self.process.step = 0
            self.process.alarm = ProcessAlarm()

    def write_d(self, address: int, value: int) -> bool:
        if ROBOT_READ_ONLY_START <= address <= ROBOT_READ_ONLY_END:
            raise ValueError("Robot D12100~D12156 registers are read-only from HMI side")
        if ROBOT_MANUAL_INTERNAL_START <= address <= ROBOT_MANUAL_INTERNAL_END:
            raise ValueError("Robot D3080~D3093 registers are PLC-internal and HMI write is forbidden")
        if not self.connected:
            return False
        self.registers[address] = int(value) & 0xFFFF
        if address == 1004 and (self.registers[address] & 0x0001):
            # PLC EMC status remains latched after the HMI request returns OFF.
            self.registers[1108] = self.registers.get(1108, 0) | 0x0001
            self.inject_process_alarm(source="EMC", code=900)
        # 模擬 PLC 接收命令後更新實際速度，供主頁展示 Ready / Running。
        if address == 1002 and self.registers[address] == 1:
            command = self.registers.get(1000, 0)
            mode_commands = {
                CMD_MODE_MANUAL: (MACHINE_MODE_MANUAL, 300),
                CMD_MODE_AUTO: (MACHINE_MODE_AUTO, 301),
            }
            if command in mode_commands:
                self.registers[PLC_CMD_ACK_INDEX] = self.registers.get(1001, 0)
                if self.reject_mode_changes:
                    self.registers[PLC_CMD_RESPONSE_CODE] = 430
                else:
                    mode, response = mode_commands[command]
                    self.registers[PLC_MACHINE_MODE] = mode
                    self.registers[PLC_CMD_RESPONSE_CODE] = response
            elif command == 6:
                self.registers[1108] = self.registers.get(1108, 0) & ~0x0001
                self.reset_process_alarm()
            elif command == 10:
                self.registers[101] = self.registers.get(1003, 0)
            elif command == 11:
                self.registers[101] = 0
            elif command == 40:
                self.registers[1120] = 3
                self.registers[1121] = self.registers.get(1001, 0)
                self.registers[1122] = 200
                self.registers[1123] = 0
            elif command in (CMD_SMALL_MATERIAL_FIRST, CMD_SMALL_MATERIAL_LAST):
                self.registers[PLC_CMD_ACK_INDEX] = self.registers.get(1001, 0)
                self.registers[PLC_CMD_RESPONSE_CODE] = (
                    250 if command == CMD_SMALL_MATERIAL_FIRST else 251
                )
        self.last_write_time = datetime.now()
        return True

    def simulate_ur_ipc_heartbeat(self) -> None:
        """Simulate the external UR IPC; HMI itself never writes D1300."""
        plc_index = (self.registers.get(PLC_IPC_HEARTBEAT_INDEX, 0) + 1) & 0xFFFF
        self.registers[PLC_IPC_HEARTBEAT_INDEX] = plc_index
        self.registers[UR_IPC_HEARTBEAT_RETURN] = (plc_index + 1) & 0xFFFF
        self.registers[PLC_IPC_COMM_NORMAL] = 1

    def write_d_block(self, start_address: int, values: list[int]) -> bool:
        end_address = start_address + len(values) - 1
        if start_address <= ROBOT_READ_ONLY_END and end_address >= ROBOT_READ_ONLY_START:
            raise ValueError("Robot D12100~D12156 registers are read-only from HMI side")
        if start_address <= ROBOT_MANUAL_INTERNAL_END and end_address >= ROBOT_MANUAL_INTERNAL_START:
            raise ValueError("Robot D3080~D3093 registers are PLC-internal and HMI write is forbidden")
        if not self.connected:
            return False
        for offset, value in enumerate(values):
            self.registers[start_address + offset] = int(value) & 0xFFFF
        self.last_write_time = datetime.now()
        return True
