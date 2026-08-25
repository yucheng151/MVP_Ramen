"""對正在執行 MVP_V2_100 的 AS200 Simulator 做真實整合診斷。

與 ``virtual_plc_modbus.py`` 不同，本測試不重建 PLC 邏輯；它直接連到
AS200 Simulator，並在背景啟動 IPC／Nachi 周邊回覆，再檢查 PLC 自己
產生的 HMI、IPC、Robot、X/Y 與 EMC 狀態。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading
import time
from dataclasses import dataclass

from pymodbus.client import ModbusTcpClient

from as200_peripheral_sim import AS200PeripheralSimulator


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "3.HMI" / "0.0.3"
sys.path.insert(0, str(HMI_DIR))

from HMI_command import HMICommand  # noqa: E402
from HMI_heartbeat import HMIHeartbeat  # noqa: E402
from HMI_plc_client import HMIPlcClient  # noqa: E402


D_HMI_COMMAND_CODE = 1000
D_HMI_COMMAND_INDEX = 1001
D_HMI_COMMAND_VALID = 1002
D_HMI_EMC_REQUEST = 1004
D_HMI_HEARTBEAT_RETURN = 1005
D_PLC_HEARTBEAT = 1100
D_PLC_COMMAND_ACK = 1102
D_PLC_COMMAND_RESPONSE = 1103
D_HMI_COMM_STATUS = 1105
D_PLC_STATUS = 1106
D_CONVEYOR_ALARM = 1107
D_EMC_STATUS = 1108
D_MACHINE_MODE = 1109
D_SENSOR_MIRROR = 1110
D_ROBOT_IDLE = 1124
D_IPC_COMM_STATUS = 1209
D_PLC_IPC_EMC = 1207
D_IPC_EMC_DONE = 1308
D_NACHI_STATUS = 12100

MODBUS_X0_BASE = 0x0400
MODBUS_Y0_BASE = 0x0500


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


class AS200Test:
    def __init__(self, host: str, port: int, device_id: int) -> None:
        self.host = host
        self.port = port
        self.device_id = device_id
        self.client = ModbusTcpClient(host, port=port, timeout=1.0)
        self.hmi_plc = HMIPlcClient(
            ip=host,
            port=port,
            slave_id=device_id,
            timeout=1.0,
        )
        self.hmi_heartbeat = HMIHeartbeat(self.hmi_plc)
        self.hmi_command = HMICommand(self.hmi_plc)
        self.peripheral_client = ModbusTcpClient(host, port=port, timeout=1.0)
        self.peripheral: AS200PeripheralSimulator | None = None
        self.peripheral_thread: threading.Thread | None = None
        self.results: list[CheckResult] = []

    def read_d(self, address: int) -> int:
        result = self.client.read_holding_registers(
            address=address,
            count=1,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"read D{address}: {result}")
        return int(result.registers[0]) & 0xFFFF

    def write_d(self, address: int, value: int) -> None:
        result = self.client.write_register(
            address=address,
            value=int(value) & 0xFFFF,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"write D{address}: {result}")

    def set_x(self, bit_no: int, value: bool) -> None:
        result = self.client.write_coil(
            address=MODBUS_X0_BASE + bit_no,
            value=bool(value),
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"write X0.{bit_no}: {result}")

    def read_x(self, bit_no: int) -> bool:
        result = self.client.read_coils(
            address=MODBUS_X0_BASE + bit_no,
            count=1,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"read X0.{bit_no}: {result}")
        return bool(result.bits[0])

    def read_y(self, bit_no: int) -> bool:
        result = self.client.read_coils(
            address=MODBUS_Y0_BASE + bit_no,
            count=1,
            device_id=self.device_id,
        )
        if result.isError():
            raise ConnectionError(f"read Y0.{bit_no}: {result}")
        return bool(result.bits[0])

    def add(self, name: str, status: str, detail: str) -> None:
        self.results.append(CheckResult(name, status, detail))
        print(f"[{status}] {name}: {detail}")

    def hmi_heartbeat_tick(self) -> None:
        result = self.hmi_heartbeat.tick()
        if result.plc_index is None and not self.hmi_plc.connected:
            raise ConnectionError(result.message)

    def wait_for(self, predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.hmi_heartbeat_tick()
            if predicate():
                return True
            time.sleep(0.08)
        return False

    def start_peripheral(self) -> None:
        if not self.peripheral_client.connect():
            raise ConnectionError("周邊模擬器無法連線 AS200")
        self.peripheral = AS200PeripheralSimulator(
            client=self.peripheral_client,
            device_id=self.device_id,
            ipc_delay=0.5,
            nachi_accept_delay=0.15,
            nachi_action_delay=0.8,
            pulse_seconds=0.15,
        )
        self.peripheral_thread = threading.Thread(
            target=self.peripheral.run,
            kwargs={"poll_seconds": 0.05, "duration": None},
            daemon=True,
        )
        self.peripheral_thread.start()

    def stop_peripheral(self) -> None:
        if self.peripheral is not None:
            self.peripheral.request_stop()
        if self.peripheral_thread is not None:
            self.peripheral_thread.join(timeout=2.0)
        self.peripheral_client.close()

    def send_hmi_command(self, command_code: int, timeout: float = 2.0) -> tuple[int, int, int]:
        result = self.hmi_command.send_command(command_code)
        if not result.ok:
            raise ConnectionError(result.message)
        index = result.command_index
        self.wait_for(lambda: self.read_d(D_PLC_COMMAND_ACK) == index, timeout)
        ack = self.read_d(D_PLC_COMMAND_ACK)
        response = self.read_d(D_PLC_COMMAND_RESPONSE)
        self.hmi_command.clear_command()
        return index, ack, response

    def test_connection_and_heartbeats(self) -> None:
        safe_input = self.read_x(0)
        self.add(
            "X0.0 Modbus位置讀值",
            "INFO",
            (
                f"Modbus讀回X0.0={int(safe_input)}；此值不能證明"
                "AS200 Simulator的PLC CPU輸入映像已被強制，"
                "安全回路以D1108/D1207的實際結果判定"
            ),
        )

        online = self.wait_for(lambda: self.read_d(D_HMI_COMM_STATUS) == 1, 3.0)
        self.add(
            "HMI心跳 D1100/D1005/D1105",
            "PASS" if online else "FAIL",
            f"D1105={self.read_d(D_HMI_COMM_STATUS)}",
        )

        ipc_online = self.wait_for(lambda: self.read_d(D_IPC_COMM_STATUS) == 1, 4.0)
        self.add(
            "IPC心跳 D1200/D1300/D1209",
            "PASS" if ipc_online else "FAIL",
            f"D1209={self.read_d(D_IPC_COMM_STATUS)}",
        )

        robot_idle = self.wait_for(lambda: bool(self.read_d(D_ROBOT_IDLE) & 1), 3.0)
        self.add(
            "Nachi Standby/Home與Robot_Idle",
            "PASS" if robot_idle else "FAIL",
            f"D12100=0x{self.read_d(D_NACHI_STATUS):04X}, D1124={self.read_d(D_ROBOT_IDLE)}",
        )

    def test_sensor_mapping(self) -> None:
        x_values = [int(self.read_x(bit_no)) for bit_no in range(1, 5)]
        mirror = self.read_d(D_SENSOR_MIRROR)
        details = [
            f"X0.{bit_no}(Modbus)={x_values[bit_no - 1]} / "
            f"D1110.{bit_no - 1}={int(bool(mirror & (1 << (bit_no - 1))))}"
            for bit_no in range(1, 5)
        ]

        self.add(
            "X0.1~X0.4與D1110觀測",
            "INFO",
            "; ".join(details)
            + "；Python不再把Modbus寫入X的讀回值當成PLC CPU輸入強制成功",
        )

    def test_command_and_interlocks(self) -> None:
        index, ack, response = self.send_hmi_command(6)
        self.add(
            "Alarm Reset CMD6交握",
            "PASS" if ack == index else "FAIL",
            f"Index={index}, ACK={ack}, Response={response}",
        )

        # EMC解除還包含IPC停止確認及Robot_Idle條件，不能在CMD6 ACK後
        # 同一個瞬間就判定失敗，最多等待3秒讓PLC完成後續掃描。
        self.wait_for(
            lambda: self.read_d(D_EMC_STATUS) == 0
            and self.read_d(D_PLC_IPC_EMC) == 0,
            3.0,
        )
        emc = self.read_d(D_EMC_STATUS)
        plc_to_ipc_emc = self.read_d(D_PLC_IPC_EMC)
        ipc_emc_done = self.read_d(D_IPC_EMC_DONE)
        if emc or plc_to_ipc_emc:
            self.add(
                "一般動作測試允許條件",
                "BLOCKED",
                (
                    f"D1108={emc}, D1207={plc_to_ipc_emc}, D1308={ipc_emc_done}; "
                    f"X0.0(Modbus讀值)={int(self.read_x(0))}, "
                    f"D1004={self.read_d(D_HMI_EMC_REQUEST)}; "
                    "PLC仍處於EMC。請在ISPSoft Simulator的裝置監控中"
                    "手動強制X0.0 ON，再重送CMD6；測試不繞過安全互鎖"
                ),
            )
        else:
            self.add(
                "一般動作測試允許條件",
                "PASS",
                "EMC已解除，可繼續落碗、輸送帶、IPC與Nachi動作測試",
            )

    def test_auto_mode_command(self) -> None:
        index, ack, response = self.send_hmi_command(32)
        auto_mode = self.wait_for(lambda: self.read_d(D_MACHINE_MODE) == 2, 2.0)
        mode = self.read_d(D_MACHINE_MODE)
        self.add(
            "自動模式CMD32",
            "PASS" if ack == index and response == 302 and auto_mode else "FAIL",
            f"Index={index}, ACK={ack}, Response={response}, D1109={mode}",
        )

    def test_status_snapshot(self) -> None:
        y_values = ", ".join(
            f"Y0.{bit_no}={int(self.read_y(bit_no))}" for bit_no in (0, 7, 8, 9)
        )
        self.add(
            "PLC狀態快照",
            "INFO",
            (
                f"PLCStatus={self.read_d(D_PLC_STATUS)}, "
                f"ConveyorAlarm=0x{self.read_d(D_CONVEYOR_ALARM):04X}, "
                f"MachineMode={self.read_d(D_MACHINE_MODE)}, {y_values}"
            ),
        )

    def run(self) -> int:
        if not self.client.connect():
            print(f"[FAIL] 無法連線 AS200 Simulator {self.host}:{self.port}")
            return 2
        if not self.hmi_plc.connect():
            print(f"[FAIL] HMI實際通訊模組無法連線 {self.host}:{self.port}")
            self.client.close()
            return 2
        original_command = {
            address: self.read_d(address)
            for address in (D_HMI_COMMAND_CODE, D_HMI_COMMAND_VALID)
        }
        try:
            # 不再用Modbus寫入X0.0。AS200 Simulator可能只回寫通訊位置，
            # 不會同步PLC CPU的實際輸入映像。X0.0請由ISPSoft手動強制，
            # 並以D1108/D1207是否解除作為安全回路的實際判據。
            self.start_peripheral()
            self.test_connection_and_heartbeats()
            self.test_sensor_mapping()
            self.test_command_and_interlocks()
            if self.read_d(D_EMC_STATUS) == 0 and self.read_d(D_PLC_IPC_EMC) == 0:
                self.test_auto_mode_command()
            self.test_status_snapshot()
        finally:
            for address, value in original_command.items():
                self.write_d(address, value)
            self.stop_peripheral()
            self.hmi_plc.close()
            self.client.close()

        failed = sum(result.status == "FAIL" for result in self.results)
        blocked = sum(result.status == "BLOCKED" for result in self.results)
        print(f"RESULT: FAIL={failed}, BLOCKED={blocked}")
        return 1 if failed or blocked else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP Ramen AS200真實PLC整合診斷")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10002)
    parser.add_argument("--device-id", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return AS200Test(args.host, args.port, args.device_id).run()


if __name__ == "__main__":
    raise SystemExit(main())
