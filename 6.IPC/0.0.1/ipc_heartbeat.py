"""IPC <-> PLC 雙向握手心跳程式。

PLC 點位：
    D1200  PLCtoIPC_HB_Index（IPC 讀取）
    D1300  IPCtoPLC_HB_ReturnIndex（IPC 寫入）

握手規則：IPC 回傳值 = PLC Index + 1，16-bit 溢位後回到 0。
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from dataclasses import dataclass
from threading import Event
from typing import Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


DEFAULT_PLC_IP = "192.168.1.5"
DEFAULT_PLC_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_TIMEOUT = 1.0
DEFAULT_HEARTBEAT_INTERVAL = 0.5
DEFAULT_RECONNECT_DELAY = 2.0

D_PLC_TO_IPC_HB_INDEX = 1200
D_IPC_TO_PLC_HB_RETURN_INDEX = 1300


@dataclass(frozen=True)
class Settings:
    ip: str
    port: int
    slave_id: int
    timeout: float
    interval: float
    reconnect_delay: float


class IPCHeartbeat:
    """維持一條 Modbus TCP 連線並執行 IPC 心跳握手。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ModbusTcpClient(
            host=settings.ip,
            port=settings.port,
            timeout=settings.timeout,
        )
        self.connected = False
        self.last_error: Optional[str] = None

    @staticmethod
    def calc_return_index(plc_index: int) -> int:
        return (int(plc_index) + 1) & 0xFFFF

    def connect(self) -> bool:
        try:
            self.connected = bool(self.client.connect())
        except (ModbusException, OSError) as exc:
            self.connected = False
            self.last_error = str(exc)
            return False

        if self.connected:
            self.last_error = None
        else:
            self.last_error = (
                f"無法連線 PLC {self.settings.ip}:{self.settings.port}"
            )
        return self.connected

    def close(self) -> None:
        try:
            self.client.close()
        except (ModbusException, OSError):
            pass
        finally:
            self.connected = False

    def tick(self) -> tuple[int, int]:
        """完成一次 D1200 讀取與 D1300 回寫。"""
        if not self.connected:
            raise ConnectionError("尚未連線 PLC")

        try:
            result = self.client.read_holding_registers(
                address=D_PLC_TO_IPC_HB_INDEX,
                count=1,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"讀取 D1200 失敗：{exc}") from exc

        if result.isError():
            self.connected = False
            raise ConnectionError(f"讀取 D1200 失敗：{result}")

        plc_index = int(result.registers[0]) & 0xFFFF
        return_index = self.calc_return_index(plc_index)

        try:
            result = self.client.write_register(
                address=D_IPC_TO_PLC_HB_RETURN_INDEX,
                value=return_index,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"寫入 D1300 失敗：{exc}") from exc

        if result.isError():
            self.connected = False
            raise ConnectionError(f"寫入 D1300 失敗：{result}")

        self.last_error = None
        return plc_index, return_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP 拉麵機 IPC 心跳")
    parser.add_argument("--ip", default=DEFAULT_PLC_IP, help="PLC IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PLC_PORT)
    parser.add_argument("--slave-id", type=int, default=DEFAULT_SLAVE_ID)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_HEARTBEAT_INTERVAL
    )
    parser.add_argument(
        "--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY
    )
    parser.add_argument(
        "--debug", action="store_true", help="顯示每次心跳讀寫值"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.slave_id <= 255:
        raise SystemExit("--slave-id 必須介於 0 到 255")
    if args.timeout <= 0 or args.interval <= 0 or args.reconnect_delay <= 0:
        raise SystemExit("timeout、interval、reconnect-delay 必須大於 0")

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    settings = Settings(
        ip=args.ip,
        port=args.port,
        slave_id=args.slave_id,
        timeout=args.timeout,
        interval=args.interval,
        reconnect_delay=args.reconnect_delay,
    )
    heartbeat = IPCHeartbeat(settings)
    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    logging.info(
        "IPC 心跳啟動：PLC=%s:%s，讀 D1200，寫 D1300",
        settings.ip,
        settings.port,
    )

    try:
        while not stop_event.is_set():
            if not heartbeat.connected:
                if not heartbeat.connect():
                    logging.warning("%s", heartbeat.last_error)
                    stop_event.wait(settings.reconnect_delay)
                    continue
                logging.info("PLC 已連線")

            try:
                plc_index, return_index = heartbeat.tick()
                logging.debug(
                    "Heartbeat OK：D1200=%s，D1300=%s",
                    plc_index,
                    return_index,
                )
                stop_event.wait(settings.interval)
            except ConnectionError as exc:
                logging.error("%s", exc)
                heartbeat.close()
                stop_event.wait(settings.reconnect_delay)
    finally:
        heartbeat.close()
        logging.info("IPC 心跳已停止")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
