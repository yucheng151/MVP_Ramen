"""HMI 對 PLC 的命令寫入模組。

本模組只負責 HMI -> PLC 的命令寫入，使用由 main_hmi.py 建立並傳入的
共用 Modbus TCP client。它不會自行建立新的 ModbusTcpClient。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from HMI_plc_client import HMIPlcClient
from register_map import (
    CMD_MODE_AUTO,
    CMD_MODE_MANUAL,
    CMD_SMALL_MATERIAL_FIRST,
    CMD_SMALL_MATERIAL_LAST,
    HMI_CMD_CODE,
    HMI_CMD_INDEX,
    HMI_CMD_VALID,
    HMI_CONVEYOR_SPEED,
    HMI_ROBOT_ACTION_NO,
    MACHINE_MODE_AUTO,
    MACHINE_MODE_MANUAL,
)


# =====================================================
# HMI -> PLC 命令 D 暫存器位址
# =====================================================
D_HMI_TO_PLC_CMD_CODE = HMI_CMD_CODE
D_HMI_TO_PLC_CMD_INDEX = HMI_CMD_INDEX
D_HMI_TO_PLC_CMD_VALID = HMI_CMD_VALID
D_HMI_TO_PLC_CONVEYOR_SPEED = HMI_CONVEYOR_SPEED

CMD_NONE = 0
CMD_INITIALIZE = 1
CMD_ALARM_RESET = 6
CMD_CONVEYOR_RUN = 10
CMD_CONVEYOR_STOP = 11
CMD_SET_CONVEYOR_SPEED = 12
CMD_BOWL_DISPENSE = 20
CMD_ROBOT_MANUAL_EXECUTE = 40

DEFAULT_CONVEYOR_SPEED = 150


@dataclass
class HMICommandResult:
    ok: bool
    command_code: int
    command_index: int
    conveyor_speed: int
    message: str


class HMICommand:
    """HMI 對 PLC 命令寫入控制器。"""

    def __init__(self, plc: HMIPlcClient):
        self.plc = plc
        self.last_error: Optional[str] = None
        self.last_command_index = 0

    def write_d(self, address: int, value: int) -> bool:
        """寫入單一個 D 暫存器。"""
        ok = self.plc.write_d(address, value)
        self.last_error = self.plc.last_error
        return ok

    def write_d_block(self, start_address: int, values: list[int]) -> bool:
        """寫入一連串 D 暫存器。"""
        ok = self.plc.write_d_block(start_address, values)
        self.last_error = self.plc.last_error
        return ok

    def next_command_index(self) -> int:
        """取得下一個命令 Index，並在 0~65535 間循環。"""
        self.last_command_index = (self.last_command_index + 1) & 0xFFFF
        return self.last_command_index

    def send_command(self, command_code: int, conveyor_speed: int = 0) -> HMICommandResult:
        """送出一個新命令。"""
        if command_code == CMD_NONE:
            return self.clear_command()

        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return HMICommandResult(
                ok=False,
                command_code=command_code,
                command_index=self.last_command_index,
                conveyor_speed=conveyor_speed,
                message="尚未連線 PLC",
            )

        command_index = self.next_command_index()

        with self.plc.lock:
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 0):
                return HMICommandResult(
                    ok=False,
                    command_code=command_code,
                    command_index=command_index,
                    conveyor_speed=conveyor_speed,
                    message=self.last_error or "清除命令有效位失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_CODE, command_code):
                return HMICommandResult(
                    ok=False,
                    command_code=command_code,
                    command_index=command_index,
                    conveyor_speed=conveyor_speed,
                    message=self.last_error or "寫入命令碼失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CONVEYOR_SPEED, conveyor_speed):
                return HMICommandResult(
                    ok=False,
                    command_code=command_code,
                    command_index=command_index,
                    conveyor_speed=conveyor_speed,
                    message=self.last_error or "寫入輸送帶速度失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_INDEX, command_index):
                return HMICommandResult(
                    ok=False,
                    command_code=command_code,
                    command_index=command_index,
                    conveyor_speed=conveyor_speed,
                    message=self.last_error or "寫入命令 Index 失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 1):
                return HMICommandResult(
                    ok=False,
                    command_code=command_code,
                    command_index=command_index,
                    conveyor_speed=conveyor_speed,
                    message=self.last_error or "打開命令有效位失敗",
                )

        return HMICommandResult(
            ok=True,
            command_code=command_code,
            command_index=command_index,
            conveyor_speed=conveyor_speed,
            message="OK",
        )

    def send_initialize(self) -> HMICommandResult:
        return self.send_command(CMD_INITIALIZE, conveyor_speed=0)

    def send_alarm_reset(self) -> HMICommandResult:
        return self.send_command(CMD_ALARM_RESET, conveyor_speed=0)

    def send_conveyor_run(self, speed: int = DEFAULT_CONVEYOR_SPEED) -> HMICommandResult:
        return self.send_command(CMD_CONVEYOR_RUN, conveyor_speed=speed)

    def send_conveyor_stop(self) -> HMICommandResult:
        return self.send_command(CMD_CONVEYOR_STOP, conveyor_speed=0)

    def send_set_conveyor_speed(self, speed: int) -> HMICommandResult:
        return self.send_command(CMD_SET_CONVEYOR_SPEED, conveyor_speed=speed)

    def send_bowl_dispense(self) -> HMICommandResult:
        """送出一次落碗命令。"""
        return self.send_command(CMD_BOWL_DISPENSE, conveyor_speed=0)

    def send_small_material_first(self) -> HMICommandResult:
        """Send CMD 50 through the existing D1000~D1002 handshake."""
        return self.send_command(CMD_SMALL_MATERIAL_FIRST, conveyor_speed=0)

    def send_small_material_last(self) -> HMICommandResult:
        """Send CMD 51 through the existing D1000~D1002 handshake."""
        return self.send_command(CMD_SMALL_MATERIAL_LAST, conveyor_speed=0)

    def send_machine_mode(self, mode: int) -> HMICommandResult:
        """Issue one mode command through the existing D1000~D1002 handshake."""
        command_codes = {
            MACHINE_MODE_MANUAL: CMD_MODE_MANUAL,
            MACHINE_MODE_AUTO: CMD_MODE_AUTO,
        }
        command_code = command_codes.get(mode)
        if command_code is None:
            self.last_error = f"Invalid machine mode: {mode}"
            return HMICommandResult(
                False, CMD_NONE, self.last_command_index, 0, self.last_error,
            )
        if not self.plc.connected:
            self.last_error = "PLC Offline"
            return HMICommandResult(
                False, command_code, self.last_command_index, 0, self.last_error,
            )

        command_index = self.next_command_index()
        with self.plc.lock:
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 0):
                return HMICommandResult(False, command_code, command_index, 0,
                                        self.last_error or "Cannot clear Command Valid")
            if not self.write_d(D_HMI_TO_PLC_CMD_CODE, command_code):
                return HMICommandResult(False, command_code, command_index, 0,
                                        self.last_error or "Cannot write mode command")
            if not self.write_d(D_HMI_TO_PLC_CMD_INDEX, command_index):
                return HMICommandResult(False, command_code, command_index, 0,
                                        self.last_error or "Cannot write Command Index")
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 1):
                return HMICommandResult(False, command_code, command_index, 0,
                                        self.last_error or "Cannot set Command Valid")
        return HMICommandResult(True, command_code, command_index, 0, "OK")

    def clear_machine_mode_command(self) -> bool:
        """Release the shared handshake after a matched mode ACK."""
        if not self.plc.connected:
            self.last_error = "PLC Offline"
            return False
        with self.plc.lock:
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 0):
                return False
            return self.write_d(D_HMI_TO_PLC_CMD_CODE, CMD_NONE)

    def send_robot_manual(
        self,
        action_no: int,
        noodle_cabinet_no: int,
        cut_no: int,
        output_cabinet_no: int,
    ) -> HMICommandResult:
        """Write D1010~D1013, then issue Robot Manual Execute (CMD 40)."""
        valid = (
            action_no == 1
            and 1 <= noodle_cabinet_no <= 10
            and 1 <= cut_no <= 6
            and 1 <= output_cabinet_no <= 2
        ) or (
            action_no == 2
            and noodle_cabinet_no == 0
            and 1 <= cut_no <= 6
            and output_cabinet_no == 0
        )
        if not valid:
            self.last_error = "Robot 單動參數超出允許範圍"
            return HMICommandResult(
                False, CMD_ROBOT_MANUAL_EXECUTE, self.last_command_index, 0,
                self.last_error,
            )
        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return HMICommandResult(
                False, CMD_ROBOT_MANUAL_EXECUTE, self.last_command_index, 0,
                self.last_error,
            )

        command_index = self.next_command_index()
        parameters = [action_no, noodle_cabinet_no, cut_no, output_cabinet_no]
        with self.plc.lock:
            if not self.write_d_block(HMI_ROBOT_ACTION_NO, parameters):
                return HMICommandResult(
                    False, CMD_ROBOT_MANUAL_EXECUTE, command_index, 0,
                    self.last_error or "寫入 Robot 單動參數失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_INDEX, command_index):
                return HMICommandResult(
                    False, CMD_ROBOT_MANUAL_EXECUTE, command_index, 0,
                    self.last_error or "寫入 Robot 命令序號失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_CODE, CMD_ROBOT_MANUAL_EXECUTE):
                return HMICommandResult(
                    False, CMD_ROBOT_MANUAL_EXECUTE, command_index, 0,
                    self.last_error or "寫入 Robot 命令碼失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 1):
                return HMICommandResult(
                    False, CMD_ROBOT_MANUAL_EXECUTE, command_index, 0,
                    self.last_error or "打開 Robot 命令有效位失敗",
                )
        return HMICommandResult(
            True, CMD_ROBOT_MANUAL_EXECUTE, command_index, 0, "OK",
        )

    def clear_robot_manual_command(self) -> bool:
        """Clear D1002 then D1000 after Robot manual completion/failure."""
        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return False
        with self.plc.lock:
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 0):
                return False
            return self.write_d(D_HMI_TO_PLC_CMD_CODE, CMD_NONE)

    def clear_command(self) -> HMICommandResult:
        """清除目前命令，但保留目前的 command_index。"""
        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return HMICommandResult(
                ok=False,
                command_code=CMD_NONE,
                command_index=self.last_command_index,
                conveyor_speed=0,
                message="尚未連線 PLC",
            )

        with self.plc.lock:
            if not self.write_d(D_HMI_TO_PLC_CMD_VALID, 0):
                return HMICommandResult(
                    ok=False,
                    command_code=CMD_NONE,
                    command_index=self.last_command_index,
                    conveyor_speed=0,
                    message=self.last_error or "清除命令有效位失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CMD_CODE, 0):
                return HMICommandResult(
                    ok=False,
                    command_code=CMD_NONE,
                    command_index=self.last_command_index,
                    conveyor_speed=0,
                    message=self.last_error or "清除命令碼失敗",
                )
            if not self.write_d(D_HMI_TO_PLC_CONVEYOR_SPEED, 0):
                return HMICommandResult(
                    ok=False,
                    command_code=CMD_NONE,
                    command_index=self.last_command_index,
                    conveyor_speed=0,
                    message=self.last_error or "清除速度失敗",
                )

        return HMICommandResult(
            ok=True,
            command_code=CMD_NONE,
            command_index=self.last_command_index,
            conveyor_speed=0,
            message="命令已清除",
        )
