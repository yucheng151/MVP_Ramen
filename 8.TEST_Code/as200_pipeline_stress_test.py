"""AS200 Simulator 多碗、多站同時存在的流水線壓力測試。"""

from __future__ import annotations

import argparse
import time

from as200_full_auto_flow_test import (
    BIT_SIM_MODE,
    BIT_SIM_X01,
    BIT_SIM_X02,
    BIT_SIM_X03,
    BIT_SIM_X04,
    D_BASKET1_STATE,
    D_BASKET2_STATE,
    D_BASKET3_STATE,
    D_NACHI_COMMAND_WORD,
    D_NACHI_STATUS_WORD,
    D_ORDER_COMPLETE_INDEX,
    D_ORDER_COMPLETE_UNIT_ID,
)
from as200_multi_order_stress_test import MultiOrderStressTest
from as200_order_integration_test import (
    D_EMC_STATUS,
    D_HMI_COMM_STATUS,
    D_MACHINE_MODE,
    D_ORDER_FIFO_COUNT,
    D_ORDER_VALID,
    D_PLC_IPC_EMC,
    D_SIMULATION,
    join_dint,
)


D_RIGHTMOST_STATION = 8006


class PipelineStressTest(MultiOrderStressTest):
    def pulse_conveyor_stations(self) -> None:
        """一次輸送帶移動，同時模擬碗抵達X0.2、X0.3、X0.4。"""
        word = self.read_d(D_SIMULATION)[0] | (1 << BIT_SIM_MODE)
        word &= ~(1 << BIT_SIM_X01)
        word |= (
            (1 << BIT_SIM_X02)
            | (1 << BIT_SIM_X03)
            | (1 << BIT_SIM_X04)
        )
        self.write_d(D_SIMULATION, word)
        self.tick_for(0.30)
        word &= ~(
            (1 << BIT_SIM_X02)
            | (1 << BIT_SIM_X03)
            | (1 << BIT_SIM_X04)
        )
        self.write_d(D_SIMULATION, word)
        self.tick_for(0.20)

    def wait_all_workstations_done(self, seconds: float = 120.0) -> bool:
        """20/30/40站皆完成後即可再次推進輸送帶。

        RightmostStation=10可能只是下一碗已建立落碗任務；此時前一碗
        已在State 15，可以先送往X0.2，所以不可把10視為工作站阻塞。
        """
        return self.wait_for(
            lambda: self.read_d(D_RIGHTMOST_STATION)[0] < 20,
            seconds,
        )

    def run_pipeline(self, order_count: int) -> int:
        if not 3 <= order_count <= 16:
            print("[FAIL] --orders must be between 3 and 16")
            return 2
        if not self.raw.connect() or not self.hmi.connect():
            print("[FAIL] Cannot connect AS200 Simulator")
            return 2

        original_simulation_word = 0
        self.start_peripheral()
        try:
            original_simulation_word = self.read_d(D_SIMULATION)[0]
            if self.read_d(D_ORDER_FIFO_COUNT)[0] != 0:
                print(
                    "[BLOCKED] FIFO must be empty before pipeline test: "
                    f"Count={self.read_d(D_ORDER_FIFO_COUNT)[0]}"
                )
                return 1

            self.last_accepted_ipc_response_seq = self.read_d(1303, 2)[1]
            self.write_d(D_SIMULATION, (1 << BIT_SIM_MODE))
            self.clear_station_inputs()

            initialized = self.wait_for(
                lambda: (
                    self.read_d(D_NACHI_STATUS_WORD)[0] & 0x1204
                ) == 0x1204,
                15.0,
            )
            print(
                f"[{'PASS' if initialized else 'FAIL'}] Nachi initialized: "
                f"D12150=0x{self.read_d(D_NACHI_COMMAND_WORD)[0]:04X}, "
                f"D12100=0x{self.read_d(D_NACHI_STATUS_WORD)[0]:04X}"
            )
            if not initialized:
                return 1

            self.tick_for(0.5)
            online = self.read_d(D_HMI_COMM_STATUS)[0] == 1
            print(f"[{'PASS' if online else 'FAIL'}] HMI online")
            if not online or not self.send_command(6, 201):
                return 1

            safe = self.wait_for(
                lambda: self.read_d(D_EMC_STATUS)[0] == 0
                and self.read_d(D_PLC_IPC_EMC)[0] == 0,
                3.0,
            )
            print(f"[{'PASS' if safe else 'FAIL'}] EMC safe")
            if not safe or not self.send_command(30, 300):
                return 1

            base = 29000000 + ((int(time.time()) % 900000) * 10)
            unit_ids = [base + index + 1 for index in range(order_count)]
            start_complete_index = self.read_complete_index()
            for unit_id in unit_ids:
                if not self.submit_order(unit_id):
                    return 1
            if not self.send_command(32, 302):
                return 1

            dropped_ids: list[int] = []
            completed_ids: list[int] = []
            # 0=已落碗在X0.1~X0.2途中；1=X0.2完成；
            # 2=X0.3完成；3=X0.4完成並出料。
            conveyor_stage: dict[int, int] = {}

            if not self.wait_bowl_drop() or not self.finish_bowl_drop():
                print("[BLOCKED] First bowl drop")
                return 1
            first_id = unit_ids[0]
            dropped_ids.append(first_id)
            conveyor_stage[first_id] = 0
            print(f"[PASS] Pipeline entry: UnitID={first_id}")

            cycle = 0
            while len(completed_ids) < order_count:
                cycle += 1
                if cycle > order_count + 4:
                    print("[FAIL] Pipeline exceeded expected conveyor cycles")
                    return 1

                if not self.wait_all_workstations_done():
                    print(
                        f"[BLOCKED] Cycle {cycle}: stations did not finish, "
                        f"Rightmost={self.read_d(D_RIGHTMOST_STATION)[0]}"
                    )
                    return 1

                before_index = self.read_complete_index()
                expected_complete = next(
                    (
                        unit_id
                        for unit_id in dropped_ids
                        if conveyor_stage[unit_id] == 2
                    ),
                    None,
                )

                active_before = [
                    (unit_id, conveyor_stage[unit_id])
                    for unit_id in dropped_ids
                    if conveyor_stage[unit_id] < 3
                ]
                self.pulse_conveyor_stations()
                for unit_id, stage in active_before:
                    conveyor_stage[unit_id] = stage + 1

                if expected_complete is not None:
                    completed = self.wait_for(
                        lambda: self.read_complete_index() != before_index,
                        30.0,
                    )
                    completed_unit_id = join_dint(
                        self.read_d(D_ORDER_COMPLETE_UNIT_ID, 2)
                    )
                    if not completed or completed_unit_id != expected_complete:
                        print(
                            f"[FAIL] Cycle {cycle}: expected completion "
                            f"{expected_complete}, got {completed_unit_id}"
                        )
                        return 1
                    completed_ids.append(completed_unit_id)
                    print(
                        f"[PASS] Pipeline complete {len(completed_ids)}/"
                        f"{order_count}: UnitID={completed_unit_id}, "
                        f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}"
                    )

                if len(dropped_ids) < order_count:
                    next_id = unit_ids[len(dropped_ids)]
                    if not self.wait_bowl_drop(90.0):
                        print(
                            f"[BLOCKED] Cycle {cycle}: next bowl did not start, "
                            f"UnitID={next_id}, "
                            f"Rightmost={self.read_d(D_RIGHTMOST_STATION)[0]}"
                        )
                        return 1
                    if not self.finish_bowl_drop():
                        print(
                            f"[BLOCKED] Cycle {cycle}: next bowl did not finish, "
                            f"UnitID={next_id}"
                        )
                        return 1
                    dropped_ids.append(next_id)
                    conveyor_stage[next_id] = 0
                    print(
                        f"[PASS] Pipeline refill: UnitID={next_id}, "
                        f"InFlight={len(dropped_ids) - len(completed_ids)}"
                    )

            final_index = self.read_complete_index()
            basket_states = self.read_d(D_BASKET1_STATE, 3)
            final_ok = (
                completed_ids == unit_ids
                and self.read_d(D_ORDER_FIFO_COUNT)[0] == 0
                and ((final_index - start_complete_index) & 0xFFFFFFFF)
                == order_count
                and basket_states == [0, 0, 0]
                and self.read_d(D_MACHINE_MODE)[0] == 2
            )
            print(
                f"[{'PASS' if final_ok else 'FAIL'}] PIPELINE SUMMARY: "
                f"Orders={order_count}, Completed={completed_ids}, "
                f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}, "
                f"BasketStates={basket_states}, "
                f"IndexDelta={(final_index - start_complete_index) & 0xFFFFFFFF}"
            )
            return 0 if final_ok else 1
        finally:
            self.write_d(D_ORDER_VALID, 0)
            self.write_d(D_SIMULATION, original_simulation_word)
            self.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AS200 pipeline stress test")
    parser.add_argument("--orders", type=int, default=6)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(PipelineStressTest().run_pipeline(args.orders))
