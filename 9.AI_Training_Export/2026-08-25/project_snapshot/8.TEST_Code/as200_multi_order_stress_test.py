"""AS200 Simulator 多訂單FIFO與完整製程壓力測試。"""

from __future__ import annotations

import argparse
import time

from as200_full_auto_flow_test import (
    BIT_DEBUG_BUSY,
    BIT_DEBUG_GRANT,
    BIT_DEBUG_REQUEST,
    BIT_DEBUG_Y00,
    BIT_SIM_MODE,
    BIT_SIM_X01,
    BIT_SIM_X02,
    BIT_SIM_X03,
    BIT_SIM_X04,
    D_NACHI_COMMAND_WORD,
    D_NACHI_STATUS_WORD,
    D_ORDER_COMPLETE_INDEX,
    D_ORDER_COMPLETE_UNIT_ID,
    FullAutoFlowTest,
)
from as200_order_integration_test import (
    D_BOWL_DEBUG,
    D_EMC_STATUS,
    D_HMI_COMM_STATUS,
    D_MACHINE_MODE,
    D_ORDER_FIFO_COUNT,
    D_ORDER_VALID,
    D_PLC_IPC_EMC,
    D_SIMULATION,
    join_dint,
)


D_HEAD_BOWL_STATE = 8012
D_HEAD_UNIT_ID = 8015
D_UR1_DONE_UNIT_ID = 8026
D_UR2_DONE_UNIT_ID = 8028


