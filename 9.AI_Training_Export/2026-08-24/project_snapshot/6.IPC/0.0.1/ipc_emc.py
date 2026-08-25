"""IPC 接收 PLC EMC 停止要求並回覆停止完成。

PLC 點位：
    D1207  PLCtoIPC_EMC_Request（PLC 寫入，IPC 讀取）
    D1308  IPCtoPLC_EMC_Done（IPC 寫入，PLC 讀取）

安全注意：此程式只處理 PLC 與 IPC 的通訊握手，不能取代安全迴路。
請將 stop_small_material_robot() 改為小料手臂廠商 SDK 的安全停止指令。
只有在手臂確認安全停止後，才可以回寫 D1308 = 1。
"""

from __future__ import annotations

import argparse
import logging
import signal
from dataclasses import dataclass
from threading import Event
from typing import Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException


DEFAULT_PLC_IP = "192.168.1.5"
DEFAULT_PLC_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_TIMEOUT = 1.0
DEFAULT_INTERVAL = 0.1
DEFAULT_RECONNECT_DELAY = 2.0

D_PLC_TO_IPC_EMC_REQUEST = 1207
D_IPC_TO_PLC_EMC_DONE = 1308


@dataclass(frozen=True)
class Settings:
    ip: str
    port: int
    slave_id: int
    timeout: float
    interval: float
    reconnect_delay: float
    simulate_stop: bool


class PLCClient:
    """IPC EMC 專用 Modbus TCP client。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ModbusTcpClient(
            host=settings.ip,
            port=settings.port,
            timeout=settings.timeout,
        )
        self.connected = False
        self.last_error: Optional[str] = None

    def connect(self) -> bool:
        try:
            self.connected = bool(self.client.connect())
        except (ModbusException, OSError) as exc:
            self.connected = False
            self.last_error = str(exc)
            return False

        self.last_error = None if self.connected else (
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

    def read_emc_request(self) -> bool:
        try:
            result = self.client.read_holding_registers(
                address=D_PLC_TO_IPC_EMC_REQUEST,
                count=1,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"讀取 D1207 失敗：{exc}") from exc

        if result.isError():
            self.connected = False
            raise ConnectionError(f"讀取 D1207 失敗：{result}")

        return bool(int(result.registers[0]) & 0x0001)

    def write_emc_done(self, done: bool) -> None:
        try:
            result = self.client.write_register(
                address=D_IPC_TO_PLC_EMC_DONE,
                value=1 if done else 0,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"寫入 D1308 失敗：{exc}") from exc

        if result.isError():
            self.connected = False
            raise ConnectionError(f"寫入 D1308 失敗：{result}")


def stop_small_material_robot(simulate_stop: bool) -> bool:
    """停止小料手臂並在安全停止完成時回傳 True。

    現場使用時，請以手臂廠商 SDK 的安全停止指令取代 TODO 區段，且必須
    等待控制器回報停止完成後才回傳 True。
    """
    if simulate_stop:
        logging.warning("模擬模式：視為小料手臂已安全停止")
        return True

    # TODO: 在此呼叫小料手臂廠商 SDK 的安全停止指令，並確認停止完成。
    logging.error("尚未設定小料手臂安全停止 SDK；不會回寫 D1308=1")
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP 拉麵機 IPC EMC 停止處理")
    parser.add_argument("--ip", default=DEFAULT_PLC_IP, help="PLC IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PLC_PORT)
    parser.add_argument("--slave-id", type=int, default=DEFAULT_SLAVE_ID)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument(
        "--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY,
    )
    parser.add_argument(
        "--simulate-stop", action="store_true",
        help="測試用途；不控制真實手臂但會回覆停止完成",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.slave_id <= 255:
        raise SystemExit("--slave-id 必須介於 0 到 255")
    if args.timeout <= 0 or args.interval <= 0 or args.reconnect_delay <= 0:
        raise SystemExit("timeout、interval、reconnect-delay 必須大於 0")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    settings = Settings(
        ip=args.ip,
        port=args.port,
        slave_id=args.slave_id,
        timeout=args.timeout,
        interval=args.interval,
        reconnect_delay=args.reconnect_delay,
        simulate_stop=args.simulate_stop,
    )
    plc = PLCClient(settings)
    stop_event = Event()
    emc_active = False
    emc_done_written = False

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    logging.info("IPC EMC 監控啟動：讀 D1207、寫 D1308")

    try:
        while not stop_event.is_set():
            if not plc.connected:
                if not plc.connect():
                    logging.warning("%s", plc.last_error)
                    stop_event.wait(settings.reconnect_delay)
                    continue
                logging.info("PLC 已連線")

            try:
                request = plc.read_emc_request()

                if request and not emc_active:
                    emc_active = True
                    logging.warning("收到 PLC EMC 停止要求（D1207=1）")
                    emc_done_written = False

                    if stop_small_material_robot(settings.simulate_stop):
                        plc.write_emc_done(True)
                        emc_done_written = True
                        logging.warning("小料手臂已停止，回覆 D1308=1")

                elif not request and emc_active:
                    emc_active = False
                    if emc_done_written:
                        plc.write_emc_done(False)
                    emc_done_written = False
                    logging.info("PLC 已解除 EMC 要求，回覆 D1308=0")

                stop_event.wait(settings.interval)

            except ConnectionError as exc:
                logging.error("%s", exc)
                plc.close()
                stop_event.wait(settings.reconnect_delay)
    finally:
        plc.close()
        logging.info("IPC EMC 監控已停止")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
