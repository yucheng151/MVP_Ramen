"""MVP 拉麵機 IPC 控制器：心跳、PLC 任務與 EMC。

PLC -> IPC
    D1200  心跳 Index
    D1201  任務代碼（101=前三料、102=後三料）
    D1202  任務 Seq
    D1203  任務 Valid
    D1204  配方編號
    D1207  EMC 停止要求

IPC -> PLC
    D1300  心跳回傳 Index
    D1301  Ack Seq
    D1302  Busy
    D1303  Response Code（201/202=完成，901=失敗）
    D1304  Response Seq
    D1305  Error Code
    D1307  Current Task
    D1308  EMC 停止完成

安全注意：本程式的 Modbus EMC 握手不能取代實體安全迴路。實機前必須將
SmallMaterialRobot 的 TODO 區段替換為手臂廠商 SDK，且只有確認安全停止後
才能回寫 D1308=1。
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

D_PLC_TO_IPC_START = 1200
D_IPC_TO_PLC_HB_RETURN = 1300
D_IPC_TO_PLC_ACK_SEQ = 1301
D_IPC_TO_PLC_BUSY = 1302
D_IPC_TO_PLC_RESPONSE_CODE = 1303
D_IPC_TO_PLC_RESPONSE_SEQ = 1304
D_IPC_TO_PLC_ERROR_CODE = 1305
D_IPC_TO_PLC_CURRENT_TASK = 1307
D_IPC_TO_PLC_EMC_DONE = 1308

CMD_FIRST_MATERIAL = 101
CMD_LAST_MATERIAL = 102
RESP_FIRST_MATERIAL_DONE = 201
RESP_LAST_MATERIAL_DONE = 202
RESP_ERROR = 901
ERR_UNSUPPORTED_COMMAND = 1001
ERR_ROBOT_NOT_CONFIGURED = 1002
ERR_ROBOT_TASK_FAILED = 1003
ERR_EMC_ABORT = 1004


@dataclass(frozen=True)
class Settings:
    ip: str
    port: int
    slave_id: int
    timeout: float
    interval: float
    reconnect_delay: float
    simulate: bool


@dataclass(frozen=True)
class PLCInputs:
    heartbeat_index: int
    request_code: int
    request_seq: int
    request_valid: bool
    recipe_no: int
    emc_request: bool


class PLCClient:
    """IPC 控制器使用的唯一 Modbus TCP 連線。"""

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

    def read_inputs(self) -> PLCInputs:
        try:
            result = self.client.read_holding_registers(
                address=D_PLC_TO_IPC_START,
                count=8,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"讀取 D1200~D1207 失敗：{exc}") from exc
        if result.isError():
            self.connected = False
            raise ConnectionError(f"讀取 D1200~D1207 失敗：{result}")

        data = result.registers
        return PLCInputs(
            heartbeat_index=int(data[0]) & 0xFFFF,
            request_code=int(data[1]) & 0xFFFF,
            request_seq=int(data[2]) & 0xFFFF,
            request_valid=bool(int(data[3]) & 0x0001),
            recipe_no=int(data[4]) & 0xFFFF,
            emc_request=bool(int(data[7]) & 0x0001),
        )

    def write_d(self, address: int, value: int) -> None:
        try:
            result = self.client.write_register(
                address=address,
                value=int(value) & 0xFFFF,
                device_id=self.settings.slave_id,
            )
        except (ModbusException, OSError) as exc:
            self.connected = False
            raise ConnectionError(f"寫入 D{address} 失敗：{exc}") from exc
        if result.isError():
            self.connected = False
            raise ConnectionError(f"寫入 D{address} 失敗：{result}")


class SmallMaterialRobot:
    """小料手臂控制介面。

    實機時，將三個方法中的 TODO 換成手臂廠商 SDK。simulate=True 僅供 PLC
    通訊測試，不能用於真實機械手臂。
    """

    def __init__(self, simulate: bool) -> None:
        self.simulate = simulate

    def start_task(self, command_code: int, recipe_no: int) -> bool:
        if self.simulate:
            logging.warning("模擬模式：開始 IPC 任務 code=%s, recipe=%s", command_code, recipe_no)
            return True
        # TODO: 呼叫小料手臂 SDK，開始指定的投料任務。
        logging.error("尚未設定小料手臂 SDK，拒絕執行任務")
        return False

    def task_finished(self) -> Optional[bool]:
        """回傳 True=成功、False=失敗、None=仍執行中。"""
        if self.simulate:
            return True
        # TODO: 從手臂 SDK 取得任務完成／失敗狀態。
        return False

    def emergency_stop(self) -> bool:
        """安全停止完成後回傳 True。"""
        if self.simulate:
            logging.warning("模擬模式：小料手臂已安全停止")
            return True
        # TODO: 呼叫手臂 SDK 的安全停止，並等待控制器確認停止。
        logging.error("尚未設定小料手臂安全停止 SDK；不會回覆 EMC Done")
        return False


class IPCController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.plc = PLCClient(settings)
        self.robot = SmallMaterialRobot(settings.simulate)
        self.active_seq: Optional[int] = None
        self.active_command: Optional[int] = None
        self.last_handled_seq: Optional[int] = None
        self.emc_active = False
        self.emc_done_written = False

    def _write_heartbeat(self, index: int) -> None:
        self.plc.write_d(D_IPC_TO_PLC_HB_RETURN, (index + 1) & 0xFFFF)

    def _complete_task(self, response_code: int, error_code: int = 0) -> None:
        if self.active_seq is None:
            return
        self.plc.write_d(D_IPC_TO_PLC_BUSY, 0)
        self.plc.write_d(D_IPC_TO_PLC_RESPONSE_CODE, response_code)
        self.plc.write_d(D_IPC_TO_PLC_RESPONSE_SEQ, self.active_seq)
        self.plc.write_d(D_IPC_TO_PLC_ERROR_CODE, error_code)
        self.plc.write_d(D_IPC_TO_PLC_CURRENT_TASK, 0)
        self.last_handled_seq = self.active_seq
        self.active_seq = None
        self.active_command = None

    def _start_task(self, request_code: int, request_seq: int, recipe_no: int) -> None:
        self.plc.write_d(D_IPC_TO_PLC_ACK_SEQ, request_seq)
        self.last_handled_seq = request_seq

        if request_code not in (CMD_FIRST_MATERIAL, CMD_LAST_MATERIAL):
            self.active_seq = request_seq
            self._complete_task(RESP_ERROR, ERR_UNSUPPORTED_COMMAND)
            return

        if not self.robot.start_task(request_code, recipe_no):
            self.active_seq = request_seq
            self._complete_task(RESP_ERROR, ERR_ROBOT_NOT_CONFIGURED)
            return

        self.active_seq = request_seq
        self.active_command = request_code
        self.plc.write_d(D_IPC_TO_PLC_CURRENT_TASK, request_code)
        self.plc.write_d(D_IPC_TO_PLC_BUSY, 1)
        logging.info("IPC 任務開始：code=%s, seq=%s, recipe=%s", request_code, request_seq, recipe_no)

    def _handle_emc(self) -> None:
        if not self.emc_active:
            self.emc_active = True
            self.emc_done_written = False
            logging.warning("收到 PLC EMC 停止要求（D1207=1）")

            if self.active_seq is not None:
                self._complete_task(RESP_ERROR, ERR_EMC_ABORT)

            if self.robot.emergency_stop():
                self.plc.write_d(D_IPC_TO_PLC_EMC_DONE, 1)
                self.emc_done_written = True
                logging.warning("小料手臂已停止，回覆 D1308=1")

    def tick(self) -> None:
        inputs = self.plc.read_inputs()
        self._write_heartbeat(inputs.heartbeat_index)

        if inputs.emc_request:
            self._handle_emc()
            return

        if self.emc_active:
            self.emc_active = False
            if self.emc_done_written:
                self.plc.write_d(D_IPC_TO_PLC_EMC_DONE, 0)
            self.emc_done_written = False
            logging.info("PLC 已解除 EMC 要求，D1308 清為 0")

        if self.active_seq is not None:
            finished = self.robot.task_finished()
            if finished is True:
                response = (
                    RESP_FIRST_MATERIAL_DONE
                    if self.active_command == CMD_FIRST_MATERIAL
                    else RESP_LAST_MATERIAL_DONE
                )
                self._complete_task(response)
                logging.info("IPC 任務完成")
            elif finished is False:
                self._complete_task(RESP_ERROR, ERR_ROBOT_TASK_FAILED)
                logging.error("IPC 任務失敗")
            return

        if (
            inputs.request_valid
            and inputs.request_seq != self.last_handled_seq
        ):
            self._start_task(
                inputs.request_code,
                inputs.request_seq,
                inputs.recipe_no,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP 拉麵機 PLC-to-IPC 控制器")
    parser.add_argument("--ip", default=DEFAULT_PLC_IP, help="PLC IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PLC_PORT)
    parser.add_argument("--slave-id", type=int, default=DEFAULT_SLAVE_ID)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--reconnect-delay", type=float, default=DEFAULT_RECONNECT_DELAY)
    parser.add_argument(
        "--simulate", action="store_true",
        help="測試用途：模擬手臂完成／EMC 停止；不可用於實機",
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
        simulate=args.simulate,
    )
    controller = IPCController(settings)
    stop_event = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    logging.info("IPC 控制器啟動：心跳、任務、EMC 都由同一程式處理")
    try:
        while not stop_event.is_set():
            if not controller.plc.connected:
                if not controller.plc.connect():
                    logging.warning("%s", controller.plc.last_error)
                    stop_event.wait(settings.reconnect_delay)
                    continue
                logging.info("PLC 已連線")

            try:
                controller.tick()
                stop_event.wait(settings.interval)
            except ConnectionError as exc:
                logging.error("%s", exc)
                controller.plc.close()
                stop_event.wait(settings.reconnect_delay)
    finally:
        controller.plc.close()
        logging.info("IPC 控制器已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
