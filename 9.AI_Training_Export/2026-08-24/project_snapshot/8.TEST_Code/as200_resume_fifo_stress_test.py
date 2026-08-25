"""Resume and finish orders left in the AS200 FIFO after a diagnostic stop."""

from __future__ import annotations

from as200_multi_order_stress_test import (
    BIT_SIM_MODE,
    BIT_SIM_X02,
    BIT_SIM_X03,
    BIT_SIM_X04,
    D_HEAD_BOWL_STATE,
    D_HEAD_UNIT_ID,
    D_ORDER_COMPLETE_INDEX,
    D_ORDER_COMPLETE_UNIT_ID,
    D_ORDER_FIFO_COUNT,
    D_ORDER_VALID,
    D_SIMULATION,
    D_UR1_DONE_UNIT_ID,
    D_UR2_DONE_UNIT_ID,
    MultiOrderStressTest,
)
from as200_order_integration_test import join_dint


def main() -> int:
    test = MultiOrderStressTest()
    if not test.raw.connect() or not test.hmi.connect():
        print("[FAIL] Cannot connect AS200 Simulator")
        return 2

    original_simulation = 0
    test.start_peripheral()
    try:
        original_simulation = test.read_d(D_SIMULATION)[0]
        test.write_d(D_SIMULATION, original_simulation | (1 << BIT_SIM_MODE))
        test.clear_station_inputs()
        # PLC可能保留断电／前次测试时的StationXXLast=TRUE。
        # 清除模拟输入后必须让PLC实际扫描到OFF，下一次ON才会形成上升沿。
        test.tick_for(0.5)

        initial_count = test.read_d(D_ORDER_FIFO_COUNT)[0]
        if initial_count == 0:
            print("[PASS] FIFO already empty")
            return 0

        completed: list[int] = []
        print(f"[INFO] Resuming FIFO Count={initial_count}")

        while test.read_d(D_ORDER_FIFO_COUNT)[0] > 0:
            expected_unit_id = test.read_dint(D_HEAD_UNIT_ID)
            state = test.read_d(D_HEAD_BOWL_STATE)[0]
            before_count = test.read_d(D_ORDER_FIFO_COUNT)[0]
            label = f"UnitID={expected_unit_id} State={state}"

            if state in (0, 10):
                if not test.wait_bowl_drop() or not test.finish_bowl_drop():
                    print(f"[BLOCKED] {label}: bowl drop")
                    return 1
                state = test.read_d(D_HEAD_BOWL_STATE)[0]

            if state in (15, 20):
                test.set_sim_bit(BIT_SIM_X02, True)
                station20_done = test.wait_for(
                    lambda: (
                        test.read_d(D_HEAD_BOWL_STATE)[0] == 25
                        and test.read_dint(D_UR1_DONE_UNIT_ID) == expected_unit_id
                    ),
                    60.0,
                )
                test.set_sim_bit(BIT_SIM_X02, False)
                if not station20_done:
                    print(f"[BLOCKED] {label}: X0.2")
                    return 1
                state = 25

            if state in (25, 30):
                test.set_sim_bit(BIT_SIM_X03, True)
                station30_done = test.wait_for(
                    lambda: (
                        test.read_d(D_HEAD_BOWL_STATE)[0] == 35
                        and test.read_dint(D_UR2_DONE_UNIT_ID) == expected_unit_id
                    ),
                    30.0,
                )
                test.set_sim_bit(BIT_SIM_X03, False)
                if not station30_done:
                    print(f"[BLOCKED] {label}: X0.3")
                    return 1
                state = 35

            before_index = test.read_complete_index()
            if state == 35:
                test.set_sim_bit(BIT_SIM_X04, True)
            completed_ok = test.wait_for(
                lambda: test.read_complete_index() != before_index,
                20.0,
            )
            completed_unit_id = join_dint(
                test.read_d(D_ORDER_COMPLETE_UNIT_ID, 2)
            )
            test.set_sim_bit(BIT_SIM_X04, False)
            count_ok = test.wait_for(
                lambda: test.read_d(D_ORDER_FIFO_COUNT)[0] == before_count - 1,
                3.0,
            )
            if not completed_ok or not count_ok or completed_unit_id != expected_unit_id:
                print(
                    f"[BLOCKED] {label}: complete, "
                    f"CompletedUnitID={completed_unit_id}, "
                    f"FIFO={test.read_d(D_ORDER_FIFO_COUNT)[0]}"
                )
                return 1
            completed.append(completed_unit_id)
            print(
                f"[PASS] Resumed UnitID={completed_unit_id}, "
                f"FIFO={before_count}->{before_count - 1}"
            )

        print(f"[PASS] RESUME SUMMARY: Completed={completed}, FIFO=0")
        return 0
    finally:
        test.write_d(D_ORDER_VALID, 0)
        test.write_d(D_SIMULATION, original_simulation)
        test.stop()


if __name__ == "__main__":
    raise SystemExit(main())
