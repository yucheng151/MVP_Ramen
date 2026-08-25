"""Read-only recorder for the PLC automatic-flow Debug D registers.

No HMI UI event, Python exception or interpreted process event is written to
these files.  Every row is a timestamped raw PLC register snapshot captured
while automatic mode is active.
"""

from __future__ import annotations

from collections import deque
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading
import time
import uuid


DEBUG_START = 8000
DEBUG_COUNT = 32
MONITOR_START = 8100
MONITOR_COUNT = 35
ALL_ADDRESSES = tuple(range(DEBUG_START, DEBUG_START + DEBUG_COUNT)) + tuple(
    range(MONITOR_START, MONITOR_START + MONITOR_COUNT)
)


REGISTER_NAMES = {
    8000: "SimulationInputWord",
    8001: "BowlDebugBits",
    8002: "NoodleDebugBits",
    8003: "Basket1State",
    8004: "Basket2State",
    8005: "Basket3State",
    8006: "RightmostStation",
    8007: "CurrentCookJobState",
    8008: "NoodleActionStep",
    8009: "NoodleActionDebugBits",
    8010: "AutoFlowDebugBits",
    8011: "SoupDebugBits",
    8012: "HeadBowlState",
    8013: "HeadJobState",
    8014: "SoupSeenBits",
    8015: "HeadUnitID_Low",
    8016: "HeadUnitID_High",
    8017: "SoupRequestUnitID_Low",
    8018: "SoupRequestUnitID_High",
    8019: "SoupGrantUnitID_Low",
    8020: "SoupGrantUnitID_High",
    8021: "SoupDoneUnitID_Low",
    8022: "SoupDoneUnitID_High",
    8023: "FIFOHead",
    8024: "FIFOCount",
    8025: "URDoneFlags",
    8026: "UR1DoneUnitID_Low",
    8027: "UR1DoneUnitID_High",
    8028: "UR2DoneUnitID_Low",
    8029: "UR2DoneUnitID_High",
    8030: "StateAtUR1Done",
    8031: "StateAtUR2Done",
    8100: "MonitorMagic",
    8101: "MonitorVersion",
    8102: "Station1UnitID_Low",
    8103: "Station1UnitID_High",
    8104: "Station1BowlState",
    8105: "Station2UnitID_Low",
    8106: "Station2UnitID_High",
    8107: "Station2BowlState",
    8108: "Station3UnitID_Low",
    8109: "Station3UnitID_High",
    8110: "Station3BowlState",
    8111: "Station4UnitID_Low",
    8112: "Station4UnitID_High",
    8113: "Station4BowlState",
    8114: "Basket1UnitID_Low",
    8115: "Basket1UnitID_High",
    8116: "Basket1State",
    8117: "Basket1CabinetNo",
    8118: "Basket2UnitID_Low",
    8119: "Basket2UnitID_High",
    8120: "Basket2State",
    8121: "Basket2CabinetNo",
    8122: "Basket3UnitID_Low",
    8123: "Basket3UnitID_High",
    8124: "Basket3State",
    8125: "Basket3CabinetNo",
    8126: "AutoActiveFlags",
    8127: "NoodleActionStep",
    8128: "IPCActionStep",
    8129: "RightmostStation",
    8130: "FIFOCount",
    8131: "CompleteUnitID_Low",
    8132: "CompleteUnitID_High",
    8133: "CompleteIndex_Low",
    8134: "CompleteIndex_High",
}


