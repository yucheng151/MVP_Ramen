"""Unit tests for the read-only HMI full-auto PLC monitor."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "3.HMI" / "0.0.3"
sys.path.insert(0, str(HMI_DIR))

from auto_live_monitor import AutoLiveMonitor  # noqa: E402
from register_map import AUTO_MONITOR_MAGIC  # noqa: E402


def split_dint(value: int) -> tuple[int, int]:
    raw = int(value) & 0xFFFFFFFF
    return raw & 0xFFFF, (raw >> 16) & 0xFFFF


class FakePLC:
    def __init__(self, precise: bool) -> None:
        self.blocks = {}
        self.reads = []
        order = [0] * 9
        order[0:2] = split_dint(1008)
        order[2] = 8
        order[3] = 4
        order[4] = 200
        order[5:7] = split_dint(1004)
        order[7:9] = split_dint(4)
        self.blocks[(1130, 9)] = order
        self.blocks[(1109, 1)] = [2]

        debug = [0] * 32
        debug[2] = 0b00010101
        debug[3:6] = [40, 70, 0]
        debug[6] = 40
        debug[12] = 40
        debug[13] = 80
        debug[15:17] = split_dint(1004)
        debug[17:19] = split_dint(1004)
        debug[19:21] = split_dint(1004)
        debug[21:23] = split_dint(1003)
        debug[25] = 3
        debug[26:28] = split_dint(1005)
        debug[28:30] = split_dint(1004)
        debug[30] = 25
        debug[31] = 35
        self.blocks[(8000, 32)] = debug

        monitor = [0] * 35
        if precise:
            monitor[0] = AUTO_MONITOR_MAGIC
            monitor[1] = 1
            for offset, unit_id, bowl_state in (
                (2, 1007, 15), (5, 1006, 20),
                (8, 1005, 30), (11, 1004, 40),
            ):
                monitor[offset:offset + 2] = split_dint(unit_id)
                monitor[offset + 2] = bowl_state
            for offset, unit_id, state, cabinet in (
                (14, 1008, 40, 4),
                (18, 1009, 70, 7),
                (22, 0, 0, 0),
            ):
                monitor[offset:offset + 2] = split_dint(unit_id)
                monitor[offset + 2] = state
                monitor[offset + 3] = cabinet
            monitor[26] = 0b11000101
            monitor[27] = 120
            monitor[28] = 40
            monitor[29] = 40
            monitor[30] = 4
            monitor[31:33] = split_dint(1004)
            monitor[33:35] = split_dint(4)
        self.blocks[(8100, 35)] = monitor

    def read_d(self, address: int, count: int = 1):
        self.reads.append((address, count))
        return list(self.blocks[(address, count)])


def run() -> None:
    compatibility_plc = FakePLC(precise=False)
    compatibility = AutoLiveMonitor(
        compatibility_plc, allow_debug_fallback=True,
    ).read_snapshot()
    assert compatibility is not None
    assert compatibility["precise"] is False
    assert compatibility["fifo_count"] == 4
    assert compatibility["stations"][3]["unit_id"] == 1004
    assert compatibility["baskets"][0]["state"] == "煮麵中"

    precise_plc = FakePLC(precise=True)
    precise = AutoLiveMonitor(
        precise_plc, allow_debug_fallback=False,
    ).read_snapshot()
    assert precise is not None
    assert precise["precise"] is True
    assert [row["unit_id"] for row in precise["stations"]] == [1007, 1006, 1005, 1004]
    assert [row["unit_id"] for row in precise["baskets"]] == [1008, 1009, None]
    assert precise["baskets"][0]["cabinet_no"] == 4
    assert precise["active"]["ur1_active"] is True
    assert precise["active"]["ur2_active"] is True
    assert precise["complete_index"] == 4
    assert (8000, 32) not in precise_plc.reads

    field_unmapped_plc = FakePLC(precise=False)
    field_unmapped = AutoLiveMonitor(
        field_unmapped_plc, allow_debug_fallback=False,
    ).read_snapshot()
    assert field_unmapped is not None
    assert field_unmapped["available"] is False
    assert field_unmapped["mapping_required"] is True
    assert (8000, 32) not in field_unmapped_plc.reads
    print("[PASS] SIM/FIELD monitor isolation, compatibility and precise mappings")


if __name__ == "__main__":
    run()
