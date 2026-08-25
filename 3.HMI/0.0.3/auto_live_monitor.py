"""Read-only PLC snapshot used by the full-auto bowl-flow monitor."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from register_map import (
    AUTO_MONITOR_MAGIC,
    AUTO_MONITOR_VERSION,
    PLC_AUTO_DEBUG_COUNT,
    PLC_AUTO_DEBUG_START,
    PLC_AUTO_MONITOR_COUNT,
    PLC_AUTO_MONITOR_START,
    PLC_MACHINE_MODE,
    PLC_ORDER_ACK_UNIT_ID,
)


BASKET_STATE_NAMES = {
    0: "空閒",
    10: "已分配",
    20: "等待拿生麵",
    30: "拿生麵下鍋",
    40: "煮麵中",
    50: "煮麵完成",
    60: "拿熟麵甩麵",
    70: "甩麵待碗",
    80: "倒麵進碗",
    90: "倒麵完成",
}

BOWL_STATE_NAMES = {
    0: "等待落碗",
    10: "落碗中",
    15: "前往倒麵／UR1站",
    20: "倒麵／UR1站作業",
    25: "前往UR2站",
    30: "UR2站作業",
    35: "前往注湯站",
    40: "注湯站作業",
    100: "已完成",
}


def join_dint(low_word: int, high_word: int) -> int:
    raw = (int(high_word) << 16) | int(low_word)
    return raw - 0x100000000 if raw & 0x80000000 else raw


def join_dword(low_word: int, high_word: int) -> int:
    return (int(high_word) << 16) | int(low_word)


def _station_for_bowl_state(bowl_state: int) -> int | None:
    if bowl_state in (10, 15):
        return 0
    if bowl_state in (20, 25):
        return 1
    if bowl_state in (30, 35):
        return 2
    if bowl_state == 40:
        return 3
    return None


def _station_rows() -> list[dict]:
    names = ("落碗", "倒麵 & UR1", "UR2", "注湯 & 完成")
    return [
        {"no": index + 1, "name": name, "unit_id": None,
         "bowl_state": 0, "state": "空閒", "exact": False}
        for index, name in enumerate(names)
    ]


class AutoLiveMonitor:
    """Poll the PLC auto-flow registers allowed by the selected HMI edition."""

    def __init__(self, plc, allow_debug_fallback: bool = True) -> None:
        self.plc = plc
        self.allow_debug_fallback = bool(allow_debug_fallback)

    def read_snapshot(
        self,
        *,
        mode_value: int | None = None,
        debug_block: list[int] | None = None,
        monitor_block: list[int] | None = None,
    ) -> Optional[dict]:
        order = self.plc.read_d(PLC_ORDER_ACK_UNIT_ID, 9)
        mode = (
            [int(mode_value)]
            if mode_value is not None
            else self.plc.read_d(PLC_MACHINE_MODE, 1)
        )
        if order is None or mode is None:
            return None

        precise = monitor_block
        if precise is None:
            precise = self.plc.read_d(
                PLC_AUTO_MONITOR_START, PLC_AUTO_MONITOR_COUNT,
            )
        if precise is not None and precise[0] == AUTO_MONITOR_MAGIC:
            # FIELD版不可讀取D8000模擬／除錯區。缺少的相容欄位以0表示。
            debug = [0] * PLC_AUTO_DEBUG_COUNT
            if self.allow_debug_fallback:
                debug_read = debug_block
                if debug_read is None:
                    debug_read = self.plc.read_d(
                        PLC_AUTO_DEBUG_START, PLC_AUTO_DEBUG_COUNT,
                    )
                if debug_read is not None:
                    debug = debug_read
            return self._parse_precise(order, mode[0], debug, precise)

        if not self.allow_debug_fallback:
            return self._parse_mapping_required(order, mode[0])

        debug = debug_block
        if debug is None:
            debug = self.plc.read_d(PLC_AUTO_DEBUG_START, PLC_AUTO_DEBUG_COUNT)
        if debug is None:
            return None
        return self._parse_compatibility(order, mode[0], debug)

    def _parse_mapping_required(self, order: list[int], mode: int) -> dict:
        """FIELD版缺少正式D8100映射時，明確顯示未配置而不借用假資料。"""
        result = self._base_snapshot(
            order, mode, [0] * PLC_AUTO_DEBUG_COUNT,
        )
        result.update(
            source="FIELD D8100未配置",
            precise=False,
            available=False,
            mapping_required=True,
            monitor_version=0,
            stations=_station_rows(),
            baskets=[
                {
                    "no": number, "state_no": 0, "state": "等待PLC映射",
                    "unit_id": None, "cabinet_no": None, "exact": False,
                }
                for number in range(1, 4)
            ],
            active={},
        )
        return result

    @staticmethod
    def _base_snapshot(order: list[int], mode: int, debug: list[int]) -> dict:
        head_unit_id = join_dint(debug[15], debug[16])
        soup_request_unit_id = join_dint(debug[17], debug[18])
        soup_grant_unit_id = join_dint(debug[19], debug[20])
        soup_done_unit_id = join_dint(debug[21], debug[22])
        ur1_done_unit_id = join_dint(debug[26], debug[27])
        ur2_done_unit_id = join_dint(debug[28], debug[29])
        return {
            "read_at": datetime.now().isoformat(timespec="seconds"),
            "machine_mode": int(mode),
            "ack_unit_id": join_dint(order[0], order[1]),
            "ack_index": int(order[2]),
            "fifo_count": int(order[3]),
            "order_response": int(order[4]),
            "complete_unit_id": join_dint(order[5], order[6]),
            "complete_index": join_dword(order[7], order[8]),
            "simulation_mode": bool(debug[0] & 0x0001),
            "bowl_debug_word": int(debug[1]),
            "noodle_debug_word": int(debug[2]),
            "basket_states": [int(value) for value in debug[3:6]],
            "rightmost_station": int(debug[6]),
            "cook_job_state": int(debug[7]),
            "noodle_action_step": int(debug[8]),
            "noodle_action_flags": int(debug[9]),
            "auto_flow_flags": int(debug[10]),
            "head_bowl_state": int(debug[12]),
            "head_job_state": int(debug[13]),
            "head_unit_id": head_unit_id,
            "soup_request_unit_id": soup_request_unit_id,
            "soup_grant_unit_id": soup_grant_unit_id,
            "soup_done_unit_id": soup_done_unit_id,
            "ur1_done_unit_id": ur1_done_unit_id,
            "ur2_done_unit_id": ur2_done_unit_id,
            "ur_done_flags": int(debug[25]),
            "ur1_done_bowl_state": int(debug[30]),
            "ur2_done_bowl_state": int(debug[31]),
        }

    def _parse_compatibility(
        self, order: list[int], mode: int, debug: list[int],
    ) -> dict:
        result = self._base_snapshot(order, mode, debug)
        stations = _station_rows()
        station_index = _station_for_bowl_state(result["head_bowl_state"])
        if station_index is not None and result["head_unit_id"]:
            stations[station_index].update(
                unit_id=result["head_unit_id"],
                bowl_state=result["head_bowl_state"],
                state=BOWL_STATE_NAMES.get(
                    result["head_bowl_state"],
                    f"BowlState {result['head_bowl_state']}",
                ),
                exact=True,
            )

        # The persistent done UnitIDs provide useful live context for the two
        # robot stations, but are marked non-exact because the bowl may already
        # have advanced when the HMI starts in the middle of a run.
        if (
            not stations[2]["unit_id"]
            and result["ur1_done_unit_id"]
            and result["ur1_done_unit_id"] != result["ur2_done_unit_id"]
        ):
            stations[2].update(
                unit_id=result["ur1_done_unit_id"],
                bowl_state=30,
                state="UR1完成，等待／執行UR2",
            )
        if (
            not stations[3]["unit_id"]
            and result["ur2_done_unit_id"]
            and result["ur2_done_unit_id"] != result["soup_done_unit_id"]
        ):
            stations[3].update(
                unit_id=result["ur2_done_unit_id"],
                bowl_state=40,
                state="UR2完成，等待／執行注湯",
            )

        baskets = [
            {
                "no": index + 1,
                "state_no": state,
                "state": BASKET_STATE_NAMES.get(state, f"State {state}"),
                "unit_id": None,
                "cabinet_no": None,
                "exact": False,
            }
            for index, state in enumerate(result["basket_states"])
        ]
        result.update(
            source="D8000相容模式",
            precise=False,
            available=True,
            mapping_required=False,
            monitor_version=0,
            stations=stations,
            baskets=baskets,
            active={
                "robot_idle": bool(result["noodle_debug_word"] & (1 << 0)),
                "load_grant": bool(result["noodle_debug_word"] & (1 << 1)),
                "noodle_busy": bool(result["noodle_debug_word"] & (1 << 2)),
                "noodle_zone_locked": bool(result["noodle_debug_word"] & (1 << 3)),
                "shake_grant": bool(result["noodle_debug_word"] & (1 << 4)),
                "drop_grant": bool(result["noodle_debug_word"] & (1 << 5)),
            },
        )
        return result

    def _parse_precise(
        self, order: list[int], mode: int, debug: list[int], precise: list[int],
    ) -> dict:
        result = self._base_snapshot(order, mode, debug)
        stations = _station_rows()
        station_offsets = (2, 5, 8, 11)
        for row, offset in zip(stations, station_offsets):
            unit_id = join_dint(precise[offset], precise[offset + 1])
            bowl_state = int(precise[offset + 2])
            row.update(
                unit_id=unit_id or None,
                bowl_state=bowl_state,
                state=(
                    BOWL_STATE_NAMES.get(bowl_state, f"BowlState {bowl_state}")
                    if unit_id else "空閒"
                ),
                exact=True,
            )

        baskets = []
        for number, offset in enumerate((14, 18, 22), 1):
            unit_id = join_dint(precise[offset], precise[offset + 1])
            state_no = int(precise[offset + 2])
            baskets.append({
                "no": number,
                "unit_id": unit_id or None,
                "state_no": state_no,
                "state": BASKET_STATE_NAMES.get(state_no, f"State {state_no}"),
                "cabinet_no": int(precise[offset + 3]) or None,
                "exact": True,
            })

        flags = int(precise[26])
        result.update(
            source="D8100精確監看",
            precise=True,
            available=True,
            mapping_required=False,
            monitor_version=int(precise[1]),
            stations=stations,
            baskets=baskets,
            noodle_action_step=int(precise[27]),
            ipc_action_step=int(precise[28]),
            rightmost_station=int(precise[29]),
            fifo_count=int(precise[30]),
            complete_unit_id=join_dint(precise[31], precise[32]),
            complete_index=join_dword(precise[33], precise[34]),
            active={
                "robot_idle": bool(flags & (1 << 0)),
                "load_grant": bool(flags & (1 << 1)),
                "noodle_busy": bool(flags & (1 << 2)),
                "noodle_zone_locked": bool(flags & (1 << 3)),
                "shake_grant": bool(flags & (1 << 4)),
                "drop_grant": bool(flags & (1 << 5)),
                "ur1_active": bool(flags & (1 << 6)),
                "ur2_active": bool(flags & (1 << 7)),
                "conveyor_request": bool(flags & (1 << 8)),
                "soup_request": bool(flags & (1 << 9)),
            },
        )
        return result


__all__ = [
    "AUTO_MONITOR_MAGIC",
    "AUTO_MONITOR_VERSION",
    "AutoLiveMonitor",
    "BASKET_STATE_NAMES",
    "BOWL_STATE_NAMES",
    "join_dint",
    "join_dword",
]
