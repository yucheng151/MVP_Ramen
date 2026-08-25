"""SIMULATION版專用的AS200測試控制器；FIELD版不得建立此物件。"""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import threading
import time

from pymodbus.client import ModbusTcpClient

from register_map import (
    HMI_ORDER_CABINET_NO,
    HMI_ORDER_FIRMNESS_NO,
    HMI_ORDER_INDEX,
    HMI_ORDER_UNIT_ID,
    HMI_ORDER_VALID,
    PLC_ORDER_ACK_INDEX,
    PLC_ORDER_ACK_UNIT_ID,
    PLC_ORDER_FIFO_COUNT,
    PLC_ORDER_RESPONSE_CODE,
)


D_SIMULATION = 8000
BIT_SIMULATION_MODE = 0
STATION_BITS = {0: None, 1: 1, 2: 2, 3: 3, 4: 4}


def split_dint(value: int) -> tuple[int, int]:
    raw = int(value) & 0xFFFFFFFF
    return raw & 0xFFFF, (raw >> 16) & 0xFFFF


def join_dint(low_word: int, high_word: int) -> int:
    raw = (int(high_word) << 16) | int(low_word)
    return raw - 0x100000000 if raw & 0x80000000 else raw


class SimulationController:
    """Write only the documented D8000 and HMI order simulation interfaces."""

    def __init__(self, plc) -> None:
        self.plc = plc
        self.pending_order_index: int | None = None
        self.last_message = "等待操作"
        self._peripheral = None
        self._peripheral_client = None
        self._peripheral_thread: threading.Thread | None = None
        self._stress_process: subprocess.Popen | None = None
        self._stress_live_path = (
            Path(__file__).resolve().parents[2]
            / "8.TEST_Code" / "logs" / "hmi_stress_live.json"
        )

    @property
    def peripheral_running(self) -> bool:
        return bool(
            self._peripheral_thread is not None
            and self._peripheral_thread.is_alive()
        )

    @property
    def stress_running(self) -> bool:
        return bool(
            self._stress_process is not None
            and self._stress_process.poll() is None
        )

    def start_stress(self, total_orders: int) -> bool:
        if self.stress_running:
            self.last_message = "自動壓力測試已在執行"
            return False
        if not 3 <= int(total_orders) <= 100000 or not self._require_plc():
            self.last_message = "訂單數量必須介於3到100000"
            return False
        fifo = self.plc.read_d(PLC_ORDER_FIFO_COUNT, 1)
        if fifo is None or int(fifo[0]) != 0:
            self.last_message = f"開始前PLC FIFO必須為0，目前為{fifo[0] if fifo else '--'}"
            return False

        # 耐久測試本身會建立周邊模擬器，先停止手動工作台的那一份。
        self.stop_peripheral()
        self._stress_live_path.parent.mkdir(parents=True, exist_ok=True)
        if self._stress_live_path.exists():
            self._stress_live_path.unlink()
        test_dir = Path(__file__).resolve().parents[2] / "8.TEST_Code"
        script = test_dir / "as200_1000_order_endurance_test.py"
        queue_window = min(16, max(3, int(total_orders)))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._stress_process = subprocess.Popen(
                [
                    sys.executable, str(script),
                    "--orders", str(int(total_orders)),
                    "--queue-window", str(queue_window),
                    "--live-state", str(self._stress_live_path),
                ],
                cwd=str(test_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        except OSError as exc:
            self._stress_process = None
            self.last_message = f"無法啟動自動壓力測試：{exc}"
            return False
        self.last_message = f"已開始自動連續測試 {total_orders} 碗"
        return True

    def read_stress_status(self) -> dict:
        default = {
            "status": "RUNNING" if self.stress_running else "IDLE",
            "target": 0, "submitted": 0, "completed": 0, "fifo": 0,
            "units": [], "error": "", "updated_at": "--",
        }
        if self._stress_live_path.exists():
            try:
                loaded = json.loads(self._stress_live_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    default.update(loaded)
            except (OSError, ValueError, TypeError):
                pass
        if self._stress_process is not None:
            exit_code = self._stress_process.poll()
            default["exit_code"] = exit_code
            if exit_code is not None and default["status"] in ("STARTING", "RUNNING"):
                default["status"] = "PASS" if exit_code == 0 else "FAIL"
                if exit_code != 0 and not default.get("error"):
                    default["error"] = f"測試程式提前結束，ExitCode={exit_code}"
        return default

    def stop_stress(self) -> None:
        process = self._stress_process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                process.kill()
        self._stress_process = None
        if self.plc.connected:
            self.plc.write_d(HMI_ORDER_VALID, 0)
            self.plc.write_d(D_SIMULATION, 0)
        self.last_message = "自動壓力測試已停止"

    def _require_plc(self) -> bool:
        if not self.plc.connected:
            self.last_message = "AS200 Simulator尚未連線"
            return False
        return True

    def read_status(self) -> dict | None:
        if not self._require_plc():
            return None
        simulation = self.plc.read_d(D_SIMULATION, 1)
        order_input = self.plc.read_d(HMI_ORDER_INDEX, 2)
        order_reply = self.plc.read_d(PLC_ORDER_ACK_UNIT_ID, 5)
        if simulation is None or order_input is None or order_reply is None:
            self.last_message = self.plc.last_error or "讀取模擬狀態失敗"
            return None

        ack_index = int(order_reply[2])
        if self.pending_order_index is not None and ack_index == self.pending_order_index:
            # Valid在PLC確認後自動清除，避免同一筆訂單重送。
            self.plc.write_d(HMI_ORDER_VALID, 0)
            self.pending_order_index = None

        word = int(simulation[0])
        return {
            "simulation_word": word,
            "enabled": bool(word & 0x0001),
            "station": next(
                (number for number, bit_no in STATION_BITS.items()
                 if bit_no is not None and word & (1 << bit_no)),
                0,
            ),
            "order_valid": bool(order_input[1]),
            "ack_unit_id": join_dint(order_reply[0], order_reply[1]),
            "ack_index": ack_index,
            "fifo_count": int(order_reply[3]),
            "response_code": int(order_reply[4]),
            "peripheral_running": self.peripheral_running,
        }

    def set_enabled(self, enabled: bool) -> bool:
        if not self._require_plc():
            return False
        current = self.plc.read_d(D_SIMULATION, 1)
        if current is None:
            return False
        word = int(current[0])
        word = word | 0x0001 if enabled else word & ~0x001F
        ok = self.plc.write_d(D_SIMULATION, word)
        self.last_message = "模擬模式已開啟" if ok and enabled else "模擬模式已關閉" if ok else "寫入D8000失敗"
        return ok

    def set_station(self, station: int) -> bool:
        if station not in STATION_BITS or not self._require_plc():
            return False
        current = self.plc.read_d(D_SIMULATION, 1)
        if current is None:
            return False
        # 一次只允許一個站點感測器ON，避免同一個碗同時存在兩站。
        word = (int(current[0]) & ~0x001E) | 0x0001
        bit_no = STATION_BITS[station]
        if bit_no is not None:
            word |= 1 << bit_no
        ok = self.plc.write_d(D_SIMULATION, word)
        names = {0: "站點感測器已全部清除", 1: "X0.1落碗到位", 2: "X0.2倒麵／UR1到位", 3: "X0.3 UR2到位", 4: "X0.4注湯到位"}
        self.last_message = names[station] if ok else "寫入站點模擬訊號失敗"
        return ok

    def submit_order(self, unit_id: int, cabinet_no: int, firmness_no: int) -> bool:
        if not self._require_plc():
            return False
        if not 1 <= cabinet_no <= 10 or firmness_no not in (1, 2, 3):
            self.last_message = "麵櫃或軟硬度設定錯誤"
            return False
        indexes = self.plc.read_d(HMI_ORDER_INDEX, 1)
        ack = self.plc.read_d(PLC_ORDER_ACK_INDEX, 1)
        if indexes is None or ack is None:
            return False
        order_index = (max(int(indexes[0]), int(ack[0])) + 1) & 0xFFFF
        if order_index == 0:
            order_index = 1
        low, high = split_dint(unit_id)
        self.plc.write_d(HMI_ORDER_VALID, 0)
        ok = self.plc.write_d_block(
            HMI_ORDER_UNIT_ID,
            [low, high, cabinet_no, firmness_no, order_index],
        ) and self.plc.write_d(HMI_ORDER_VALID, 1)
        if ok:
            self.pending_order_index = order_index
            self.last_message = f"訂單已送出：UnitID {unit_id} / Index {order_index}"
        else:
            self.last_message = self.plc.last_error or "PLC訂單寫入失敗"
        return ok

    def start_peripheral(self) -> bool:
        if self.peripheral_running:
            self.last_message = "IPC／UR／Nachi模擬器已在執行"
            return True
        if not self._require_plc():
            return False

        test_dir = Path(__file__).resolve().parents[2] / "8.TEST_Code"
        if str(test_dir) not in sys.path:
            sys.path.insert(0, str(test_dir))
        try:
            from as200_peripheral_sim import AS200PeripheralSimulator
        except Exception as exc:
            self.last_message = f"載入周邊模擬器失敗：{exc}"
            return False

        client = ModbusTcpClient(
            host=self.plc.ip, port=self.plc.port, timeout=1.0,
        )
        if not client.connect():
            self.last_message = "周邊模擬器無法連線AS200"
            return False
        peripheral = AS200PeripheralSimulator(
            client=client,
            device_id=self.plc.slave_id,
            ipc_delay=0.5,
            nachi_accept_delay=0.15,
            nachi_action_delay=0.8,
            pulse_seconds=1.0,
        )
        thread = threading.Thread(
            target=peripheral.run,
            kwargs={"poll_seconds": 0.05, "duration": None},
            name="hmi-as200-peripheral-sim",
            daemon=True,
        )
        self._peripheral_client = client
        self._peripheral = peripheral
        self._peripheral_thread = thread
        thread.start()
        time.sleep(0.05)
        self.last_message = "IPC／UR／Nachi周邊模擬已啟動"
        return thread.is_alive()

    def stop_peripheral(self) -> None:
        if self._peripheral is not None:
            self._peripheral.request_stop()
        if self._peripheral_thread is not None:
            self._peripheral_thread.join(timeout=2.0)
        if self._peripheral_client is not None:
            self._peripheral_client.close()
        self._peripheral = None
        self._peripheral_thread = None
        self._peripheral_client = None
        self.last_message = "IPC／UR／Nachi周邊模擬已停止"

    def close(self) -> None:
        self.stop_stress()
        self.stop_peripheral()


__all__ = ["SimulationController"]
