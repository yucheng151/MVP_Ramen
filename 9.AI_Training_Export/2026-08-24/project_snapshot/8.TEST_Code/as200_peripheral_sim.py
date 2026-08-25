"""AS200 Simulator 周邊設備模擬器。

本程式不是另一台虛擬 PLC。它以 Modbus TCP client 連到正在執行
MVP_V2_100 的 AS200 Simulator，模擬 PLC 外部的兩組設備：

* IPC / UR1 / UR2：D1200~D1308 交握，回覆 201 / 202 / 203。
* Nachi：D12100~D12104 回覆 D12150~D12156 的命令交握。

AS200 Simulator 允許透過 Modbus coil 位址 0x0400 起點強制 X 接點；
整合測試會用真正的 X0.1~X0.4，不使用測試用 D 暫存器冒充 X 接點。
"""

from __future__ import annotations

import argparse
import logging
import signal
import time
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient


LOG = logging.getLogger("as200_peripheral_sim")


# PLC -> IPC
D_PLC_IPC_HEARTBEAT = 1200
D_PLC_IPC_REQUEST_CODE = 1201
D_PLC_IPC_REQUEST_SEQ = 1202
D_PLC_IPC_REQUEST_VALID = 1203
D_PLC_IPC_EMC_REQUEST = 1207

# IPC -> PLC
D_IPC_HEARTBEAT_RETURN = 1300
D_IPC_ACK_SEQ = 1301
D_IPC_BUSY = 1302
D_IPC_RESPONSE_CODE = 1303
D_IPC_RESPONSE_SEQ = 1304
D_IPC_ERROR_CODE = 1305
D_IPC_CURRENT_TASK = 1307
D_IPC_EMC_DONE = 1308

# Nachi -> PLC
D_NACHI_STATUS = 12100
D_NACHI_DATA_FINISH = 12101
D_NACHI_ERROR_CODE = 12102
D_NACHI_ACTION_FINISH = 12103
D_NACHI_RETURN_INDEX = 12104

# PLC -> Nachi
D_NACHI_COMMAND_WORD = 12150
D_NACHI_COMMAND_INDEX = 12151
D_NACHI_ACTION_NO = 12152
D_NACHI_NOODLE_CABINET = 12153
D_NACHI_CUT_NO = 12154
D_NACHI_OUTPUT_CABINET = 12155
D_NACHI_NOODLE_TYPE = 12156

IPC_RESPONSE_BY_COMMAND = {101: 201, 102: 202, 103: 203}

BIT_NACHI_STANDBY = 0
BIT_NACHI_STATUS_OUTPUT = 1
BIT_NACHI_HOME = 2
BIT_NACHI_EXTERNAL_CONTROL = 9
BIT_NACHI_REMOTE_AVAILABLE = 12
BIT_NACHI_DATA_READY = 8
BIT_NACHI_EXTERNAL_START = 1
BIT_NACHI_INTERVAL_PERMIT = 9


def bit(bit_no: int) -> int:
    return 1 << bit_no


NACHI_READY_WORD = (
    bit(BIT_NACHI_STANDBY)
    | bit(BIT_NACHI_STATUS_OUTPUT)
    | bit(BIT_NACHI_HOME)
    | bit(BIT_NACHI_EXTERNAL_CONTROL)
    | bit(BIT_NACHI_REMOTE_AVAILABLE)
)

NACHI_RUNNING_WORD = bit(BIT_NACHI_STATUS_OUTPUT) | bit(BIT_NACHI_EXTERNAL_CONTROL)


@dataclass
class IPCTask:
    code: int
    seq: int
    started_at: float


@dataclass
class NachiDataTask:
    index: int
    action_no: int
    started_at: float
    finish_pulsed: bool = False


@dataclass
class NachiTask:
    index: int
    action_no: int
    started_at: float
    phase: int = 1
    action_pulsed: bool = False


