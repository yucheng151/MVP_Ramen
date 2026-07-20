"""HMI 與 PLC 之間共用的 Modbus TCP client。

本模組只負責建立一條唯一的 Modbus TCP 連線，供 heartbeat、command、
status 等模組共用。所有讀寫都透過同一把 lock，避免多執行緒同時送出
Modbus request。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import List, Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from config import PLC_IP, PLC_PORT, PLC_SLAVE_ID, PLC_TIMEOUT


class HMIPlcClient:
    """共用的 PLC Modbus TCP client。

    此類別在 main_hmi.py 中建立一次，然後把同一個實例傳給 heartbeat、
    command 與 status 模組，確保整個 HMI 程式只會維持一條 TCP 連線。
    """

    def __init__(
        self,
        ip: str = PLC_IP,
        port: int = PLC_PORT,
        slave_id: int = PLC_SLAVE_ID,
        timeout: float = PLC_TIMEOUT,
    ):
        self.ip = ip
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self.client = ModbusTcpClient(
            host=self.ip,
            port=self.port,
            timeout=self.timeout,
        )
        self.connected = False
        self.last_error: Optional[str] = None
        self.lock = threading.RLock()
        self.last_read_time: Optional[datetime] = None
        self.last_write_time: Optional[datetime] = None

    def connect(self) -> bool:
        """建立 Modbus TCP 連線。"""
        with self.lock:
            try:
                self.connected = bool(self.client.connect())
            except (ModbusException, OSError) as exc:
                self.connected = False
                self.last_error = str(exc)
                return False

            if self.connected:
                self.last_error = None
            else:
                self.last_error = f"無法連線 {self.ip}:{self.port}"

            return self.connected

    def reconnect(self) -> bool:
        """重新連線 PLC。"""
        self.close()
        return self.connect()

    def close(self) -> None:
        """關閉 Modbus TCP 連線。"""
        with self.lock:
            try:
                self.client.close()
            except (ModbusException, OSError):
                pass
            finally:
                self.connected = False

    def read_d(self, address: int, count: int = 1) -> Optional[List[int]]:
        """讀取 PLC Holding Registers（D 暫存器）。"""
        if address < 0:
            raise ValueError("address 不可小於 0")
        if count <= 0:
            raise ValueError("count 必須大於 0")

        with self.lock:
            if not self.connected:
                self.last_error = "尚未連線 PLC"
                return None

            try:
                result = self.client.read_holding_registers(
                    address=address,
                    count=count,
                    device_id=self.slave_id,
                )
            except (ModbusException, OSError) as exc:
                self.connected = False
                self.last_error = f"讀取 D{address} 失敗：{exc}"
                return None

            if result.isError():
                self.connected = False
                self.last_error = f"讀取 D{address} 失敗：{result}"
                return None

            self.last_error = None
            self.last_read_time = datetime.now()
            return result.registers

    def write_d(self, address: int, value: int) -> bool:
        """寫入單一個 PLC Holding Register（D 暫存器）。"""
        if address < 0:
            raise ValueError("address 不可小於 0")

        with self.lock:
            if not self.connected:
                self.last_error = "尚未連線 PLC"
                return False

            value = int(value) & 0xFFFF

            try:
                result = self.client.write_register(
                    address=address,
                    value=value,
                    device_id=self.slave_id,
                )
            except (ModbusException, OSError) as exc:
                self.connected = False
                self.last_error = f"寫入 D{address} 失敗：{exc}"
                return False

            if result.isError():
                self.connected = False
                self.last_error = f"寫入 D{address} 失敗：{result}"
                return False

            self.last_error = None
            self.last_write_time = datetime.now()
            return True

    def write_d_block(self, start_address: int, values: list[int]) -> bool:
        """寫入一連串的 PLC Holding Registers。"""
        if start_address < 0:
            raise ValueError("start_address 不可小於 0")
        if not values:
            raise ValueError("values 不可為空")

        with self.lock:
            if not self.connected:
                self.last_error = "尚未連線 PLC"
                return False

            normalized_values = [int(value) & 0xFFFF for value in values]

            try:
                result = self.client.write_registers(
                    address=start_address,
                    values=normalized_values,
                    device_id=self.slave_id,
                )
            except (ModbusException, OSError) as exc:
                self.connected = False
                self.last_error = f"寫入 D{start_address}.. 失敗：{exc}"
                return False

            if result.isError():
                self.connected = False
                self.last_error = f"寫入 D{start_address}.. 失敗：{result}"
                return False

            self.last_error = None
            self.last_write_time = datetime.now()
            return True
