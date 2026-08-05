"""無 PLC 時用於 UI 測試的記憶體 client。"""
from __future__ import annotations

from datetime import datetime
import threading

from register_map import (
    CMD_MODE_AUTO,
    CMD_MODE_MANUAL,
    CMD_MODE_SEMI_AUTO,
    MACHINE_MODE_AUTO,
    MACHINE_MODE_MANUAL,
    MACHINE_MODE_SEMI_AUTO,
    PLC_CMD_ACK_INDEX,
    PLC_CMD_RESPONSE_CODE,
    PLC_MACHINE_MODE,
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
        self.registers = {101: 0, 102: 24, 103: 150, 104: 10, 105: 10,
                          106: 50, 107: 50, 108: 150, 109: 10, 110: 10,
                          111: 50, 112: 50, 1105: 1, 1107: 0, 1110: 0,
                          1004: 0, 1108: 0, PLC_MACHINE_MODE: MACHINE_MODE_MANUAL,
                          1120: 0, 1121: 0, 1122: 0, 1123: 0, 1124: 1,
                          12100: 0x0006, 12150: 0}

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
        # 模擬 PLC 接收命令後更新實際速度，供主頁展示 Ready / Running。
        if address == 1002 and self.registers[address] == 1:
            command = self.registers.get(1000, 0)
            mode_commands = {
                CMD_MODE_MANUAL: (MACHINE_MODE_MANUAL, 300),
                CMD_MODE_SEMI_AUTO: (MACHINE_MODE_SEMI_AUTO, 301),
                CMD_MODE_AUTO: (MACHINE_MODE_AUTO, 302),
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
            elif command == 10:
                self.registers[101] = self.registers.get(1003, 0)
            elif command == 11:
                self.registers[101] = 0
            elif command == 40:
                self.registers[1120] = 3
                self.registers[1121] = self.registers.get(1001, 0)
                self.registers[1122] = 200
                self.registers[1123] = 0
        self.last_write_time = datetime.now()
        return True

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