class PLCDebugLog:
    def __init__(
        self,
        log_dir: Path | str,
        retention_days: int = 90,
        heartbeat_seconds: float = 60.0,
    ) -> None:
        self.log_dir = Path(log_dir)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.log_dir = Path(__file__).resolve().parent / "logs" / "plc_debug"
            self.log_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = max(1, int(retention_days))
        self.heartbeat_seconds = max(10.0, float(heartbeat_seconds))
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        self._lock = threading.RLock()
        self._previous: tuple[int, ...] | None = None
        self._last_write = 0.0
        self._sample_index = 0
        self.last_error = ""
        self.last_record: dict | None = None
        self._cleanup_old_files()
        self._write_address_map()

    def _paths(self, now: datetime | None = None) -> tuple[Path, Path]:
        day = (now or datetime.now()).strftime("%Y-%m-%d")
        return (
            self.log_dir / f"plc_debug_{day}.jsonl",
            self.log_dir / f"plc_debug_{day}.csv",
        )

    @property
    def current_jsonl_path(self) -> Path:
        return self._paths()[0]

    @property
    def current_csv_path(self) -> Path:
        return self._paths()[1]

    @property
    def address_map_path(self) -> Path:
        return self.log_dir / "plc_debug_address_map.csv"

    @staticmethod
    def join_dword(low_word: int, high_word: int) -> int:
        return (int(high_word) << 16) | int(low_word)

    def capture_blocks(
        self,
        debug_words,
        monitor_words,
        *,
        auto_enabled: bool,
        machine_mode_raw: int,
    ) -> bool:
        """Store one raw PLC snapshot when changed or heartbeat is due."""
        if not auto_enabled:
            with self._lock:
                self._previous = None
                self._last_write = 0.0
            return False
        if debug_words is None or monitor_words is None:
            self.last_error = "PLC Debug registers could not be read"
            return False
        if len(debug_words) != DEBUG_COUNT or len(monitor_words) != MONITOR_COUNT:
            self.last_error = (
                f"Unexpected PLC Debug size: D8000={len(debug_words)}, "
                f"D8100={len(monitor_words)}"
            )
            return False

        try:
            values = tuple(int(value) & 0xFFFF for value in (*debug_words, *monitor_words))
            with self._lock:
                now_mono = time.monotonic()
                if self._previous is None:
                    changed_indexes = list(range(len(values)))
                    reason = "INITIAL"
                else:
                    changed_indexes = [
                        index for index, (before, after) in enumerate(zip(self._previous, values))
                        if before != after
                    ]
                    reason = "CHANGE"

                if not changed_indexes and now_mono - self._last_write < self.heartbeat_seconds:
                    return False
                if not changed_indexes:
                    reason = "HEARTBEAT"

                changed_addresses = [ALL_ADDRESSES[index] for index in changed_indexes]
                changes = []
                for index in changed_indexes:
                    address = ALL_ADDRESSES[index]
                    before = None if self._previous is None else self._previous[index]
                    after = values[index]
                    changes.append({
                        "address": f"D{address}",
                        "name": REGISTER_NAMES.get(address, ""),
                        "before": before,
                        "after": after,
                        "before_hex": None if before is None else f"0x{before:04X}",
                        "after_hex": f"0x{after:04X}",
                    })

                self._sample_index += 1
                record = self._write_record(
                    values=values,
                    reason=reason,
                    changes=changes,
                    machine_mode_raw=int(machine_mode_raw) & 0xFFFF,
                )
                self._previous = values
                self._last_write = now_mono
                self.last_record = record
                self.last_error = ""
                return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _write_record(self, values, reason, changes, machine_mode_raw: int) -> dict:
        now = datetime.now().astimezone()
        registers = {
            f"D{address}": value for address, value in zip(ALL_ADDRESSES, values)
        }
        record = {
            "timestamp": now.isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            "sample_index": self._sample_index,
            "reason": reason,
            "machine_mode_raw": machine_mode_raw,
            "changed_addresses": [item["address"] for item in changes],
            "changes": changes,
            "registers": registers,
        }
        jsonl_path, csv_path = self._paths(now)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

        new_csv = not csv_path.exists() or csv_path.stat().st_size == 0
        fieldnames = (
            "timestamp", "session_id", "sample_index", "reason",
            "machine_mode_raw", "changed_addresses", "change_detail",
            *(f"D{address}" for address in ALL_ADDRESSES),
        )
        encoding = "utf-8-sig" if new_csv else "utf-8"
        with csv_path.open("a", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if new_csv:
                writer.writeheader()
            writer.writerow({
                "timestamp": record["timestamp"],
                "session_id": self.session_id,
                "sample_index": self._sample_index,
                "reason": reason,
                "machine_mode_raw": machine_mode_raw,
                "changed_addresses": ",".join(record["changed_addresses"]),
                "change_detail": json.dumps(changes, ensure_ascii=False, separators=(",", ":")),
                **registers,
            })
        return record

    def read_recent(self, limit: int = 250) -> list[dict]:
        rows: deque[dict] = deque(maxlen=max(1, int(limit)))
        with self._lock:
            for path in sorted(self.log_dir.glob("plc_debug_*.jsonl"))[-7:]:
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                rows.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                except OSError:
                    continue
        return list(rows)

    def _write_address_map(self) -> None:
        new_file = not self.address_map_path.exists()
        if not new_file:
            return
        try:
            with self.address_map_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("address", "name", "source"))
                writer.writeheader()
                for address in ALL_ADDRESSES:
                    writer.writerow({
                        "address": f"D{address}",
                        "name": REGISTER_NAMES.get(address, ""),
                        "source": "PLC raw read-only",
                    })
        except OSError as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"

    def _cleanup_old_files(self) -> None:
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        for pattern in ("plc_debug_*.jsonl", "plc_debug_*.csv"):
            for path in self.log_dir.glob(pattern):
                try:
                    if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                        path.unlink()
                except OSError:
                    continue


__all__ = [
    "ALL_ADDRESSES", "DEBUG_COUNT", "DEBUG_START", "MONITOR_COUNT",
    "MONITOR_START", "PLCDebugLog", "REGISTER_NAMES",
]
