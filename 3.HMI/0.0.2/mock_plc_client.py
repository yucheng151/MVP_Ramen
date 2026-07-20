"""無 PLC 時用於 UI 測試的記憶體 client。"""
from __future__ import annotations

from datetime import datetime
import threading


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
        self.registers = {101: 0, 102: 24, 103: 150, 104: 10, 105: 10,
                          106: 50, 107: 50, 108: 150, 109: 10, 110: 10,
                          111: 50, 112: 50, 1105: 1, 1107: 0, 1110: 0}

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
        if not self.connected:
            return False
        self.registers[address] = int(value) & 0xFFFF
        # 模擬 PLC 接收命令後更新實際速度，供主頁展示 Ready / Running。
        if address == 1002 and self.registers[address] == 1:
            command = self.registers.get(1000, 0)
            if command == 10:
                self.registers[101] = self.registers.get(1003, 0)
            elif command == 11:
                self.registers[101] = 0
        self.last_write_time = datetime.now()
        return True

    def write_d_block(self, start_address: int, values: list[int]) -> bool:
        if not self.connected:
            return False
        for offset, value in enumerate(values):
            self.registers[start_address + offset] = int(value) & 0xFFFF
        self.last_write_time = datetime.now()
        return True
