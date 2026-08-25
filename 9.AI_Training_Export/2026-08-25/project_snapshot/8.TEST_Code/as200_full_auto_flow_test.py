"""AS200 Simulator 單碗全自動流程整合測試。

PLC 程式在 AS200 Simulator 內執行；本程式只負責模擬 HMI 訂單、
X0.1~X0.4 現場感測器、IPC/UR 與 Nachi 外部設備交握。
"""

from __future__ import annotations

import time

from as200_order_integration_test import (
    D_BOWL_DEBUG,
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
    OrderIntegrationTest,
    join_dint,
    split_dint,
)


D_PLC_IPC_REQUEST_CODE = 1201
D_PLC_IPC_REQUEST_SEQ = 1202
D_PLC_IPC_REQUEST_VALID = 1203
D_IPC_BUSY = 1302
D_IPC_RESPONSE_CODE = 1303
D_IPC_RESPONSE_SEQ = 1304

D_NACHI_COMMAND_WORD = 12150
D_NACHI_COMMAND_INDEX = 12151
D_NACHI_ACTION_NO = 12152
D_NACHI_STATUS_WORD = 12100
D_NACHI_DATA_FINISH = 12101
D_NOODLE_DEBUG_BITS = 8002
D_BASKET1_STATE = 8003
D_BASKET2_STATE = 8004
D_BASKET3_STATE = 8005
D_RIGHTMOST_STATION = 8006
D_CURRENT_COOK_JOB_STATE = 8007
D_NOODLE_ACTION_STEP = 8008
D_NOODLE_ACTION_DEBUG_BITS = 8009
D_AUTO_FLOW_DEBUG_BITS = 8010
D_ORDER_COMPLETE_UNIT_ID = 1135
D_ORDER_COMPLETE_INDEX = 1137

BIT_SIM_MODE = 0
BIT_SIM_X01 = 1
BIT_SIM_X02 = 2
BIT_SIM_X03 = 3
BIT_SIM_X04 = 4

BIT_DEBUG_REQUEST = 1
BIT_DEBUG_GRANT = 2
BIT_DEBUG_BUSY = 4
BIT_DEBUG_Y00 = 5


