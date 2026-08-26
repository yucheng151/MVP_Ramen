"""AS200 Simulator 1000笔滚动FIFO＋多站流水线耐久压力测试。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from as200_full_auto_flow_test import (
    BIT_SIM_MODE,
    D_BASKET1_STATE,
    D_NACHI_COMMAND_WORD,
    D_NACHI_STATUS_WORD,
    D_ORDER_COMPLETE_INDEX,
    D_ORDER_COMPLETE_UNIT_ID,
)
from as200_order_integration_test import (
    D_EMC_STATUS,
    D_HMI_COMM_STATUS,
    D_MACHINE_MODE,
    D_ORDER_ACK_INDEX,
    D_ORDER_ACK_UNIT_ID,
    D_ORDER_CABINET,
    D_ORDER_FIFO_COUNT,
    D_ORDER_FIRMNESS,
    D_ORDER_INDEX,
    D_ORDER_RESPONSE,
    D_ORDER_UNIT_ID,
    D_ORDER_VALID,
    D_PLC_IPC_EMC,
    D_SIMULATION,
    join_dint,
    split_dint,
)
from as200_pipeline_stress_test import PipelineStressTest


# 背景执行时Windows预设可能是CP950；日志讯息统一使用UTF-8，
# 避免非Big5字元让耐久测试本身被输出编码中断。
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if sys.stderr is not None:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


class EnduranceLogger:
    def __init__(self, log_dir: Path, total: int) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"pipeline_{total}_{stamp}.log"
        self.csv_path = log_dir / f"pipeline_{total}_{stamp}.csv"
        self.summary_path = log_dir / f"pipeline_{total}_{stamp}_summary.json"
        self._log_file = self.log_path.open("a", encoding="utf-8", buffering=1)
        self._csv_file = self.csv_path.open(
            "w", encoding="utf-8-sig", newline="", buffering=1
        )
        self.csv = csv.DictWriter(
            self._csv_file,
            fieldnames=[
                "sequence",
                "unit_id",
                "submitted_at",
                "dropped_at",
                "completed_at",
                "latency_seconds",
                "fifo_after",
                "complete_index",
                "basket_1_state",
                "basket_2_state",
                "basket_3_state",
                "result",
            ],
        )
        self.csv.writeheader()

    def event(self, message: str, console: bool = False) -> None:
        line = f"[{datetime.now().isoformat(timespec='milliseconds')}] {message}"
        self._log_file.write(line + "\n")
        self._log_file.flush()
        if console:
            print(line, flush=True)

    def order(self, row: dict[str, object]) -> None:
        self.csv.writerow(row)
        self._csv_file.flush()

    def summary(self, data: dict[str, object]) -> None:
        self.summary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def close(self) -> None:
        self._csv_file.close()
        self._log_file.close()


class ThousandOrderEnduranceTest(PipelineStressTest):
    def submit_order_quiet(
        self,
        unit_id: int,
        cabinet_no: int = 1,
        firmness_no: int = 2,
    ) -> tuple[bool, int]:
        before_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
        old_input_index = self.read_d(D_ORDER_INDEX)[0]
        old_ack_index = self.read_d(D_ORDER_ACK_INDEX)[0]
        order_index = (max(old_input_index, old_ack_index) + 1) & 0xFFFF or 1

        self.write_d(D_ORDER_VALID, 0)
        self.write_block(
            D_ORDER_UNIT_ID,
            split_dint(unit_id) + [cabinet_no, firmness_no, order_index],
        )
        self.write_d(D_ORDER_VALID, 1)
        acknowledged = self.wait_for(
            lambda: self.read_d(D_ORDER_ACK_INDEX)[0] == order_index,
            4.0,
        )
        ack_unit_id = join_dint(self.read_d(D_ORDER_ACK_UNIT_ID, 2))
        response = self.read_d(D_ORDER_RESPONSE)[0]
        after_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
        self.write_d(D_ORDER_VALID, 0)
        ok = (
            acknowledged
            and ack_unit_id == unit_id
            and response == 200
            and after_count == before_count + 1
        )
        return ok, response

    def run_endurance(
        self,
        total_orders: int,
        queue_window: int,
        log_dir: Path,
        live_state_path: Path | None = None,
        cabinet_no: int = 1,
        firmness_no: int = 2,
    ) -> int:
        recorder = EnduranceLogger(log_dir, total_orders)
        print(f"LOG_FILE={recorder.log_path}", flush=True)
        print(f"CSV_FILE={recorder.csv_path}", flush=True)
        print(f"SUMMARY_FILE={recorder.summary_path}", flush=True)

        result_code = 1
        failure = ""
        completed_ids: list[int] = []
        submitted_at: dict[int, float] = {}
        dropped_at: dict[int, float] = {}
        unit_ids: list[int] = []
        conveyor_stage: dict[int, int] = {}
        submitted_count = 0
        started_wall = datetime.now().isoformat(timespec="seconds")
        started_mono = time.monotonic()
        original_simulation_word = 0

        def publish_live(status: str, error: str = "") -> None:
            if live_state_path is None:
                return
            stage_names = {
                0: "落碗→放麵／UR1",
                1: "放麵／UR1→UR2",
                2: "UR2→注湯",
                3: "注湯／完成",
            }
            completed_set = set(completed_ids)
            rows = []
            for sequence, unit_id in enumerate(unit_ids, 1):
                if unit_id in completed_set:
                    location = "完成"
                elif unit_id in conveyor_stage:
                    location = stage_names.get(conveyor_stage[unit_id], "輸送中")
                elif sequence <= submitted_count:
                    location = "FIFO等待"
                else:
                    location = "尚未送出"
                rows.append({
                    "sequence": sequence,
                    "unit_id": unit_id,
                    "location": location,
                })
            fifo_count = 0
            try:
                if getattr(self.raw, "connected", False):
                    fifo_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
            except Exception:
                pass
            data = {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "error": error,
                "target": total_orders,
                "submitted": submitted_count,
                "completed": len(completed_ids),
                "fifo": fifo_count,
                "units": rows,
                "log_file": str(recorder.log_path),
                "csv_file": str(recorder.csv_path),
                "summary_file": str(recorder.summary_path),
            }
            live_state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = live_state_path.with_suffix(live_state_path.suffix + ".tmp")
            temp.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8",
            )
            temp.replace(live_state_path)

        publish_live("STARTING")

        if not 1 <= total_orders <= 100000:
            recorder.event("FAIL total_orders超出范围", True)
            recorder.close()
            return 2
        if not 3 <= queue_window <= 31:
            recorder.event("FAIL queue_window必须为3到31", True)
            recorder.close()
            return 2
        if not 1 <= cabinet_no <= 10 or firmness_no not in (1, 2, 3):
            recorder.event("FAIL 麵櫃或軟硬度設定無效", True)
            recorder.close()
            return 2
        if not self.raw.connect() or not self.hmi.connect():
            recorder.event("FAIL 无法连接AS200 Simulator", True)
            recorder.close()
            return 2

        self.start_peripheral()
        try:
            original_simulation_word = self.read_d(D_SIMULATION)[0]
            if self.read_d(D_ORDER_FIFO_COUNT)[0] != 0:
                failure = (
                    "测试开始前FIFO不为空："
                    f"{self.read_d(D_ORDER_FIFO_COUNT)[0]}"
                )
                raise RuntimeError(failure)

            self.last_accepted_ipc_response_seq = self.read_d(1303, 2)[1]
            self.write_d(
                D_SIMULATION,
                (original_simulation_word & ~0x001F) | (1 << BIT_SIM_MODE),
            )
            self.clear_station_inputs()

            initialized = self.wait_for(
                lambda: (
                    self.read_d(D_NACHI_STATUS_WORD)[0] & 0x1204
                ) == 0x1204,
                15.0,
            )
            if not initialized:
                raise RuntimeError("Nachi初始化未完成")
            recorder.event(
                "Nachi初始化完成 "
                f"D12150=0x{self.read_d(D_NACHI_COMMAND_WORD)[0]:04X} "
                f"D12100=0x{self.read_d(D_NACHI_STATUS_WORD)[0]:04X}",
                True,
            )

            self.tick_for(0.5)
            if self.read_d(D_HMI_COMM_STATUS)[0] != 1:
                raise RuntimeError("HMI未上线")
            if not self.send_command(6, 201):
                raise RuntimeError("CMD6失败")
            if not self.wait_for(
                lambda: self.read_d(D_EMC_STATUS)[0] == 0
                and self.read_d(D_PLC_IPC_EMC)[0] == 0,
                3.0,
            ):
                raise RuntimeError("EMC未解除")
            if not self.send_command(30, 300):
                raise RuntimeError("CMD30失败")

            base = 100000000 + ((int(time.time()) % 900000) * 1000)
            unit_ids = [base + index + 1 for index in range(total_orders)]
            order_sequence = {
                unit_id: index + 1 for index, unit_id in enumerate(unit_ids)
            }
            start_complete_index = self.read_complete_index()

            initial_submit = min(queue_window, total_orders)
            for _ in range(initial_submit):
                unit_id = unit_ids[submitted_count]
                ok, response = self.submit_order_quiet(
                    unit_id, cabinet_no, firmness_no,
                )
                if not ok:
                    raise RuntimeError(
                        f"初始送单失败 UnitID={unit_id} Response={response}"
                    )
                submitted_at[unit_id] = time.monotonic()
                submitted_count += 1
                publish_live("RUNNING")
            recorder.event(
                f"初始FIFO完成 Submitted={submitted_count} "
                f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}",
                True,
            )

            if not self.send_command(32, 302):
                raise RuntimeError("CMD32失败")

            dropped_ids: list[int] = []
            if not self.wait_bowl_drop(90.0) or not self.finish_bowl_drop():
                raise RuntimeError("第一碗落碗失败")
            first_id = unit_ids[0]
            dropped_ids.append(first_id)
            dropped_at[first_id] = time.monotonic()
            conveyor_stage[first_id] = 0
            publish_live("RUNNING")
            recorder.event(f"第一碗进入流水线 UnitID={first_id}", True)

            cycle = 0
            while len(completed_ids) < total_orders:
                cycle += 1
                if cycle > total_orders + 5:
                    raise RuntimeError("输送带循环次数超过预期")
                if not self.wait_all_workstations_done(180.0):
                    raise RuntimeError(
                        f"Cycle={cycle} 工作站逾时 "
                        f"Rightmost={self.read_d(8006)[0]}"
                    )

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
                publish_live("RUNNING")

                if expected_complete is not None:
                    if not self.wait_for(
                        lambda: self.read_complete_index() != before_index,
                        45.0,
                    ):
                        raise RuntimeError(
                            f"完成逾时 UnitID={expected_complete} Cycle={cycle}"
                        )
                    completed_unit_id = join_dint(
                        self.read_d(D_ORDER_COMPLETE_UNIT_ID, 2)
                    )
                    if completed_unit_id != expected_complete:
                        raise RuntimeError(
                            f"完成顺序错误 Expected={expected_complete} "
                            f"Actual={completed_unit_id}"
                        )
                    completed_ids.append(completed_unit_id)
                    publish_live("RUNNING")
                    now_mono = time.monotonic()
                    complete_index = self.read_complete_index()
                    fifo_after = self.read_d(D_ORDER_FIFO_COUNT)[0]
                    basket_states = self.read_d(D_BASKET1_STATE, 3)
                    sequence = order_sequence[completed_unit_id]
                    recorder.order(
                        {
                            "sequence": sequence,
                            "unit_id": completed_unit_id,
                            "submitted_at": f"{submitted_at[completed_unit_id]:.3f}",
                            "dropped_at": f"{dropped_at[completed_unit_id]:.3f}",
                            "completed_at": f"{now_mono:.3f}",
                            "latency_seconds": (
                                f"{now_mono - submitted_at[completed_unit_id]:.3f}"
                            ),
                            "fifo_after": fifo_after,
                            "complete_index": complete_index,
                            "basket_1_state": basket_states[0],
                            "basket_2_state": basket_states[1],
                            "basket_3_state": basket_states[2],
                            "result": "PASS",
                        }
                    )
                    recorder.event(
                        f"PASS {sequence}/{total_orders} "
                        f"UnitID={completed_unit_id} FIFO={fifo_after} "
                        f"Index={complete_index} "
                        f"Latency={now_mono - submitted_at[completed_unit_id]:.3f}s"
                    )

                    if submitted_count < total_orders:
                        next_submit_id = unit_ids[submitted_count]
                        ok, response = self.submit_order_quiet(
                            next_submit_id, cabinet_no, firmness_no,
                        )
                        if not ok:
                            raise RuntimeError(
                                f"滚动补单失败 UnitID={next_submit_id} "
                                f"Response={response}"
                            )
                        submitted_at[next_submit_id] = time.monotonic()
                        submitted_count += 1
                        publish_live("RUNNING")

                    if (
                        len(completed_ids) % 10 == 0
                        or len(completed_ids) == total_orders
                    ):
                        elapsed = time.monotonic() - started_mono
                        rate = len(completed_ids) / elapsed if elapsed > 0 else 0
                        remaining = total_orders - len(completed_ids)
                        eta_seconds = remaining / rate if rate > 0 else 0
                        recorder.event(
                            f"PROGRESS Completed={len(completed_ids)}/"
                            f"{total_orders} Submitted={submitted_count} "
                            f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]} "
                            f"Rate={rate:.4f}/s ETA={eta_seconds:.0f}s",
                            True,
                        )

                if len(dropped_ids) < submitted_count:
                    next_drop_id = unit_ids[len(dropped_ids)]
                    if not self.wait_bowl_drop(120.0):
                        raise RuntimeError(
                            f"等待落碗启动逾时 UnitID={next_drop_id}"
                        )
                    if not self.finish_bowl_drop():
                        raise RuntimeError(
                            f"落碗完成逾时 UnitID={next_drop_id}"
                        )
                    dropped_ids.append(next_drop_id)
                    dropped_at[next_drop_id] = time.monotonic()
                    conveyor_stage[next_drop_id] = 0
                    publish_live("RUNNING")

            final_index = self.read_complete_index()
            basket_states = self.read_d(D_BASKET1_STATE, 3)
            index_delta = (final_index - start_complete_index) & 0xFFFFFFFF
            final_ok = (
                completed_ids == unit_ids
                and self.read_d(D_ORDER_FIFO_COUNT)[0] == 0
                and index_delta == total_orders
                and basket_states == [0, 0, 0]
                and self.read_d(D_MACHINE_MODE)[0] == 2
            )
            result_code = 0 if final_ok else 1
            if not final_ok:
                failure = "最终状态检查失败"
            recorder.event(
                f"{'PASS' if final_ok else 'FAIL'} SUMMARY "
                f"Completed={len(completed_ids)}/{total_orders} "
                f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]} "
                f"IndexDelta={index_delta} BasketStates={basket_states}",
                True,
            )
            publish_live("PASS" if final_ok else "FAIL", failure)

        except Exception as exc:
            failure = str(exc)
            recorder.event(f"FAIL {failure}", True)
            publish_live("FAIL", failure)
            try:
                recorder.event(
                    "FAIL_STATE "
                    f"Completed={len(completed_ids)} "
                    f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]} "
                    f"Rightmost={self.read_d(8006)[0]} "
                    f"BasketStates={self.read_d(D_BASKET1_STATE, 3)} "
                    f"D12150=0x{self.read_d(D_NACHI_COMMAND_WORD)[0]:04X} "
                    f"D12100=0x{self.read_d(D_NACHI_STATUS_WORD)[0]:04X}",
                    True,
                )
            except Exception:
                pass
            result_code = 1
        finally:
            elapsed = time.monotonic() - started_mono
            summary = {
                "result": "PASS" if result_code == 0 else "FAIL",
                "failure": failure,
                "started_at": started_wall,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_seconds": round(elapsed, 3),
                "target_orders": total_orders,
                "submitted_orders": len(submitted_at),
                "completed_orders": len(completed_ids),
                "last_completed_unit_id": completed_ids[-1] if completed_ids else 0,
                "log_file": str(recorder.log_path),
                "csv_file": str(recorder.csv_path),
            }
            recorder.summary(summary)
            try:
                self.write_d(D_ORDER_VALID, 0)
                self.write_d(D_SIMULATION, original_simulation_word)
            finally:
                self.stop()
                recorder.close()

        return result_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AS200 1000-order endurance test")
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--queue-window", type=int, default=16)
    parser.add_argument("--live-state", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=10002)
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--cabinet", type=int, default=1)
    parser.add_argument("--firmness", type=int, default=2)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "logs",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(
        ThousandOrderEnduranceTest(
            host=args.host,
            port=args.port,
            device_id=args.device_id,
        ).run_endurance(
            total_orders=args.orders,
            queue_window=args.queue_window,
            log_dir=args.log_dir,
            live_state_path=args.live_state,
            cabinet_no=args.cabinet,
            firmness_no=args.firmness,
        )
    )