class MultiOrderStressTest(FullAutoFlowTest):
    def read_complete_index(self) -> int:
        words = self.read_d(D_ORDER_COMPLETE_INDEX, 2)
        return words[0] | (words[1] << 16)

    def read_dint(self, address: int) -> int:
        return join_dint(self.read_d(address, 2))

    def clear_station_inputs(self) -> None:
        for bit_no in (BIT_SIM_X01, BIT_SIM_X02, BIT_SIM_X03, BIT_SIM_X04):
            self.set_sim_bit(bit_no, False)

    def wait_bowl_drop(self, seconds: float = 15.0) -> bool:
        return self.wait_debug_bit(BIT_DEBUG_Y00, True, seconds)

    def finish_bowl_drop(self) -> bool:
        self.set_sim_bit(BIT_SIM_X01, True)
        done = self.wait_debug_bit(BIT_DEBUG_BUSY, False, 4.0)
        self.set_sim_bit(BIT_SIM_X01, False)
        grants_clear = self.wait_for(
            lambda: not bool(
                self.read_d(D_BOWL_DEBUG)[0]
                & ((1 << BIT_DEBUG_REQUEST) | (1 << BIT_DEBUG_GRANT))
            ),
            4.0,
        )
        return done and grants_clear

    def run_stress(self, order_count: int) -> int:
        if not 1 <= order_count <= 32:
            print("[FAIL] --orders must be between 1 and 32")
            return 2
        if not self.raw.connect() or not self.hmi.connect():
            print("[FAIL] Cannot connect AS200 Simulator")
            return 2

        original_simulation_word = 0
        seen_ipc_commands: list[int] = []
        seen_nachi_actions: list[int] = []
        completed_ids: list[int] = []
        self.start_peripheral()
        try:
            original_simulation_word = self.read_d(D_SIMULATION)[0]
            self.last_accepted_ipc_response_seq = self.read_d(1303, 2)[1]
            self.write_d(D_SIMULATION, original_simulation_word | (1 << BIT_SIM_MODE))
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

            base = 28000000 + ((int(time.time()) % 900000) * 10)
            unit_ids = [base + index + 1 for index in range(order_count)]
            start_complete_index = self.read_complete_index()

            for unit_id in unit_ids:
                if not self.submit_order(unit_id):
                    return 1

            queued = self.read_d(D_ORDER_FIFO_COUNT)[0] == order_count
            print(
                f"[{'PASS' if queued else 'FAIL'}] FIFO queued: "
                f"Count={self.read_d(D_ORDER_FIFO_COUNT)[0]}, IDs={unit_ids}"
            )
            if not queued or not self.send_command(32, 302):
                return 1

            for position, expected_unit_id in enumerate(unit_ids, start=1):
                label = f"Order {position}/{order_count} UnitID={expected_unit_id}"

                if not self.wait_bowl_drop():
                    print(f"[BLOCKED] {label}: bowl drop did not start")
                    return 1
                if not self.finish_bowl_drop():
                    print(f"[BLOCKED] {label}: X0.1 bowl drop did not finish")
                    return 1

                self.tick_for(0.2)
                self.set_sim_bit(BIT_SIM_X02, True)

                station20_done = self.wait_for(
                    lambda: (
                        self.read_d(D_HEAD_BOWL_STATE)[0] == 25
                        and self.read_dint(D_HEAD_UNIT_ID) == expected_unit_id
                        and self.read_dint(D_UR1_DONE_UNIT_ID) == expected_unit_id
                    ),
                    60.0,
                )
                if not station20_done:
                    print(
                        f"[BLOCKED] {label}: X0.2 station, "
                        f"BowlState={self.read_d(D_HEAD_BOWL_STATE)[0]}, "
                        f"HeadUnitID={self.read_dint(D_HEAD_UNIT_ID)}, "
                        f"UR1DoneUnitID={self.read_dint(D_UR1_DONE_UNIT_ID)}"
                    )
                    return 1

                self.set_sim_bit(BIT_SIM_X02, False)
                self.tick_for(0.2)
                self.set_sim_bit(BIT_SIM_X03, True)
                station30_done = self.wait_for(
                    lambda: (
                        self.read_d(D_HEAD_BOWL_STATE)[0] == 35
                        and self.read_dint(D_HEAD_UNIT_ID) == expected_unit_id
                        and self.read_dint(D_UR2_DONE_UNIT_ID) == expected_unit_id
                    ),
                    30.0,
                )
                if not station30_done:
                    print(
                        f"[BLOCKED] {label}: X0.3 station, "
                        f"BowlState={self.read_d(D_HEAD_BOWL_STATE)[0]}, "
                        f"HeadUnitID={self.read_dint(D_HEAD_UNIT_ID)}, "
                        f"UR2DoneUnitID={self.read_dint(D_UR2_DONE_UNIT_ID)}"
                    )
                    return 1

                self.set_sim_bit(BIT_SIM_X03, False)
                self.tick_for(0.2)
                before_index = self.read_complete_index()
                self.set_sim_bit(BIT_SIM_X04, True)

                completed = self.wait_for(
                    lambda: self.read_complete_index() != before_index,
                    20.0,
                )
                completed_unit_id = join_dint(
                    self.read_d(D_ORDER_COMPLETE_UNIT_ID, 2)
                )
                completed_index = self.read_complete_index()
                expected_fifo_count = order_count - position
                fifo_ok = self.wait_for(
                    lambda: self.read_d(D_ORDER_FIFO_COUNT)[0]
                    == expected_fifo_count,
                    3.0,
                )
                self.set_sim_bit(BIT_SIM_X04, False)
                self.tick_for(0.2)

                order_ok = (
                    completed
                    and completed_unit_id == expected_unit_id
                    and completed_index != before_index
                    and fifo_ok
                )
                print(
                    f"[{'PASS' if order_ok else 'FAIL'}] {label}: "
                    f"CompletedUnitID={completed_unit_id}, "
                    f"CompleteIndex={before_index}->{completed_index}, "
                    f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}"
                )
                if not order_ok:
                    return 1
                completed_ids.append(completed_unit_id)

            final_index = self.read_complete_index()
            index_delta = (final_index - start_complete_index) & 0xFFFFFFFF
            final_ok = (
                completed_ids == unit_ids
                and self.read_d(D_ORDER_FIFO_COUNT)[0] == 0
                and index_delta == order_count
                and self.read_d(D_MACHINE_MODE)[0] == 2
            )
            print(
                f"[{'PASS' if final_ok else 'FAIL'}] STRESS SUMMARY: "
                f"Orders={order_count}, Completed={completed_ids}, "
                f"IndexDelta={index_delta}, FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}"
            )
            return 0 if final_ok else 1
        finally:
            self.write_d(D_ORDER_VALID, 0)
            self.write_d(D_SIMULATION, original_simulation_word)
            self.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AS200 multi-order stress test")
    parser.add_argument("--orders", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(MultiOrderStressTest().run_stress(args.orders))
