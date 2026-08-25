"""Tests for the SIMULATION-only HMI control panel."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "3.HMI" / "0.0.3"
sys.path.insert(0, str(HMI_DIR))

from simulation_control import SimulationController  # noqa: E402


class FakePLC:
    def __init__(self) -> None:
        self.connected = True
        self.last_error = None
        self.ip = "127.0.0.1"
        self.port = 10002
        self.slave_id = 1
        self.registers = {8000: 0xA000, 1024: 7, 1025: 0}
        for address in range(1130, 1135):
            self.registers[address] = 0
        self.registers[1132] = 6

    def read_d(self, address: int, count: int = 1):
        return [self.registers.get(address + offset, 0) for offset in range(count)]

    def write_d(self, address: int, value: int) -> bool:
        self.registers[address] = int(value) & 0xFFFF
        return True

    def write_d_block(self, address: int, values: list[int]) -> bool:
        for offset, value in enumerate(values):
            self.registers[address + offset] = int(value) & 0xFFFF
        return True


def run() -> None:
    plc = FakePLC()
    controller = SimulationController(plc)

    assert controller.set_enabled(True)
    assert plc.registers[8000] == 0xA001
    assert controller.set_station(2)
    assert plc.registers[8000] == 0xA005
    assert controller.set_station(4)
    assert plc.registers[8000] == 0xA011
    assert controller.set_station(0)
    assert plc.registers[8000] == 0xA001

    assert controller.submit_order(30001234, 4, 2)
    assert plc.registers[1022] == 4
    assert plc.registers[1023] == 2
    assert plc.registers[1024] == 8
    assert plc.registers[1025] == 1

    plc.registers[1130] = plc.registers[1020]
    plc.registers[1131] = plc.registers[1021]
    plc.registers[1132] = 8
    plc.registers[1133] = 1
    plc.registers[1134] = 200
    status = controller.read_status()
    assert status is not None
    assert status["ack_unit_id"] == 30001234
    assert status["response_code"] == 200
    assert plc.registers[1025] == 0

    assert controller.set_enabled(False)
    assert plc.registers[8000] == 0xA000
    print("[PASS] HMI simulation D8000 controls and D1020 order handshake")


if __name__ == "__main__":
    run()
