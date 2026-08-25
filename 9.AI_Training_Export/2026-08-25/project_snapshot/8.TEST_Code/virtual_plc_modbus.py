#!/usr/bin/env python3
"""可供 MVP_Ramen HMI / IPC 連線的本機 Modbus TCP 虛擬 PLC。

此伺服器模擬 PLC 的 D 暫存器與相關 I/O 狀態，目的是在沒有實體 PLC 時
驗證 HMI、IPC 握手、畫面狀態及故障處理。它不是 ISPSoft 執行引擎，不能
取代 ISPSoft Simulator 對實際 LD/ST 程式的驗證。

預設端點：127.0.0.1:502，device/slave id = 1。

測試控制暫存器（只供本機測試，不加入正式 PLC）：
    D15000  X0 輸入字：bit n = X0.n
    D15001  Y0 輸出字：bit n = Y0.n
    D15010  情境編號，定義見 SCENARIOS
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    from pymodbus.server import StartAsyncTcpServer
    from pymodbus.simulator.simdata import DataType
    from pymodbus.simulator.simdevice import SimData, SimDevice
except ImportError as exc:  # pragma: no cover - 只在缺少套件時執行
    raise SystemExit("缺少 pymodbus，請先執行：py -m pip install pymodbus") from exc


D_COUNT = 20000
IO_COUNT = 256

# HMI -> PLC
D_HMI_CMD_CODE = 1000
D_HMI_CMD_INDEX = 1001
D_HMI_CMD_VALID = 1002
D_HMI_CONVEYOR_SPEED = 1003
D_HMI_EMC = 1004
D_HMI_HEARTBEAT_RETURN = 1005
D_HMI_ROBOT_ACTION = 1010

# PLC -> HMI
D_PLC_HEARTBEAT = 1100
D_PLC_ACK_INDEX = 1102
D_PLC_RESPONSE_CODE = 1103
D_PLC_CONVEYOR_STATUS = 1104
D_HMI_COMM_STATUS = 1105
D_PLC_STATUS_CODE = 1106
D_PLC_EMC_STATUS = 1108
D_MACHINE_MODE = 1109
D_SENSOR_STATUS = 1110
D_ROBOT_MANUAL_STATUS = 1120
D_ROBOT_MANUAL_ACK = 1121
D_ROBOT_MANUAL_RESULT = 1122
D_ROBOT_MANUAL_ALARM = 1123
D_ROBOT_IDLE = 1124
D_MAIN_PROCESS_STEP = 1400

# PLC <-> UR IPC
D_PLC_IPC_HEARTBEAT = 1200
D_PLC_IPC_REQUEST_CODE = 1201
D_PLC_IPC_REQUEST_SEQ = 1202
D_PLC_IPC_REQUEST_VALID = 1203
D_PLC_IPC_EMC = 1207
D_PLC_IPC_COMM_NORMAL = 1209
D_IPC_HEARTBEAT_RETURN = 1300
D_IPC_ACK_SEQ = 1301
D_IPC_BUSY = 1302
D_IPC_RESPONSE_CODE = 1303
D_IPC_RESPONSE_SEQ = 1304
D_IPC_ERROR_CODE = 1305
D_IPC_CURRENT_TASK = 1307
D_IPC_EMC_DONE = 1308

# Nachi monitor registers
D_NACHI_STATUS = 12100
D_NACHI_READ_COMPLETE = 12101
D_NACHI_ERROR = 12102
D_NACHI_ACTION_COMPLETE = 12103
D_NACHI_INDEX = 12104
D_NACHI_COMMAND = 12150

# Test-only registers
D_TEST_X0_WORD = 15000
D_TEST_Y0_WORD = 15001
D_TEST_SCENARIO = 15010

SCENARIOS = {
    0: "normal",
    1: "bowl_sensor_stuck",   # X0.1 永遠不成立
    2: "station20_stuck",     # X0.2 永遠不成立
    3: "ipc_timeout",         # 停止IPC心跳回覆
    4: "robot_alarm",         # Nachi錯誤/警報
    5: "emc",                 # EMC保持中
    6: "slow",                # 所有模擬動作延長4倍
}

SCENARIO_NAMES = {name: number for number, name in SCENARIOS.items()}


@dataclass
class PendingEvent:
    due: float
    name: str
    value: int = 0


class VirtualPLC:
    """執行 HMI 握手、心跳、I/O 與情境故障注入。"""

    def __init__(self, internal_ipc: bool = True) -> None:
        self.lock = threading.RLock()
        self.d = [0] * D_COUNT
        self.x = [False] * 16
        self.y = [False] * 16
        self.coils = [False] * IO_COUNT
        self.discrete_inputs = [False] * IO_COUNT
        self.input_registers = [0] * D_COUNT
        self.internal_ipc = internal_ipc
        self.last_hmi_command_index: Optional[int] = None
        self.events: list[PendingEvent] = []
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_hb_tick = time.monotonic()
        self.last_ipc_hb_tick = time.monotonic()
        self.current_scenario = -1
        self._initialize_registers()

    def _initialize_registers(self) -> None:
        self.d[101] = 0
        self.d[102] = 24
        self.d[103] = 150
        self.d[104] = 10
        self.d[105] = 10
        self.d[106] = 50
        self.d[107] = 50
        self.d[108] = 300
        self.d[109] = 10
        self.d[110] = 10
        self.d[111] = 50
        self.d[112] = 50
        self.d[D_HMI_COMM_STATUS] = 1
        self.d[D_MACHINE_MODE] = 0
        self.d[D_ROBOT_IDLE] = 1
        self.d[D_PLC_IPC_COMM_NORMAL] = 1
        self.d[D_IPC_HEARTBEAT_RETURN] = 1
        self.d[D_NACHI_STATUS] = 0x0006  # 狀態輸出 + Home
        self.d[D_NACHI_READ_COMPLETE] = 1
        self.d[D_TEST_X0_WORD] = 0
        self.d[D_TEST_Y0_WORD] = 0
        self.d[D_TEST_SCENARIO] = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run_loop, name="virtual-plc", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        while not self.stop_event.is_set():
            now = time.monotonic()
            with self.lock:
                self._apply_scenario()
                self._update_heartbeats(now)
                self._process_hmi_command(now)
                self._process_events(now)
                self._update_io_mirrors()
            self.stop_event.wait(0.02)

    def _duration(self, seconds: float) -> float:
        return seconds * (4.0 if self.d[D_TEST_SCENARIO] == 6 else 1.0)

    def _schedule(self, delay: float, name: str, value: int = 0) -> None:
        self.events.append(PendingEvent(time.monotonic() + self._duration(delay), name, value))

    def _apply_scenario(self) -> None:
        scenario = int(self.d[D_TEST_SCENARIO])
        if scenario not in SCENARIOS:
            scenario = 0
            self.d[D_TEST_SCENARIO] = 0
        if scenario == self.current_scenario:
            return

        self.current_scenario = scenario
        # 清除前一情境的故障狀態。
        self.d[D_PLC_EMC_STATUS] = 0
        self.d[D_PLC_IPC_EMC] = 0
        self.d[D_IPC_EMC_DONE] = 0
        self.d[D_NACHI_ERROR] = 0
        self.d[D_NACHI_STATUS] = 0x0006
        self.d[D_PLC_IPC_COMM_NORMAL] = 1

        if scenario == 4:
            self.d[D_NACHI_ERROR] = 401
            self.d[D_NACHI_STATUS] |= (1 << 3) | (1 << 4)
        elif scenario == 5:
            self.d[D_PLC_EMC_STATUS] = 1
            self.d[D_PLC_IPC_EMC] = 1
            self.d[D_IPC_EMC_DONE] = 1
        logging.info("情境切換：%s (%s)", scenario, SCENARIOS[scenario])

    def _update_heartbeats(self, now: float) -> None:
        if now - self.last_hb_tick >= 0.5:
            self.last_hb_tick = now
            self.d[D_PLC_HEARTBEAT] = (self.d[D_PLC_HEARTBEAT] + 1) & 0xFFFF

        # HMI回傳可以比PLC快一個或慢一個scan，測試器給予寬鬆判斷。
        expected = (self.d[D_PLC_HEARTBEAT] + 1) & 0xFFFF
        self.d[D_HMI_COMM_STATUS] = int(
            self.d[D_HMI_HEARTBEAT_RETURN] in (expected, self.d[D_PLC_HEARTBEAT])
            or self.d[D_HMI_HEARTBEAT_RETURN] == 0
        )

        if now - self.last_ipc_hb_tick >= 0.5:
            self.last_ipc_hb_tick = now
            self.d[D_PLC_IPC_HEARTBEAT] = (self.d[D_PLC_IPC_HEARTBEAT] + 1) & 0xFFFF

        if self.current_scenario == 3:
            self.d[D_PLC_IPC_COMM_NORMAL] = 0
        elif self.internal_ipc:
            self.d[D_IPC_HEARTBEAT_RETURN] = (self.d[D_PLC_IPC_HEARTBEAT] + 1) & 0xFFFF
            self.d[D_PLC_IPC_COMM_NORMAL] = 1
        else:
            expected_ipc = (self.d[D_PLC_IPC_HEARTBEAT] + 1) & 0xFFFF
            self.d[D_PLC_IPC_COMM_NORMAL] = int(
                self.d[D_IPC_HEARTBEAT_RETURN] == expected_ipc
            )

    def _process_hmi_command(self, now: float) -> None:
        _ = now
        if not (self.d[D_HMI_CMD_VALID] & 0x0001):
            return
        command_index = self.d[D_HMI_CMD_INDEX]
        if command_index == self.last_hmi_command_index:
            return
        self.last_hmi_command_index = command_index
        command = self.d[D_HMI_CMD_CODE]
        self.d[D_PLC_ACK_INDEX] = command_index
        self.d[D_PLC_STATUS_CODE] = 1

        if command == 1:  # Initialize
            self.d[D_PLC_RESPONSE_CODE] = 200
            self.d[D_PLC_STATUS_CODE] = 0
        elif command == 6:  # Alarm reset
            self.d[D_TEST_SCENARIO] = 0
            self.d[D_PLC_RESPONSE_CODE] = 206
            self.d[D_PLC_STATUS_CODE] = 0
        elif command == 10:  # Conveyor run
            self.d[101] = self.d[D_HMI_CONVEYOR_SPEED]
            self.d[D_PLC_CONVEYOR_STATUS] = 1
            self.d[D_PLC_RESPONSE_CODE] = 210
        elif command == 11:  # Conveyor stop
            self.d[101] = 0
            self.d[D_PLC_CONVEYOR_STATUS] = 0
            self.d[D_PLC_RESPONSE_CODE] = 211
        elif command == 12:  # Set conveyor speed
            self.d[108] = self.d[D_HMI_CONVEYOR_SPEED]
            self.d[D_PLC_RESPONSE_CODE] = 212
        elif command == 20:  # Bowl dispense
            self._start_bowl_dispense()
        elif command == 30:
            self.d[D_MACHINE_MODE] = 0
            self.d[D_PLC_RESPONSE_CODE] = 300
        elif command == 31:
            self.d[D_MACHINE_MODE] = 1
            self.d[D_PLC_RESPONSE_CODE] = 301
        elif command == 32:
            self.d[D_MACHINE_MODE] = 2
            self.d[D_PLC_RESPONSE_CODE] = 302
        elif command == 40:
            self._start_robot_manual(command_index)
        elif command == 50:
            self.d[D_PLC_RESPONSE_CODE] = 250
        elif command == 51:
            self.d[D_PLC_RESPONSE_CODE] = 251
        elif command == 60:
            self._start_semi_auto()
        else:
            self.d[D_PLC_RESPONSE_CODE] = 400
            self.d[D_PLC_STATUS_CODE] = 4

    def _start_bowl_dispense(self) -> None:
        if self.x[1]:
            self.d[D_PLC_RESPONSE_CODE] = 421
            return
        self.y[0] = True
        self.d[D_TEST_Y0_WORD] |= 1 << 0
        self.d[D_PLC_RESPONSE_CODE] = 220
        self._schedule(0.35, "bowl_arrive")

    def _start_robot_manual(self, command_index: int) -> None:
        self.d[D_ROBOT_MANUAL_STATUS] = 2
        self.d[D_ROBOT_MANUAL_ACK] = command_index
        self.d[D_ROBOT_MANUAL_RESULT] = 0
        self.d[D_ROBOT_MANUAL_ALARM] = 0
        self.d[D_ROBOT_IDLE] = 0
        self._schedule(0.8, "robot_manual_done")

    def _start_semi_auto(self) -> None:
        self.d[D_MACHINE_MODE] = 1
        self.d[D_MAIN_PROCESS_STEP] = 10
        self.d[D_PLC_RESPONSE_CODE] = 260
        self._schedule(0.4, "semi_step", 20)
        self._schedule(0.8, "semi_step", 30)
        self._schedule(1.2, "semi_step", 40)
        self._schedule(1.6, "semi_step", 50)
        self._schedule(2.0, "semi_step", 60)
        self._schedule(2.4, "semi_step", 70)
        self._schedule(2.8, "semi_step", 80)
        self._schedule(3.2, "semi_done")

    def _process_events(self, now: float) -> None:
        ready = [event for event in self.events if event.due <= now]
        self.events = [event for event in self.events if event.due > now]
        for event in ready:
            if event.name == "bowl_arrive":
                if self.current_scenario != 1:
                    self.x[1] = True
                    self.d[D_TEST_X0_WORD] |= 1 << 1
                    self.y[0] = False
                    self.d[D_TEST_Y0_WORD] &= ~(1 << 0)
            elif event.name == "robot_manual_done":
                self.d[D_ROBOT_MANUAL_STATUS] = 3
                self.d[D_ROBOT_MANUAL_RESULT] = 200
                self.d[D_ROBOT_IDLE] = 1
            elif event.name == "semi_step":
                self.d[D_MAIN_PROCESS_STEP] = event.value
            elif event.name == "semi_done":
                self.d[D_MAIN_PROCESS_STEP] = 0

    def _update_io_mirrors(self) -> None:
        # D15000/D15001亦可由外部控制器直接寫入。
        requested_x = self.d[D_TEST_X0_WORD]
        requested_y = self.d[D_TEST_Y0_WORD]
        for bit in range(16):
            self.x[bit] = bool(requested_x & (1 << bit))
            self.y[bit] = bool(requested_y & (1 << bit))

        if self.current_scenario == 1:
            self.x[1] = False
        if self.current_scenario == 2:
            self.x[2] = False

        x_word = sum((1 << bit) for bit, state in enumerate(self.x) if state)
        y_word = sum((1 << bit) for bit, state in enumerate(self.y) if state)
        self.d[D_TEST_X0_WORD] = x_word
        self.d[D_TEST_Y0_WORD] = y_word

        # HMI D1110位元：X0.1~X0.4、落碗Busy、半自動執行中。
        sensor_word = 0
        sensor_word |= int(self.x[1]) << 0
        sensor_word |= int(self.x[2]) << 1
        sensor_word |= int(self.x[3]) << 2
        sensor_word |= int(self.x[4]) << 3
        sensor_word |= int(self.y[0] and not self.x[1]) << 4
        sensor_word |= int(self.d[D_MAIN_PROCESS_STEP] != 0) << 5
        self.d[D_SENSOR_STATUS] = sensor_word

        for bit in range(16):
            self.coils[bit] = self.y[bit]
            self.discrete_inputs[bit] = self.x[bit]

    async def modbus_action(
        self,
        function_code: int,
        start_address: int,
        address: int,
        count: int,
        current_registers: list[int],
        set_values: Optional[list[int] | list[bool]],
    ) -> None:
        """在每次Modbus存取前後同步虛擬PLC資料。"""
        with self.lock:
            if function_code in (3, 6, 16, 22, 23):
                bank = self.d
            elif function_code == 4:
                bank = self.input_registers
            elif function_code in (1, 5, 15):
                bank = self.coils
            elif function_code == 2:
                bank = self.discrete_inputs
            else:
                return

            if set_values is not None:
                for offset, value in enumerate(set_values):
                    target = address + offset
                    if 0 <= target < len(bank):
                        bank[target] = bool(value) if isinstance(bank[target], bool) else int(value) & 0xFFFF

            # callback提供的是底層區塊；只更新本次請求會使用的範圍。
            for target in range(address, min(address + count, len(bank))):
                current_index = target - start_address
                if 0 <= current_index < len(current_registers):
                    current_registers[current_index] = bank[target]


def build_device(plc: VirtualPLC, device_id: int) -> SimDevice:
    coils = [SimData(0, count=IO_COUNT, values=False, datatype=DataType.BITS)]
    discrete = [SimData(0, count=IO_COUNT, values=False, datatype=DataType.BITS)]
    holding = [SimData(0, count=D_COUNT, values=0, datatype=DataType.UINT16)]
    inputs = [SimData(0, count=D_COUNT, values=0, datatype=DataType.UINT16)]
    return SimDevice(
        id=device_id,
        simdata=(coils, discrete, holding, inputs),
        action=plc.modbus_action,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP Ramen本機Modbus TCP虛擬PLC")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument(
        "--external-ipc",
        action="store_true",
        help="停用內建IPC心跳，改由6.IPC程式寫D1300",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    plc = VirtualPLC(internal_ipc=not args.external_ipc)
    plc.start()
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, signame, None)
        if signum is not None:
            try:
                loop.add_signal_handler(signum, stop.set)
            except (NotImplementedError, RuntimeError):
                pass

    device = build_device(plc, args.device_id)
    logging.info(
        "虛擬PLC啟動：Modbus TCP %s:%s，device_id=%s，IPC=%s",
        args.host,
        args.port,
        args.device_id,
        "external" if args.external_ipc else "internal simulator",
    )
    logging.info("HMI啟動參數：--ip %s --port %s", args.host, args.port)
    logging.info("按 Ctrl+C 停止")

    server_task = asyncio.create_task(
        StartAsyncTcpServer([device], address=(args.host, args.port))
    )
    try:
        await server_task
    finally:
        plc.stop()


def main() -> int:
    args = parse_args()
    if not (1 <= args.port <= 65535):
        raise SystemExit("port必須介於1~65535")
    if not (0 <= args.device_id <= 255):
        raise SystemExit("device-id必須介於0~255")
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
