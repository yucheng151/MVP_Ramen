#!/usr/bin/env python3
"""MVP 拉麵機 PLC 全自動流程的本機參考模型與壓力測試。

這支程式不讀取、也不執行 ISPSoft 的 .isp 專案檔。它依照目前 PLC
規劃重建一份可執行的狀態模型，用來在沒有實體 PLC 時檢查流程不變量：

* 最多三個麵篩同時工作，且 UnitID 不得配錯麵篩。
* 不同煮麵時間允許後下鍋的麵先煮好。
* 上一碗未到 X0.2 前，不得落下一碗。
* 放麵完成後才能執行 UR1 CMD101，且 CMD103 必須先完成。
* UR1 CMD101 與 UR2 CMD102 不得同時執行。
* Nachi 與 UR1 CMD101 / UR2 CMD102 不得同時進入共用碰撞區。
* 碗依序經過 X0.2、X0.3、X0.4，完成 UnitID 保持 FIFO。

執行：
    python plc_auto_logic_sim.py
    python plc_auto_logic_sim.py --trace
    python plc_auto_logic_sim.py --random-tests 200
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional


# DUT_NoodleBasket.State
BASKET_FREE = 0
BASKET_ASSIGNED = 10
BASKET_WAIT_LOAD = 20
BASKET_LOADING = 30
BASKET_COOKING = 40
BASKET_COOKED = 50
BASKET_SHAKING = 60
BASKET_STANDBY = 70
BASKET_DROPPING = 80

# DUT_Unit.BowlState
BOWL_WAIT_DROP = 0
BOWL_DROP_RUNNING = 10
BOWL_TO_STATION20 = 15
BOWL_AT_STATION20 = 20
BOWL_TO_STATION30 = 25
BOWL_AT_STATION30 = 30
BOWL_TO_STATION40 = 35
BOWL_AT_STATION40 = 40
BOWL_COMPLETE = 100


class LogicViolation(RuntimeError):
    """流程不變量遭破壞。"""


@dataclass
class Unit:
    unit_id: int
    cabinet_no: int
    firmness_no: int
    cook_ticks: int
    fifo_index: int
    basket_no: int = 0
    bowl_state: int = BOWL_WAIT_DROP
    travel_remaining: int = 0
    vision_done: bool = False
    noodle_drop_done: bool = False
    ur1_done: bool = False
    ur2_done: bool = False
    soup_done: bool = False


@dataclass
class Basket:
    number: int
    state: int = BASKET_FREE
    unit_id: int = 0
    cabinet_no: int = 0
    firmness_no: int = 0
    cook_remaining: int = 0
    cooked_tick: Optional[int] = None

    def clear(self) -> None:
        self.state = BASKET_FREE
        self.unit_id = 0
        self.cabinet_no = 0
        self.firmness_no = 0
        self.cook_remaining = 0
        self.cooked_tick = None


@dataclass
class Action:
    kind: str
    unit_id: int
    remaining: int
    basket_no: int = 0


@dataclass
class SimulationResult:
    name: str
    ticks: int
    order_ids: list[int]
    completed_ids: list[int]
    cooked_order: list[int]
    event_log: list[str] = field(default_factory=list)


class RamenPLCSimulation:
    """目前 PLC 架構的離散時間參考模型。"""

    DROP_TICKS = 2
    TRAVEL_TO_20_TICKS = 3
    TRAVEL_TO_30_TICKS = 4
    TRAVEL_TO_40_TICKS = 3
    NACHI_LOAD_TICKS = 2
    NACHI_SHAKE_TICKS = 2
    NACHI_DROP_TICKS = 2
    UR_VISION_TICKS = 2
    UR1_TICKS = 3
    UR2_TICKS = 3
    SOUP_TICKS = 2

    def __init__(self, name: str, units: Iterable[Unit], max_ticks: int = 5000):
        self.name = name
        self.units = list(units)
        self.unit_by_id = {unit.unit_id: unit for unit in self.units}
        self.baskets = [Basket(number=index) for index in range(1, 4)]
        self.max_ticks = max_ticks
        self.tick_no = 0
        self.nachi_action: Optional[Action] = None
        self.ur_action: Optional[Action] = None
        self.bowl_action: Optional[Action] = None
        self.soup_action: Optional[Action] = None
        self.conveyor_running = False
        self.completed_ids: list[int] = []
        self.cooked_order: list[int] = []
        self.drop_started_ids: list[int] = []
        self.event_log: list[str] = []

        if len(self.unit_by_id) != len(self.units):
            raise LogicViolation("訂單中存在重複 UnitID")

    def log(self, message: str) -> None:
        self.event_log.append(f"T{self.tick_no:04d} {message}")

    def unit(self, unit_id: int) -> Unit:
        return self.unit_by_id[unit_id]

    def basket(self, basket_no: int) -> Basket:
        return self.baskets[basket_no - 1]

    def run(self) -> SimulationResult:
        while len(self.completed_ids) < len(self.units):
            if self.tick_no >= self.max_ticks:
                waiting = [
                    (unit.unit_id, unit.bowl_state, unit.basket_no)
                    for unit in self.units
                    if unit.bowl_state != BOWL_COMPLETE
                ]
                raise LogicViolation(f"流程逾時／疑似死鎖：{waiting}")
            self.tick()

        expected = [unit.unit_id for unit in self.units]
        if self.completed_ids != expected:
            raise LogicViolation(
                f"完成 UnitID 未保持 FIFO：expected={expected}, actual={self.completed_ids}"
            )

        return SimulationResult(
            name=self.name,
            ticks=self.tick_no,
            order_ids=expected,
            completed_ids=list(self.completed_ids),
            cooked_order=list(self.cooked_order),
            event_log=list(self.event_log),
        )

    def tick(self) -> None:
        self.tick_no += 1
        self._advance_actions()
        self._advance_cooking()
        self._advance_conveyor()
        self._assign_free_baskets()
        self._schedule_bowl_drop()
        self._schedule_soup()
        self._schedule_ur()
        self._schedule_nachi()
        self._decide_conveyor()
        self._check_invariants()

    # ------------------------------------------------------------------
    # 動作完成
    # ------------------------------------------------------------------
    def _advance_actions(self) -> None:
        for attr in ("bowl_action", "soup_action", "ur_action", "nachi_action"):
            action = getattr(self, attr)
            if action is None:
                continue
            action.remaining -= 1
            if action.remaining <= 0:
                setattr(self, attr, None)
                self._complete_action(action)

    def _complete_action(self, action: Action) -> None:
        unit = self.unit(action.unit_id)

        if action.kind == "bowl_drop":
            if unit.bowl_state != BOWL_DROP_RUNNING:
                raise LogicViolation("落碗完成時 BowlState 不是 10")
            unit.bowl_state = BOWL_TO_STATION20
            unit.travel_remaining = self.TRAVEL_TO_20_TICKS
            self.log(f"Unit {unit.unit_id}: 落碗完成，前往 X0.2")
            return

        if action.kind == "nashi_load":
            basket = self.basket(action.basket_no)
            if basket.state != BASKET_LOADING or basket.unit_id != unit.unit_id:
                raise LogicViolation("Nachi拿生麵完成時麵篩資料不一致")
            basket.state = BASKET_COOKING
            basket.cook_remaining = unit.cook_ticks
            self.log(
                f"Unit {unit.unit_id}: 麵篩{basket.number}開始煮麵 "
                f"({unit.cook_ticks} ticks)"
            )
            return

        if action.kind == "nashi_shake":
            basket = self.basket(action.basket_no)
            if basket.state != BASKET_SHAKING or basket.unit_id != unit.unit_id:
                raise LogicViolation("Nachi甩麵完成時麵篩資料不一致")
            basket.state = BASKET_STANDBY
            self.log(f"Unit {unit.unit_id}: 麵篩{basket.number}甩麵完成並Standby")
            return

        if action.kind == "nashi_drop":
            basket = self.basket(action.basket_no)
            if unit.bowl_state != BOWL_AT_STATION20:
                raise LogicViolation("倒麵完成時碗不在 X0.2")
            if basket.state != BASKET_DROPPING or basket.unit_id != unit.unit_id:
                raise LogicViolation("倒麵完成時 UnitID 與麵篩配對錯誤")
            unit.noodle_drop_done = True
            basket.clear()
            self.log(f"Unit {unit.unit_id}: 倒麵完成，麵篩{action.basket_no}釋放")
            return

        if action.kind == "vision103":
            unit.vision_done = True
            self.log(f"Unit {unit.unit_id}: UR1 CMD103完成，收到203")
            return

        if action.kind == "ur1_101":
            if not unit.vision_done or not unit.noodle_drop_done:
                raise LogicViolation("UR1 CMD101完成，但103或倒麵尚未完成")
            unit.ur1_done = True
            unit.bowl_state = BOWL_TO_STATION30
            unit.travel_remaining = self.TRAVEL_TO_30_TICKS
            self.log(f"Unit {unit.unit_id}: UR1 CMD101完成，收到201，前往X0.3")
            return

        if action.kind == "ur2_102":
            if not unit.ur1_done or unit.bowl_state != BOWL_AT_STATION30:
                raise LogicViolation("UR2 CMD102完成，但UR1或站位條件不成立")
            unit.ur2_done = True
            unit.bowl_state = BOWL_TO_STATION40
            unit.travel_remaining = self.TRAVEL_TO_40_TICKS
            self.log(f"Unit {unit.unit_id}: UR2 CMD102完成，收到202，前往X0.4")
            return

        if action.kind == "soup":
            if not unit.ur2_done or unit.bowl_state != BOWL_AT_STATION40:
                raise LogicViolation("注湯完成，但UR2或站位條件不成立")
            unit.soup_done = True
            unit.bowl_state = BOWL_COMPLETE
            self.completed_ids.append(unit.unit_id)
            self.log(f"Unit {unit.unit_id}: 注湯完成，訂單完成")
            return

        raise LogicViolation(f"未知動作：{action.kind}")

    # ------------------------------------------------------------------
    # 煮麵與排程
    # ------------------------------------------------------------------
    def _advance_cooking(self) -> None:
        for basket in self.baskets:
            if basket.state != BASKET_COOKING:
                continue
            basket.cook_remaining -= 1
            if basket.cook_remaining <= 0:
                basket.state = BASKET_COOKED
                basket.cooked_tick = self.tick_no
                self.cooked_order.append(basket.unit_id)
                self.log(f"Unit {basket.unit_id}: 麵篩{basket.number}煮麵完成")

    def _assign_free_baskets(self) -> None:
        assigned_ids = {basket.unit_id for basket in self.baskets if basket.unit_id}
        waiting_units = [
            unit
            for unit in self.units
            if unit.basket_no == 0 and unit.unit_id not in assigned_ids
        ]
        for basket, unit in zip(
            [basket for basket in self.baskets if basket.state == BASKET_FREE],
            waiting_units,
        ):
            basket.state = BASKET_ASSIGNED
            basket.unit_id = unit.unit_id
            basket.cabinet_no = unit.cabinet_no
            basket.firmness_no = unit.firmness_no
            unit.basket_no = basket.number
            basket.state = BASKET_WAIT_LOAD
            self.log(
                f"Unit {unit.unit_id}: 指派麵篩{basket.number}，"
                f"麵櫃{unit.cabinet_no}"
            )

    def _nashi_safe(self) -> bool:
        return self.ur_action is None or self.ur_action.kind == "vision103"

    def _schedule_nachi(self) -> None:
        if self.nachi_action is not None or not self._nashi_safe():
            return

        # 動作優先順序：拿生麵 > 甩麵 > 倒麵。
        load_candidates = [
            basket for basket in self.baskets if basket.state == BASKET_WAIT_LOAD
        ]
        if load_candidates:
            basket = min(load_candidates, key=lambda item: self.unit(item.unit_id).fifo_index)
            basket.state = BASKET_LOADING
            self.nachi_action = Action(
                "nashi_load", basket.unit_id, self.NACHI_LOAD_TICKS, basket.number
            )
            self.log(f"Unit {basket.unit_id}: Nachi開始拿生麵至麵篩{basket.number}")
            return

        shake_candidates = [
            basket for basket in self.baskets if basket.state == BASKET_COOKED
        ]
        if shake_candidates:
            basket = min(
                shake_candidates,
                key=lambda item: (
                    item.cooked_tick if item.cooked_tick is not None else self.tick_no,
                    self.unit(item.unit_id).fifo_index,
                ),
            )
            basket.state = BASKET_SHAKING
            self.nachi_action = Action(
                "nashi_shake", basket.unit_id, self.NACHI_SHAKE_TICKS, basket.number
            )
            self.log(f"Unit {basket.unit_id}: Nachi開始取熟麵並甩麵")
            return

        station20_units = [
            unit
            for unit in self.units
            if unit.bowl_state == BOWL_AT_STATION20 and not unit.noodle_drop_done
        ]
        if not station20_units:
            return
        unit = min(station20_units, key=lambda item: item.fifo_index)
        basket = self.basket(unit.basket_no)
        if basket.state != BASKET_STANDBY or basket.unit_id != unit.unit_id:
            return
        if self.conveyor_running:
            return
        basket.state = BASKET_DROPPING
        self.nachi_action = Action(
            "nashi_drop", unit.unit_id, self.NACHI_DROP_TICKS, basket.number
        )
        self.log(f"Unit {unit.unit_id}: Nachi開始倒麵進碗")

    # ------------------------------------------------------------------
    # 落碗、輸送帶與四站流程
    # ------------------------------------------------------------------
    def _schedule_bowl_drop(self) -> None:
        if self.bowl_action is not None:
            return
        if any(
            unit.bowl_state in (BOWL_DROP_RUNNING, BOWL_TO_STATION20)
            for unit in self.units
        ):
            return

        candidates = [unit for unit in self.units if unit.bowl_state == BOWL_WAIT_DROP]
        if not candidates:
            return
        unit = min(candidates, key=lambda item: item.fifo_index)

        if self.drop_started_ids:
            previous = self.unit(self.drop_started_ids[-1])
            if previous.bowl_state < BOWL_AT_STATION20:
                raise LogicViolation(
                    f"Unit {unit.unit_id}提早落碗；前一碗{previous.unit_id}尚未到X0.2"
                )

        unit.bowl_state = BOWL_DROP_RUNNING
        self.drop_started_ids.append(unit.unit_id)
        self.bowl_action = Action("bowl_drop", unit.unit_id, self.DROP_TICKS)
        self.log(f"Unit {unit.unit_id}: 開始落碗")

    def _station_blocked(self) -> bool:
        if self.nachi_action and self.nachi_action.kind == "nashi_drop":
            return True
        if self.ur_action and self.ur_action.kind in ("ur1_101", "ur2_102"):
            return True
        if self.soup_action is not None:
            return True
        return any(
            unit.bowl_state in (
                BOWL_AT_STATION20,
                BOWL_AT_STATION30,
                BOWL_AT_STATION40,
            )
            for unit in self.units
        )

    def _decide_conveyor(self) -> None:
        has_travelling_bowl = any(
            unit.bowl_state
            in (BOWL_TO_STATION20, BOWL_TO_STATION30, BOWL_TO_STATION40)
            for unit in self.units
        )
        self.conveyor_running = has_travelling_bowl and not self._station_blocked()

    def _advance_conveyor(self) -> None:
        if not self.conveyor_running:
            return

        arrivals: list[Unit] = []
        for unit in self.units:
            if unit.bowl_state not in (
                BOWL_TO_STATION20,
                BOWL_TO_STATION30,
                BOWL_TO_STATION40,
            ):
                continue
            unit.travel_remaining -= 1
            if unit.travel_remaining <= 0:
                arrivals.append(unit)

        if not arrivals:
            return

        # 任一站到位後輸送帶立即停止；其餘碗保留目前途中位置。
        self.conveyor_running = False
        for unit in arrivals:
            if unit.bowl_state == BOWL_TO_STATION20:
                unit.bowl_state = BOWL_AT_STATION20
                self.log(f"Unit {unit.unit_id}: X0.2到位")
            elif unit.bowl_state == BOWL_TO_STATION30:
                unit.bowl_state = BOWL_AT_STATION30
                self.log(f"Unit {unit.unit_id}: X0.3到位")
            elif unit.bowl_state == BOWL_TO_STATION40:
                unit.bowl_state = BOWL_AT_STATION40
                self.log(f"Unit {unit.unit_id}: X0.4到位")

    # ------------------------------------------------------------------
    # UR1 / UR2 / 注湯
    # ------------------------------------------------------------------
    def _schedule_ur(self) -> None:
        if self.ur_action is not None:
            return

        station30 = [
            unit
            for unit in self.units
            if unit.bowl_state == BOWL_AT_STATION30 and not unit.ur2_done
        ]
        if station30:
            unit = min(station30, key=lambda item: item.fifo_index)
            if self.nachi_action is None:
                self.ur_action = Action("ur2_102", unit.unit_id, self.UR2_TICKS)
                self.log(f"Unit {unit.unit_id}: UR2開始CMD102")
            return

        station20_ready = [
            unit
            for unit in self.units
            if unit.bowl_state == BOWL_AT_STATION20
            and unit.noodle_drop_done
            and unit.vision_done
            and not unit.ur1_done
        ]
        if station20_ready:
            unit = min(station20_ready, key=lambda item: item.fifo_index)
            if self.nachi_action is None:
                self.ur_action = Action("ur1_101", unit.unit_id, self.UR1_TICKS)
                self.log(f"Unit {unit.unit_id}: UR1開始CMD101")
            return

        # 103可與輸送帶及Nachi拿麵/甩麵並行，但不可與UR2並行。
        # 鎖定最早尚未完成UR1的訂單；已拍照但未執行101時，不拍下一碗。
        pending_ur1 = [
            unit
            for unit in self.units
            if not unit.ur1_done and unit.bowl_state != BOWL_COMPLETE
        ]
        if not pending_ur1:
            return
        unit = min(pending_ur1, key=lambda item: item.fifo_index)
        if not unit.vision_done:
            self.ur_action = Action("vision103", unit.unit_id, self.UR_VISION_TICKS)
            self.log(f"Unit {unit.unit_id}: UR1開始CMD103預拍照")

    def _schedule_soup(self) -> None:
        if self.soup_action is not None:
            return
        candidates = [
            unit
            for unit in self.units
            if unit.bowl_state == BOWL_AT_STATION40 and not unit.soup_done
        ]
        if not candidates:
            return
        unit = min(candidates, key=lambda item: item.fifo_index)
        self.soup_action = Action("soup", unit.unit_id, self.SOUP_TICKS)
        self.log(f"Unit {unit.unit_id}: Y0.7開始注湯")

    # ------------------------------------------------------------------
    # 每個 Scan 的安全與資料一致性檢查
    # ------------------------------------------------------------------
    def _check_invariants(self) -> None:
        occupied_baskets = [basket for basket in self.baskets if basket.unit_id]
        basket_unit_ids = [basket.unit_id for basket in occupied_baskets]
        if len(basket_unit_ids) != len(set(basket_unit_ids)):
            raise LogicViolation("同一UnitID同時存在於兩個麵篩")
        if len(occupied_baskets) > 3:
            raise LogicViolation("使用中的麵篩超過3個")

        for basket in occupied_baskets:
            unit = self.unit(basket.unit_id)
            if unit.basket_no != basket.number:
                raise LogicViolation(
                    f"Unit {unit.unit_id}記錄麵篩{unit.basket_no}，"
                    f"但實際資料位於麵篩{basket.number}"
                )

        for station_state, station_name in (
            (BOWL_AT_STATION20, "X0.2"),
            (BOWL_AT_STATION30, "X0.3"),
            (BOWL_AT_STATION40, "X0.4"),
        ):
            at_station = [
                unit.unit_id for unit in self.units if unit.bowl_state == station_state
            ]
            if len(at_station) > 1:
                raise LogicViolation(f"{station_name}同時出現多碗：{at_station}")

        if self.ur_action and self.ur_action.kind in ("ur1_101", "ur2_102"):
            if self.nachi_action is not None:
                raise LogicViolation(
                    f"碰撞區衝突：{self.ur_action.kind} 與 {self.nachi_action.kind} 同時執行"
                )

        if self.conveyor_running:
            if self.ur_action and self.ur_action.kind in ("ur1_101", "ur2_102"):
                raise LogicViolation("輸送帶運轉時UR1/UR2正在站內動作")
            if self.nachi_action and self.nachi_action.kind == "nashi_drop":
                raise LogicViolation("輸送帶運轉時Nachi正在倒麵")

        completed_prefix = [unit.unit_id for unit in self.units[: len(self.completed_ids)]]
        if self.completed_ids != completed_prefix:
            raise LogicViolation(
                f"完成回覆順序錯誤：expected prefix={completed_prefix}, "
                f"actual={self.completed_ids}"
            )


def make_units(cook_ticks: Iterable[int], start_id: int = 1001) -> list[Unit]:
    units = []
    for index, ticks in enumerate(cook_ticks):
        units.append(
            Unit(
                unit_id=start_id + index,
                cabinet_no=(index % 10) + 1,
                firmness_no=(index % 3) + 1,
                cook_ticks=int(ticks),
                fifo_index=index,
            )
        )
    return units


def run_case(name: str, cook_ticks: Iterable[int], trace: bool = False) -> SimulationResult:
    simulation = RamenPLCSimulation(name, make_units(cook_ticks))
    result = simulation.run()
    print(
        f"[PASS] {name}: orders={len(result.order_ids)}, ticks={result.ticks}, "
        f"completed={result.completed_ids}"
    )
    if trace:
        for line in result.event_log:
            print(f"  {line}")
    return result


def run_suite(random_tests: int, trace: bool) -> None:
    run_case("單碗完整流程", [5], trace=trace)

    mixed = run_case("三麵篩不同熟成時間", [11, 2, 5], trace=trace)
    if mixed.cooked_order[:2] != [1002, 1003]:
        raise LogicViolation(
            "不同熟成時間測試未形成預期的非FIFO煮熟順序："
            f"{mixed.cooked_order}"
        )
    print(f"[PASS] 非FIFO煮熟順序可處理：{mixed.cooked_order}")

    run_case("十筆訂單與三麵篩循環使用", [8, 3, 6, 2, 10, 4, 7, 3, 9, 5])

    rng = random.Random(20260819)
    for case_index in range(1, random_tests + 1):
        order_count = rng.randint(1, 20)
        cook_times = [rng.randint(1, 14) for _ in range(order_count)]
        simulation = RamenPLCSimulation(
            f"隨機壓力測試{case_index}", make_units(cook_times, start_id=2000)
        )
        simulation.run()
    print(f"[PASS] 隨機壓力測試：{random_tests}組")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MVP拉麵機PLC全自動流程本機模型測試")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="顯示單碗與三碗案例的逐步事件紀錄",
    )
    parser.add_argument(
        "--random-tests",
        type=int,
        default=50,
        help="隨機壓力測試組數（預設50）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.random_tests < 0:
        print("--random-tests不可小於0", file=sys.stderr)
        return 2
    try:
        run_suite(args.random_tests, args.trace)
    except LogicViolation as exc:
        print(f"[FAIL] PLC流程模型檢查失敗：{exc}", file=sys.stderr)
        return 1
    print("\nRESULT: PASS - 目前參考模型未發現流程死鎖、UnitID錯配或碰撞條件違反。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