class FullAutoFlowTest(OrderIntegrationTest):
    def set_sim_bit(self, bit_no: int, enabled: bool) -> None:
        word = self.read_d(D_SIMULATION)[0] | (1 << BIT_SIM_MODE)
        if enabled:
            word |= 1 << bit_no
        else:
            word &= ~(1 << bit_no)
        self.write_d(D_SIMULATION, word)

    def wait_debug_bit(self, bit_no: int, enabled: bool, seconds: float) -> bool:
        mask = 1 << bit_no
        return self.wait_for(
            lambda: bool(self.read_d(D_BOWL_DEBUG)[0] & mask) is enabled,
            seconds,
        )

    def wait_for_ipc_response(
        self,
        expected: int,
        seconds: float,
        seen_ipc_commands: list[int],
        seen_nachi_actions: list[int],
    ) -> bool:
        expected_command = {201: 101, 202: 102, 203: 103}.get(expected)
        observed_request_seq = None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.heartbeat.tick()

            ipc = self.read_d(D_PLC_IPC_REQUEST_CODE, 4)
            if ipc[2] != 0:
                if ipc[0] not in seen_ipc_commands:
                    seen_ipc_commands.append(ipc[0])
                if ipc[0] == expected_command:
                    observed_request_seq = ipc[1]

            nachi = self.read_d(D_NACHI_COMMAND_WORD, 3)
            if (nachi[0] & (1 << 8)) and nachi[2] not in seen_nachi_actions:
                seen_nachi_actions.append(nachi[2])

            response = self.read_d(D_IPC_RESPONSE_CODE, 2)
            response_matches_observed_request = (
                observed_request_seq is not None
                and response[1] == observed_request_seq
            )
            response_matches_completed_request = (
                ipc[0] == expected_command
                and ipc[1] == response[1]
                and response[1] != self.last_accepted_ipc_response_seq
            )
            if response[0] == expected and (
                response_matches_observed_request
                or response_matches_completed_request
            ):
                self.last_accepted_ipc_response_seq = response[1]
                return True
            time.sleep(0.03)
        return False

    def wait_for_first_nachi_action(
        self,
        seconds: float,
        seen_nachi_actions: list[int],
    ) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.heartbeat.tick()
            nachi = self.read_d(D_NACHI_COMMAND_WORD, 3)
            if (nachi[0] & (1 << 8)) and nachi[2] not in seen_nachi_actions:
                seen_nachi_actions.append(nachi[2])
                return True
            time.sleep(0.02)
        return False

    def submit_order(self, unit_id: int) -> bool:
        before_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
        old_input_index = self.read_d(D_ORDER_INDEX)[0]
        old_ack_index = self.read_d(D_ORDER_ACK_INDEX)[0]
        order_index = (max(old_input_index, old_ack_index) + 1) & 0xFFFF or 1

        self.write_d(D_ORDER_VALID, 0)
        self.write_block(
            D_ORDER_UNIT_ID,
            split_dint(unit_id) + [1, 2, order_index],
        )
        self.write_d(D_ORDER_VALID, 1)

        acknowledged = self.wait_for(
            lambda: self.read_d(D_ORDER_ACK_INDEX)[0] == order_index,
            3.0,
        )
        ack_unit_id = join_dint(self.read_d(D_ORDER_ACK_UNIT_ID, 2))
        ack_index = self.read_d(D_ORDER_ACK_INDEX)[0]
        response = self.read_d(D_ORDER_RESPONSE)[0]
        after_count = self.read_d(D_ORDER_FIFO_COUNT)[0]
        self.write_d(D_ORDER_VALID, 0)

        ok = (
            acknowledged
            and ack_unit_id == unit_id
            and ack_index == order_index
            and response == 200
            and after_count == before_count + 1
        )
        print(
            f"[{'PASS' if ok else 'FAIL'}] Order: UnitID={unit_id}, "
            f"Response={response}, FIFO={before_count}->{after_count}"
        )
        return ok

    def run_full_flow(self) -> int:
        if not self.raw.connect() or not self.hmi.connect():
            print("[FAIL] Cannot connect AS200 Simulator")
            return 2

        original_simulation_word = 0
        seen_ipc_commands: list[int] = []
        seen_nachi_actions: list[int] = []
        self.start_peripheral()
        try:
            original_simulation_word = self.read_d(D_SIMULATION)[0]
            self.last_accepted_ipc_response_seq = self.read_d(
                D_IPC_RESPONSE_CODE, 2
            )[1]
            # 保留使用者已開啟的其他模擬輸入，只加上Simulation_Mode。
            self.write_d(
                D_SIMULATION,
                original_simulation_word | (1 << BIT_SIM_MODE),
            )

            # 初始化完成後D12150的啟動輸出可以全部OFF，因此以Robot
            # 回傳的Home、外部控制及遠端可用狀態判斷，不要求輸出位保留。
            nachi_initialized = self.wait_for(
                lambda: (
                    self.read_d(D_NACHI_STATUS_WORD)[0] & 0x1204
                ) == 0x1204
                and (
                    self.peripheral is None
                    or self.peripheral.nachi_startup_completed
                ),
                15.0,
            )
            print(
                f"[{'PASS' if nachi_initialized else 'FAIL'}] Nachi startup initialization: "
                f"D12150=0x{self.read_d(D_NACHI_COMMAND_WORD)[0]:04X}, "
                f"D12100=0x{self.read_d(D_NACHI_STATUS_WORD)[0]:04X}"
            )
            if not nachi_initialized:
                return 1

            # 確認初始化狀態穩定，不是切換中的單一PLC Scan。
            self.tick_for(1.0)
            nachi_initialized = (
                self.read_d(D_NACHI_STATUS_WORD)[0] & 0x1204
            ) == 0x1204
            if not nachi_initialized:
                print("[FAIL] Nachi initialization status was not stable")
                return 1

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

            unit_id = 27000000 + (int(time.time()) % 999999)
            before_complete_words = self.read_d(D_ORDER_COMPLETE_INDEX, 2)
            before_complete_index = (
                before_complete_words[0]
                | (before_complete_words[1] << 16)
            )
            if not self.submit_order(unit_id):
                return 1
            if not self.send_command(32, 302):
                return 1

            auto = self.read_d(D_MACHINE_MODE)[0] == 2
            started = self.wait_debug_bit(BIT_DEBUG_Y00, True, 8.0)
            print(
                f"[{'PASS' if auto and started else 'FAIL'}] Bowl drop start: "
                f"Mode={self.read_d(D_MACHINE_MODE)[0]}, D8001=0x{self.read_d(D_BOWL_DEBUG)[0]:04X}"
            )
            if not auto or not started:
                return 1

            # X0.1：碗落到輸送帶。
            self.set_sim_bit(BIT_SIM_X01, True)
            bowl_done = self.wait_debug_bit(BIT_DEBUG_BUSY, False, 3.0)
            self.set_sim_bit(BIT_SIM_X01, False)
            grants_clear = self.wait_for(
                lambda: not bool(
                    self.read_d(D_BOWL_DEBUG)[0]
                    & ((1 << BIT_DEBUG_REQUEST) | (1 << BIT_DEBUG_GRANT))
                ),
                3.0,
            )
            print(
                f"[{'PASS' if bowl_done and grants_clear else 'FAIL'}] X0.1 bowl arrived: "
                f"D8001=0x{self.read_d(D_BOWL_DEBUG)[0]:04X}"
            )
            if not bowl_done or not grants_clear:
                return 1

            # X0.2：放麵與UR1站。保持到UR1 CMD101完成。
            self.tick_for(0.5)
            self.set_sim_bit(BIT_SIM_X02, True)

            vision_done = self.wait_for_ipc_response(
                203, 15.0, seen_ipc_commands, seen_nachi_actions
            )
            print(
                f"[{'PASS' if vision_done else 'BLOCKED'}] UR1 CMD103/203: "
                f"IPC={seen_ipc_commands}, Nachi={seen_nachi_actions}"
            )
            if not vision_done:
                return 1

            first_nachi = bool(seen_nachi_actions) or self.wait_for_first_nachi_action(
                5.0, seen_nachi_actions
            )
            nachi_status = self.read_d(D_NACHI_STATUS_WORD)[0]
            nachi_command = self.read_d(D_NACHI_COMMAND_WORD, 3)
            noodle_debug = self.read_d(D_NOODLE_DEBUG_BITS)[0]
            noodle_states = self.read_d(D_BASKET1_STATE, 5)
            noodle_action_step = self.read_d(D_NOODLE_ACTION_STEP)[0]
            noodle_action_bits = self.read_d(D_NOODLE_ACTION_DEBUG_BITS)[0]
            print(
                f"[{'PASS' if first_nachi else 'BLOCKED'}] First Nachi command: "
                f"D12100=0x{nachi_status:04X}, "
                f"Home(D12100.2)={(nachi_status >> 2) & 1}, "
                f"D12150=0x{nachi_command[0]:04X}, "
                f"Index={nachi_command[1]}, Action={nachi_command[2]}, "
                f"Seen={seen_nachi_actions}"
            )
            print(
                "[DEBUG] Noodle scheduler: "
                f"D8002=0x{noodle_debug:04X}, "
                f"RobotIdle={(noodle_debug >> 0) & 1}, "
                f"LoadGrant={(noodle_debug >> 1) & 1}, "
                f"ActionBusy={(noodle_debug >> 2) & 1}, "
                f"ZoneLocked={(noodle_debug >> 3) & 1}, "
                f"ShakeGrant={(noodle_debug >> 4) & 1}, "
                f"DropGrant={(noodle_debug >> 5) & 1}, "
                f"Baskets={noodle_states[0:3]}, "
                f"Rightmost={noodle_states[3]}, "
                f"CookJobState={noodle_states[4]}"
            )
            print(
                "[DEBUG] AutoNoodle action: "
                f"ActionStep={noodle_action_step}, "
                f"ExchangeFinish={(noodle_action_bits >> 0) & 1}, "
                f"RobotActionFinish={(noodle_action_bits >> 1) & 1}, "
                f"D8009=0x{noodle_action_bits:04X}"
            )
            if self.peripheral is not None:
                print(
                    "[DEBUG] Nachi peripheral: "
                    f"DataRequests={self.peripheral.nachi_data_request_count}, "
                    f"ActionStarts={self.peripheral.nachi_action_start_count}, "
                    f"IntervalStarts={self.peripheral.nachi_interval_start_count}, "
                    f"LastD12150=0x{self.peripheral.last_nachi_command_word:04X}, "
                    f"StartPending={int(self.peripheral.nachi_start_pending)}"
                )
            if not first_nachi:
                return 1

            ur1_done = self.wait_for_ipc_response(
                201, 45.0, seen_ipc_commands, seen_nachi_actions
            )
            print(
                f"[{'PASS' if ur1_done else 'BLOCKED'}] Noodle drop + UR1 CMD101/201: "
                f"IPC={seen_ipc_commands}, Nachi={seen_nachi_actions}, "
                f"IPCReq={self.read_d(D_PLC_IPC_REQUEST_CODE)[0]}, "
                f"IPCBusy={self.read_d(D_IPC_BUSY)[0]}, "
                f"ActionStep={self.read_d(D_NOODLE_ACTION_STEP)[0]}, "
                f"D12101=0x{self.read_d(D_NACHI_DATA_FINISH)[0]:04X}, "
                f"D8000=0x{self.read_d(D_SIMULATION)[0]:04X}, "
                f"D8009=0x{self.read_d(D_NOODLE_ACTION_DEBUG_BITS)[0]:04X}, "
                f"D8010=0x{self.read_d(D_AUTO_FLOW_DEBUG_BITS)[0]:04X}"
            )
            if self.peripheral is not None:
                data_task = self.peripheral.nachi_data_task
                print(
                    "[DEBUG] Nachi data handshake at block: "
                    f"TaskActive={int(data_task is not None)}, "
                    f"FinishWritten={int(bool(data_task and data_task.finish_pulsed))}, "
                    f"DataReady={int(bool(self.peripheral.last_nachi_command_word & 0x0100))}"
                )
            if not ur1_done:
                return 1

            # 離開X0.2，抵達X0.3。
            self.set_sim_bit(BIT_SIM_X02, False)
            self.tick_for(0.5)
            self.set_sim_bit(BIT_SIM_X03, True)
            ur2_done = self.wait_for_ipc_response(
                202, 20.0, seen_ipc_commands, seen_nachi_actions
            )
            print(
                f"[{'PASS' if ur2_done else 'BLOCKED'}] UR2 CMD102/202: "
                f"IPC={seen_ipc_commands}"
            )
            if not ur2_done:
                return 1

            # 離開X0.3，抵達X0.4注湯/完成站。
            self.set_sim_bit(BIT_SIM_X03, False)
            self.tick_for(0.5)
            self.set_sim_bit(BIT_SIM_X04, True)
            completed = self.wait_for(
                lambda: self.read_d(D_ORDER_FIFO_COUNT)[0] == 0,
                20.0,
            )
            completed_unit_id = join_dint(
                self.read_d(D_ORDER_COMPLETE_UNIT_ID, 2)
            )
            complete_words = self.read_d(D_ORDER_COMPLETE_INDEX, 2)
            completed_index = (
                complete_words[0]
                | (complete_words[1] << 16)
            )
            notification_ok = (
                completed
                and completed_unit_id == unit_id
                and completed_index != 0
                and completed_index != before_complete_index
            )
            print(
                f"[{'PASS' if notification_ok else 'BLOCKED'}] X0.4 soup/order complete: "
                f"FIFO={self.read_d(D_ORDER_FIFO_COUNT)[0]}, "
                f"CompletedUnitID={completed_unit_id}, "
                f"CompleteIndex={before_complete_index}->{completed_index}, "
                f"IPC={seen_ipc_commands}, Nachi={seen_nachi_actions}"
            )
            if not notification_ok:
                flow_debug = self.read_d(D_NOODLE_DEBUG_BITS, 9)
                print(
                    "[DEBUG] Soup station block: "
                    f"D8002=0x{flow_debug[0]:04X}, "
                    f"Baskets={flow_debug[1:4]}, "
                    f"Rightmost={flow_debug[4]}, "
                    f"CookJobState={flow_debug[5]}, "
                    f"NoodleActionStep={flow_debug[6]}, "
                    f"D8009=0x{flow_debug[7]:04X}, "
                    f"D8010=0x{flow_debug[8]:04X}"
                )
            return 0 if notification_ok else 1
        finally:
            self.write_d(D_ORDER_VALID, 0)
            self.write_d(D_SIMULATION, original_simulation_word)
            self.stop()


if __name__ == "__main__":
    raise SystemExit(FullAutoFlowTest().run_full_flow())