class AS200PeripheralSimulator:
    def __init__(
        self,
        client: ModbusTcpClient,
        device_id: int,
        ipc_delay: float,
        nachi_accept_delay: float,
        nachi_action_delay: float,
        pulse_seconds: float,
    ) -> None:
        self.client = client
        self.device_id = device_id
        self.ipc_delay = ipc_delay
        self.nachi_accept_delay = nachi_accept_delay
        self.nachi_action_delay = nachi_action_delay
        self.pulse_seconds = pulse_seconds
        self.ipc_task: IPCTask | None = None
        self.nachi_data_task: NachiDataTask | None = None
        self.nachi_task: NachiTask | None = None
        self.last_ipc_seq: int | None = None
        self.last_nachi_data_ready = False
        self.last_nachi_interval_permit = False
        self.last_nachi_external_start = False
        self.nachi_data_consumed = False
        self.nachi_start_pending = False
        self.nachi_interval_pending = False
        self.nachi_interval_consumed = False
        self.pending_nachi_index = 0
        self.pending_nachi_action_no = 0
        self.nachi_data_request_count = 0
        self.nachi_action_start_count = 0
        self.nachi_interval_start_count = 0
        self.last_nachi_command_word = 0
        self.nachi_startup_started_at: float | None = None
        self.nachi_startup_completed = False
        self.stop_requested = False

    def read_words(self, address: int, count: int) -> list[int]:
        result = self.client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"read D{address} count={count}: {result}")
        return [int(value) & 0xFFFF for value in result.registers]

    def write_word(self, address: int, value: int) -> None:
        result = self.client.write_register(
            address=address,
            value=int(value) & 0xFFFF,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"write D{address}: {result}")

    def write_words(self, address: int, values: list[int]) -> None:
        result = self.client.write_registers(
            address=address,
            values=[int(value) & 0xFFFF for value in values],
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"write D{address} count={len(values)}: {result}")

    def initialize_outputs(self) -> None:
        heartbeat = self.read_words(D_PLC_IPC_HEARTBEAT, 1)[0]
        self.write_words(
            D_IPC_HEARTBEAT_RETURN,
            [(heartbeat + 1) & 0xFFFF, 0, 0, 0, 0, 0],
        )
        self.write_word(D_IPC_CURRENT_TASK, 0)
        self.write_word(D_IPC_EMC_DONE, 0)
        self.write_words(
            D_NACHI_STATUS,
            [NACHI_READY_WORD, 0, 0, 0, 0],
        )
        command_word = self.read_words(D_NACHI_COMMAND_WORD, 1)[0]
        self.last_nachi_data_ready = bool(command_word & bit(BIT_NACHI_DATA_READY))
        self.last_nachi_interval_permit = bool(
            command_word & bit(BIT_NACHI_INTERVAL_PERMIT)
        )
        self.last_nachi_external_start = bool(
            command_word & bit(BIT_NACHI_EXTERNAL_START)
        )
        # 周邊模擬器若在PLC已完成初始化後才啟動，外部啟動位會已經ON；
        # 此時視為既有初始化已完成，不應等待不存在的新上升沿。
        if self.last_nachi_external_start:
            self.nachi_startup_completed = True
        LOG.info("周邊初始狀態已寫入：IPC Ready、Nachi Standby/Home")

    def tick_ipc(self, now: float) -> None:
        request = self.read_words(D_PLC_IPC_HEARTBEAT, 8)
        heartbeat, code, seq, valid = request[0], request[1], request[2], request[3]
        emc_request = bool(request[7] & 1)

        self.write_word(D_IPC_HEARTBEAT_RETURN, (heartbeat + 1) & 0xFFFF)

        if emc_request:
            if self.ipc_task is not None:
                LOG.warning("EMC 中止 IPC CMD%s seq=%s", self.ipc_task.code, self.ipc_task.seq)
            self.ipc_task = None
            self.write_words(D_IPC_ACK_SEQ, [seq, 0, 901, seq, 1004])
            self.write_word(D_IPC_CURRENT_TASK, 0)
            self.write_word(D_IPC_EMC_DONE, 1)
            return

        self.write_word(D_IPC_EMC_DONE, 0)

        if (
            self.ipc_task is None
            and valid != 0
            and seq != self.last_ipc_seq
        ):
            if code not in IPC_RESPONSE_BY_COMMAND:
                self.write_words(D_IPC_ACK_SEQ, [seq, 0, 901, seq, 1001])
                self.write_word(D_IPC_CURRENT_TASK, 0)
                self.last_ipc_seq = seq
                LOG.error("IPC 收到不支援命令 CMD%s seq=%s", code, seq)
            else:
                self.ipc_task = IPCTask(code=code, seq=seq, started_at=now)
                self.last_ipc_seq = seq
                self.write_words(D_IPC_ACK_SEQ, [seq, 1, 0, 0, 0])
                self.write_word(D_IPC_CURRENT_TASK, code)
                LOG.info("IPC 接收 CMD%s seq=%s，Busy=1", code, seq)

        task = self.ipc_task
        if task is not None and now - task.started_at >= self.ipc_delay:
            response = IPC_RESPONSE_BY_COMMAND[task.code]
            self.write_words(
                D_IPC_ACK_SEQ,
                [task.seq, 0, response, task.seq, 0],
            )
            self.write_word(D_IPC_CURRENT_TASK, 0)
            LOG.info("IPC 完成 CMD%s seq=%s，回覆 %s", task.code, task.seq, response)
            self.ipc_task = None

    def tick_nachi(self, now: float) -> None:
        command = self.read_words(D_NACHI_COMMAND_WORD, 7)
        command_word = command[0]
        self.last_nachi_command_word = command_word
        index = command[1]
        action_no = command[2]
        data_ready = bool(command_word & bit(BIT_NACHI_DATA_READY))
        interval_permit = bool(command_word & bit(BIT_NACHI_INTERVAL_PERMIT))
        external_start = bool(command_word & bit(BIT_NACHI_EXTERNAL_START))
        external_start_rising = (
            external_start and not self.last_nachi_external_start
        )
        self.last_nachi_external_start = external_start

        # 開機初始化：PLC給D12150.1外部啟動後，真實Robot
        # 會先回覆「動作中」，再回到Standby/Home。初始化FB
        # 看到這次動作中才會結束，不可只回寫Ready。
        if (
            external_start_rising
            and not self.nachi_startup_completed
            and self.nachi_startup_started_at is None
            and self.nachi_task is None
            and not data_ready
        ):
            self.nachi_startup_started_at = now
            self.write_word(D_NACHI_STATUS, NACHI_RUNNING_WORD)
            LOG.info("Nachi收到開機外部啟動，回覆動作中")

        if self.nachi_startup_started_at is not None:
            startup_elapsed = now - self.nachi_startup_started_at
            if startup_elapsed < self.nachi_action_delay:
                self.write_word(D_NACHI_STATUS, NACHI_RUNNING_WORD)
            else:
                self.write_word(D_NACHI_STATUS, NACHI_READY_WORD)
                self.nachi_startup_started_at = None
                self.nachi_startup_completed = True
                LOG.info("Nachi開機動作完成，回到Standby/Home")
            self.last_nachi_data_ready = data_ready
            self.last_nachi_interval_permit = interval_permit
            return

        # D12150.8：PLC已準備好參數，Nachi讀取後以D12101.0回覆。
        # D12150.1只用於開機初始化啟動Robot程式，不是每一筆動作的允許。
        # 因此每一筆新動作以D12150.8的一次完整交握作為起點。
        if data_ready and not self.nachi_data_consumed:
            self.pending_nachi_index = index
            self.pending_nachi_action_no = action_no
            self.nachi_data_request_count += 1
            self.nachi_data_consumed = True
            self.nachi_start_pending = True
            self.nachi_data_task = NachiDataTask(
                index=index,
                action_no=action_no,
                started_at=now,
            )
            LOG.info(
                "Nachi 讀取PLC資料 Action=%s Index=%s Cabinet=%s Cut=%s Output=%s Type=%s",
                action_no,
                index,
                command[3],
                command[4],
                command[5],
                command[6],
            )

        if not data_ready:
            self.nachi_data_consumed = False

        # PLC收到D12101.0後會放掉D12150.8。資料交握完整結束後，
        # Robot內的自動程式就開始本筆Nachi第一段實際動作。
        if (
            self.last_nachi_data_ready
            and not data_ready
            and self.nachi_start_pending
            and self.nachi_task is None
        ):
            self.nachi_task = NachiTask(
                index=self.pending_nachi_index,
                action_no=self.pending_nachi_action_no,
                started_at=now,
                phase=1,
            )
            self.nachi_start_pending = False
            self.nachi_action_start_count += 1
            self.write_words(
                D_NACHI_STATUS,
                [NACHI_RUNNING_WORD, 0, 0, 0, self.pending_nachi_index],
            )
            LOG.info(
                "Nachi 開始第一段 Action=%s Index=%s",
                self.pending_nachi_action_no,
                self.pending_nachi_index,
            )

        self.last_nachi_data_ready = data_ready

        data_task = self.nachi_data_task
        if data_task is not None:
            elapsed = now - data_task.started_at
            if elapsed >= self.nachi_accept_delay and data_ready:
                # 資料交握使用電平確認：Nachi完成讀取後持續回覆ON，
                # 直到PLC放掉D12150.8。這可避免第二筆連續交換時，
                # 完成訊號比PLC掃描週期短而被漏接。
                self.write_word(D_NACHI_RETURN_INDEX, data_task.index)
                self.write_word(D_NACHI_DATA_FINISH, 1)
                if not data_task.finish_pulsed:
                    data_task.finish_pulsed = True
                    LOG.info("Nachi Index=%s 資料接收完成 D12101.0=1", data_task.index)
            elif data_task.finish_pulsed and not data_ready:
                self.write_word(D_NACHI_DATA_FINISH, 0)
                self.nachi_data_task = None

        # Action 2的第一個D12103.0代表「取熟麵並甩麵」完成；PLC等碗
        # 到位後以D12150.9允許第二段「倒麵進碗」。
        if (
            interval_permit
            and self.nachi_interval_pending
            and not self.nachi_interval_consumed
            and self.nachi_task is None
        ):
            self.nachi_task = NachiTask(
                index=self.pending_nachi_index,
                action_no=self.pending_nachi_action_no,
                started_at=now,
                phase=2,
            )
            self.nachi_interval_pending = False
            self.nachi_interval_consumed = True
            self.nachi_interval_start_count += 1
            self.write_words(
                D_NACHI_STATUS,
                [NACHI_RUNNING_WORD, 0, 0, 0, self.pending_nachi_index],
            )
            LOG.info(
                "Nachi D12150.9允許第二段倒麵 Action=%s Index=%s",
                self.pending_nachi_action_no,
                self.pending_nachi_index,
            )

        if not interval_permit:
            self.nachi_interval_consumed = False
        self.last_nachi_interval_permit = interval_permit

        task = self.nachi_task
        if task is None:
            # 資料交換期間手臂仍在原點；真正外部啟動前保持Home。
            self.write_word(D_NACHI_STATUS, NACHI_READY_WORD)
            return

        elapsed = now - task.started_at

        if (
            elapsed >= self.nachi_action_delay
            and elapsed < self.nachi_action_delay + self.pulse_seconds
        ):
            # 與真實Robot相同，在完成訊號期間持續更新D12103，避免被PLC Scan覆寫。
            self.write_word(D_NACHI_RETURN_INDEX, task.index)
            self.write_word(D_NACHI_ACTION_FINISH, 1)
            if not task.action_pulsed:
                task.action_pulsed = True
                LOG.info(
                    "Nachi Action=%s Index=%s 第%s段完成 D12103.0=1",
                    task.action_no,
                    task.index,
                    task.phase,
                )

        if elapsed >= self.nachi_action_delay + self.pulse_seconds:
            self.write_word(D_NACHI_ACTION_FINISH, 0)
            self.write_words(
                D_NACHI_STATUS,
                [NACHI_READY_WORD, 0, 0, 0, task.index],
            )
            if task.action_no == 2 and task.phase == 1:
                self.nachi_interval_pending = True
                LOG.info(
                    "Nachi Action=2 Index=%s 甩麵完成，等待D12150.9倒麵",
                    task.index,
                )
            else:
                LOG.info(
                    "Nachi Action=%s Index=%s 第%s段完成並回到Standby/Home",
                    task.action_no,
                    task.index,
                    task.phase,
                )
            self.nachi_task = None

    def run(self, poll_seconds: float, duration: float | None) -> None:
        self.initialize_outputs()
        started_at = time.monotonic()
        while not self.stop_requested:
            now = time.monotonic()
            if duration is not None and now - started_at >= duration:
                break
            try:
                self.tick_ipc(now)
                self.tick_nachi(now)
            except (ConnectionError, OSError) as exc:
                LOG.error("AS200 通訊失敗：%s", exc)
                time.sleep(max(poll_seconds, 0.5))
                continue
            time.sleep(poll_seconds)

    def request_stop(self, *_args: object) -> None:
        self.stop_requested = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP Ramen AS200 外部設備模擬器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10002)
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--poll", type=float, default=0.05)
    parser.add_argument("--ipc-delay", type=float, default=0.8)
    parser.add_argument("--nachi-accept-delay", type=float, default=0.2)
    parser.add_argument("--nachi-action-delay", type=float, default=1.2)
    parser.add_argument("--pulse-seconds", type=float, default=1.0)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    client = ModbusTcpClient(args.host, port=args.port, timeout=1.0)
    if not client.connect():
        LOG.error("無法連線 AS200 Simulator %s:%s", args.host, args.port)
        return 2

    simulator = AS200PeripheralSimulator(
        client=client,
        device_id=args.device_id,
        ipc_delay=args.ipc_delay,
        nachi_accept_delay=args.nachi_accept_delay,
        nachi_action_delay=args.nachi_action_delay,
        pulse_seconds=args.pulse_seconds,
    )
    signal.signal(signal.SIGINT, simulator.request_stop)
    signal.signal(signal.SIGTERM, simulator.request_stop)

    try:
        LOG.info("連線 AS200 Simulator %s:%s", args.host, args.port)
        simulator.run(poll_seconds=args.poll, duration=args.duration)
    finally:
        client.close()
        LOG.info("周邊模擬器已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
