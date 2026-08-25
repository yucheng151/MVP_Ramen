"""Regression test for the read-only PLC Debug D-register logger."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import tempfile


TEST_DIR = Path(__file__).resolve().parent
HMI_DIR = (
    TEST_DIR
    if (TEST_DIR / "plc_debug_log.py").exists()
    else TEST_DIR.parent / "3.HMI" / "0.0.3"
)
sys.path.insert(0, str(HMI_DIR))

from plc_debug_log import (  # noqa: E402
    DEBUG_COUNT,
    MONITOR_COUNT,
    PLCDebugLog,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mvp_plc_debug_") as temp_dir:
        log = PLCDebugLog(temp_dir, retention_days=90, heartbeat_seconds=60)
        debug = [0] * DEBUG_COUNT
        monitor = [0] * MONITOR_COUNT

        # 非Auto模式不可產生PLC Debug紀錄。
        assert not log.capture_blocks(
            debug, monitor, auto_enabled=False, machine_mode_raw=1,
        )
        assert log.read_recent() == []

        # Auto初始快照完整保留兩個D區塊。
        debug[2] = 0x0055       # D8002
        debug[3:6] = [20, 40, 50]
        monitor[30] = 7         # D8130 FIFOCount
        monitor[31] = 0x5678    # D8131 CompleteUnitID low
        monitor[32] = 0x1234    # D8132 CompleteUnitID high
        assert log.capture_blocks(
            debug, monitor, auto_enabled=True, machine_mode_raw=2,
        )

        # 未變更且未到心跳時間，不重複寫入。
        assert not log.capture_blocks(
            debug, monitor, auto_enabled=True, machine_mode_raw=2,
        )

        # PLC原始D值變更時新增一筆，且列出實際變更位址。
        debug[8] = 50           # D8008 NoodleActionStep
        monitor[16] = 60        # D8116 Basket1State
        assert log.capture_blocks(
            debug, monitor, auto_enabled=True, machine_mode_raw=2,
        )

        rows = log.read_recent()
        assert len(rows) == 2
        assert rows[0]["reason"] == "INITIAL"
        assert rows[0]["registers"]["D8002"] == 0x0055
        assert rows[0]["registers"]["D8130"] == 7
        assert rows[0]["registers"]["D8131"] == 0x5678
        assert rows[0]["registers"]["D8132"] == 0x1234
        assert rows[1]["reason"] == "CHANGE"
        assert set(rows[1]["changed_addresses"]) == {"D8008", "D8116"}
        assert rows[1]["registers"]["D8008"] == 50
        assert rows[1]["registers"]["D8116"] == 60

        with log.current_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        assert len(csv_rows) == 2
        for column in ("D8000", "D8031", "D8100", "D8134"):
            assert column in csv_rows[0]

        with log.current_jsonl_path.open("r", encoding="utf-8") as handle:
            json_rows = [json.loads(line) for line in handle if line.strip()]
        assert len(json_rows) == 2
        assert log.address_map_path.exists()

        print("RESULT: PASS - PLC Debug raw D-register logging")


if __name__ == "__main__":
    main()
