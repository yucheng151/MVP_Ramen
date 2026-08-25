"""AS200 Simulator 全自動收單與第一個落碗動作整合測試。"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from pymodbus.client import ModbusTcpClient

from as200_peripheral_sim import AS200PeripheralSimulator


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "3.HMI" / "0.0.3"
sys.path.insert(0, str(HMI_DIR))

from HMI_command import HMICommand  # noqa: E402
from HMI_heartbeat import HMIHeartbeat  # noqa: E402
from HMI_plc_client import HMIPlcClient  # noqa: E402


HOST = "127.0.0.1"
PORT = 10002
DEVICE_ID = 1

D_ORDER_UNIT_ID = 1020
D_ORDER_CABINET = 1022
D_ORDER_FIRMNESS = 1023
D_ORDER_INDEX = 1024
D_ORDER_VALID = 1025

D_ORDER_ACK_UNIT_ID = 1130
D_ORDER_ACK_INDEX = 1132
D_ORDER_FIFO_COUNT = 1133
D_ORDER_RESPONSE = 1134

D_HMI_COMM_STATUS = 1105
D_EMC_STATUS = 1108
D_MACHINE_MODE = 1109
D_PLC_IPC_EMC = 1207
D_SIMULATION = 8000
D_BOWL_DEBUG = 8001

MODBUS_Y0_BASE = 0x0500


def split_dint(value: int) -> list[int]:
    raw = int(value) & 0xFFFFFFFF
    return [raw & 0xFFFF, (raw >> 16) & 0xFFFF]


def join_dint(words: list[int]) -> int:
    raw = (int(words[1]) << 16) | int(words[0])
    return raw - 0x100000000 if raw & 0x80000000 else raw


class OrderIntegrationTest:
    def __init__(self) -> None:
        self.raw = ModbusTcpClient(HOST, port=PORT, timeout=1.0)
        self.peripheral_raw = ModbusTcpClient(HOST, port=PORT, timeout=1.0)
        self.hmi = HMIPlcClient(
            ip=HOST,
            port=PORT,
            slave_id=DEVICE_ID,
            timeout=1.0,
        )
        self.heartbeat = HMIHeartbeat(self.hmi)
        self.command = HMICommand(self.hmi)
        self.peripheral: AS200PeripheralSimulator | None = None
        self.peripheral_thread: threading.Thread | None = None

    def read_d(self, address: int, count: int = 1) -> list[int]:
        result = self.raw.read_holding_registers(
            address=address,
            count=count,
            device_id=DEVICE_ID,
        )
        if result.isError():
            raise ConnectionError(f"read D{address}: {result}")
        return [int(value) & 0xFFFF for value in result.registers]

    def write_d(self, address: int, value: int) -> None:
        result = self.raw.write_register(
            address=address,
            value=int(value) & 0xFFFF,
            device_id=DEVICE_ID,
        )
        if result.isError():
            raise ConnectionError(f"write D{address}: {result}")

    def write_block(self, address: int, values: list[int]) -> None:
        result = self.raw.write_registers(
            address=address,
            values=[int(value) & 0xFFFF for value in values],
            device_id=DEVICE_ID,
        )
        if result.isError():
            raise ConnectionError(f"write D{address} block: {result}")

    def read_y(self, bit_no: int) -> bool:
        result = self.raw.read_coils(
            address=MODBUS_Y0_BASE + bit_no,
            count=1,
            device_id=DEVICE_ID,
        )
        if result.isError():
            raise ConnectionError(f"read Y0.{bit_no}: {result}")
        return bool(result.bits[0])

    def tick_for(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.heartbeat.tick()
            time.sleep(0.05)

    def wait_for(self, predicate, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.heartbeat.tick()
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def send_command(self, code: int, expected_response: int) -> bool:
        result = self.command.send_command(code)
        if not result.ok:
            print(f"[FAIL] CMD{code} write: {result.message}")
            return False
        accepted = self.wait_for(
            lambda: self.read_d(1102)[0] == result.command_index,
            3.0,
        )
        ack = self.read_d(1102)[0]
        response = self.read_d(1103)[0]
        self.command.clear_command()
        ok = accepted and response == expected_response
        print(
            f"[{'PASS' if ok else 'FAIL'}] CMD{code}: "
            f"Index={result.command_index}, ACK={ack}, Response={response}"
        )
        return ok

    def start_peripheral(self) -> None:
        if not self.peripheral_raw.connect():
            raise ConnectionError("Peripheral simulator cannot connect")
        self.peripheral = AS200PeripheralSimulator(
            client=self.peripheral_raw,
            device_id=DEVICE_ID,
            ipc_delay=0.5,
            nachi_accept_delay=0.15,
            nachi_action_delay=0.8,
            # AS200軟體模擬的掃描與Modbus輪詢比實機慢，
            # 將外部設備完成訊號保持1秒，避免模擬測試漏接。
            pulse_seconds=1.0,
        )
        self.peripheral_thread = threading.Thread(
            target=self.peripheral.run,
            kwargs={"poll_seconds": 0.05, "duration": None},
            daemon=True,
        )
        self.peripheral_thread.start()

    def stop(self) -> None:
        if self.peripheral is not None:
            self.peripheral.request_stop()
        if self.peripheral_thread is not None:
            self.peripheral_thread.join(timeout=2.0)
        self.peripheral_raw.close()
        self.hmi.close()
        self.raw.close()

    def run(self) -> int:
        if not self.raw.connect() or not self.hmi.connect():
            print("[FAIL] Cannot connect AS200 Simulator")
            return 2

        original_simulation_word = 0
        self.start_peripheral()
        try:
            original_simulation_word = self.read_d(D_SIMULATION)[0]
            self.tick_for(1.5)
            online = self.read_d(D_HMI_COMM_STATUS)[0] == 1
            print(f"[{'PASS' if online else 'FAIL'}] HMI online: D1105={int(online)}")
            if not online:
                return 1

            if not self.send_command(6, 201):
                return 1

            safe = self.wait_for(
                lambda: self.read_d(D_EMC_STATUS)[0] == 0
                and self.read_d(D_PLC_IPC_EMC)[0] == 0,
                3.0,
            )
            print(
                f"[{'PASS' if safe else 'FAIL'}] EMC: "
                f"D1108={self.read_d(D_EMC_STATUS)[0]}, "
                f"D1207={self.read_d(D_PLC_IPC_EMC)[0]}"
            )
            if not safe:
                return 1

            # 先在手動模式收單，避免尚未確認FIFO前啟動任何自動輸出。
            if not self.send_command(30, 300):
                return 1

            before_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
            old_input_index = self.read_d(D_ORDER_INDEX)[0]
            old_ack_index = self.read_d(D_ORDER_ACK_INDEX)[0]
            order_index = (max(old_input_index, old_ack_index) + 1) & 0xFFFF
            if order_index == 0:
                order_index = 1
            # 每次執行使用不同的正整數UnitID，避免FIFO內仍有舊訂單時被判定重複。
            unit_id = 26000000 + (int(time.time()) % 999999)

            self.write_d(D_ORDER_VALID, 0)
            self.write_block(
                D_ORDER_UNIT_ID,
                split_dint(unit_id) + [1, 2, order_index],
            )
            self.write_d(D_ORDER_VALID, 1)

            acknowledged = self.wait_for(
                lambda: self.read_d(D_ORDER_ACK_INDEX)[0] == order_index,
                3.0,
            )
            ack_unit_id = join_dint(self.read_d(D_ORDER_ACK_UNIT_ID, 2))
            ack_index = self.read_d(D_ORDER_ACK_INDEX)[0]
            response = self.read_d(D_ORDER_RESPONSE)[0]
            after_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
            self.write_d(D_ORDER_VALID, 0)

            order_ok = (
                acknowledged
                and ack_unit_id == unit_id
                and ack_index == order_index
                and response == 200
                and after_count == before_count + 1
            )
            print(
                f"[{'PASS' if order_ok else 'FAIL'}] Order intake: "
                f"UnitID={unit_id}, ACKUnitID={ack_unit_id}, "
                f"Index={order_index}, ACKIndex={ack_index}, "
                f"Response={response}, FIFO={before_count}->{after_count}"
            )
            if not order_ok:
                return 1

            # 接單成功後切入全自動，確認第一個落碗要求抵達既有輸出程式。
            if not self.send_command(32, 302):
                return 1

            mode_auto = self.read_d(D_MACHINE_MODE)[0] == 2
            # AS200 Simulator的Y Modbus線圈位址未必等同實機映射，
            # 以PLC自行鏡射到D8001.5的Y0.0狀態作為可信判斷。
            bowl_output = self.wait_for(
                lambda: bool(self.read_d(D_BOWL_DEBUG)[0] & (1 << 5)),
                5.0,
            )
            print(
                f"[{'PASS' if mode_auto else 'FAIL'}] Auto mode: "
                f"D1109={self.read_d(D_MACHINE_MODE)[0]}"
            )
            print(
                f"[{'PASS' if bowl_output else 'BLOCKED'}] First bowl output: "
                f"PLC_DebugY0.0={int(bool(self.read_d(D_BOWL_DEBUG)[0] & (1 << 5)))}, "
                f"RawModbusY0.0={int(self.read_y(0))}"
            )

            simulation_word = self.read_d(D_SIMULATION)[0]
            debug_word = self.read_d(D_BOWL_DEBUG)[0]
            print(
                "[DEBUG] "
                f"D8000=0x{simulation_word:04X}, "
                f"D8001=0x{debug_word:04X}, "
                f"ZoneFree={(debug_word >> 0) & 1}, "
                f"Request={(debug_word >> 1) & 1}, "
                f"Grant={(debug_word >> 2) & 1}, "
                f"StartPulse={(debug_word >> 3) & 1}, "
                f"Busy={(debug_word >> 4) & 1}, "
                f"DebugY00={(debug_word >> 5) & 1}, "
                f"BowlArrived={(debug_word >> 6) & 1}"
            )

            if bowl_output:
                # 開啟測試模式並模擬X0.1到位，再放開X0.1。
                self.write_d(D_SIMULATION, original_simulation_word | 0x0003)
                self.tick_for(0.2)
                active_simulation = self.read_d(D_SIMULATION)[0]
                active_debug = self.read_d(D_BOWL_DEBUG)[0]
                print(
                    "[DEBUG] Simulated X0.1 held ON: "
                    f"D8000=0x{active_simulation:04X}, "
                    f"BowlArrived={(active_debug >> 6) & 1}, "
                    f"Busy={(active_debug >> 4) & 1}, "
                    f"DebugY00={(active_debug >> 5) & 1}, "
                    f"D8001=0x{active_debug:04X}"
                )
                arrived_completed = self.wait_for(
                    lambda: not bool(self.read_d(D_BOWL_DEBUG)[0] & (1 << 4)),
                    3.0,
                )
                self.write_d(D_SIMULATION, (original_simulation_word | 0x0001) & ~0x0002)
                self.tick_for(0.3)
                final_debug = self.read_d(D_BOWL_DEBUG)[0]
                output_released = not bool(final_debug & (1 << 5))
                print(
                    f"[{'PASS' if arrived_completed and output_released else 'FAIL'}] "
                    "Simulated X0.1 bowl arrival: "
                    f"Busy={(final_debug >> 4) & 1}, "
                    f"DebugY00={(final_debug >> 5) & 1}, "
                    f"BowlArrived={(final_debug >> 6) & 1}, "
                    f"D8001=0x{final_debug:04X}"
                )
                return 0 if arrived_completed and output_released else 1
            return 1
        finally:
            self.write_d(D_ORDER_VALID, 0)
            self.write_d(D_SIMULATION, original_simulation_word)
            self.stop()


if __name__ == "__main__":
    raise SystemExit(OrderIntegrationTest().run())
