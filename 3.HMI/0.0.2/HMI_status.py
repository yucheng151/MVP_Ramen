"""PLC -> HMI 的狀態讀取模組。

本模組只讀取 PLC 發送給 HMI 的狀態暫存器 D1102~D1106，使用由
main_hmi.py 建立並傳入的共用 Modbus TCP client。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Optional

from HMI_plc_client import HMIPlcClient
from register_map import (
    PLC_TO_HMI_SENSOR_STATUS,
    PLC_ROBOT_MANUAL_STATUS,
    ROBOT_COMMAND_BITS,
    ROBOT_COMMAND_WORD,
    ROBOT_STATUS_BITS,
    ROBOT_STATUS_WORD,
    SENSOR_BITS,
)


# =====================================================
# PLC -> HMI 狀態 D 暫存器位址
# =====================================================
D_PLC_TO_HMI_CMD_ACK_INDEX = 1102   # D1102
D_PLC_TO_HMI_CMD_RESPONSE_CODE = 1103  # D1103
D_PLC_TO_HMI_CONVEYOR_STATUS = 1104    # D1104
D_HMI_COMM_STATUS = 1105               # D1105
D_PLC_TO_HMI_STATUS_CODE = 1106       # D1106


def _signed_word(value: int) -> int:
    """Convert a PLC 16-bit register to signed INT."""
    return value - 0x10000 if value & 0x8000 else value


@dataclass
class HMISensorStatus:
    bowl_drop_confirm: bool = False
    pause_point_1: bool = False
    pause_point_2: bool = False
    right_stop_point: bool = False
    bowl_dispenser_busy: bool = False


@dataclass
class RobotStatus:
    """Read-only Robot data mirrored by the PLC."""

    read_ok: bool = False
    status_word: Optional[int] = None
    read_complete: Optional[int] = None
    error_code: Optional[int] = None
    action_complete: Optional[int] = None
    index: Optional[int] = None
    command_word: Optional[int] = None
    command_index: Optional[int] = None
    action_no: Optional[int] = None
    noodle_cabinet_no: Optional[int] = None
    cut_no: Optional[int] = None
    output_cabinet_no: Optional[int] = None
    noodle_type_no: Optional[int] = None

    busy: bool = False
    status_output: bool = False
    home_signal: bool = False
    error_signal: bool = False
    alarm_signal: bool = False
    estop_active: bool = False
    program_running: bool = False
    sub_start: bool = False
    external_control_start: bool = False
    remote_control_available: bool = False

    external_stop: bool = False
    external_start: bool = False
    servo_power_on: bool = False
    external_reset: bool = False
    program_select_bit1: bool = False
    program_select_pulse: bool = False
    program_start_enable: bool = False
    intermittent: bool = False
    plc_data_ready: bool = False
    interval_motion_enable: bool = False
    shutdown: bool = False


@dataclass
class RobotManualStatus:
    """PLC reply for HMI Robot Manual Execute (CMD 40)."""

    read_ok: bool = False
    status: Optional[int] = None
    ack_index: Optional[int] = None
    result_code: Optional[int] = None
    alarm_code: Optional[int] = None


@dataclass
class HMIStatusResult:
    ok: bool
    ack_index: Optional[int]
    response_code: Optional[int]
    conveyor_status: Optional[int]
    hmi_comm_status: Optional[int]
    plc_status_code: Optional[int]
    message: str
    sensors: HMISensorStatus = field(default_factory=HMISensorStatus)
    robot: RobotStatus = field(default_factory=RobotStatus)
    robot_manual: RobotManualStatus = field(default_factory=RobotManualStatus)


class HMIStatus:
    """讀取 PLC -> HMI 狀態的控制器。"""

    def __init__(self, plc: HMIPlcClient):
        self.plc = plc
        self.last_error: Optional[str] = None

    def read_status(self) -> HMIStatusResult:
        """讀取 D1102~D1106，共 5 個 WORD。"""
        if not self.plc.connected:
            self.last_error = "尚未連線 PLC"
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message="尚未連線 PLC",
            )

        data = self.plc.read_d(D_PLC_TO_HMI_CMD_ACK_INDEX, 5)
        if data is None:
            self.last_error = self.plc.last_error
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message=self.last_error or "讀取 PLC 狀態失敗",
            )

        if len(data) < 5:
            return HMIStatusResult(
                ok=False,
                ack_index=None,
                response_code=None,
                conveyor_status=None,
                hmi_comm_status=None,
                plc_status_code=None,
                message=f"PLC 回傳資料不足：預期 5 筆，收到 {len(data)} 筆",
            )

        sensor_data = self.plc.read_d(PLC_TO_HMI_SENSOR_STATUS, 1)
        if sensor_data is None:
            self.last_error = self.plc.last_error
            return HMIStatusResult(
                ok=False,
                ack_index=data[0],
                response_code=data[1],
                conveyor_status=data[2],
                hmi_comm_status=data[3],
                plc_status_code=data[4],
                message=self.last_error or "讀取 D1110 感測器狀態失敗",
            )

        sensor_word = sensor_data[0]
        sensors = HMISensorStatus(**{
            name: bool(sensor_word & (1 << bit))
            for name, bit in SENSOR_BITS.items()
        })

        # Read only. There is intentionally no Robot write path in HMIStatus.
        robot_status_data = self.plc.read_d(ROBOT_STATUS_WORD, 5)
        robot_command_data = self.plc.read_d(ROBOT_COMMAND_WORD, 7)
        robot_manual_data = self.plc.read_d(PLC_ROBOT_MANUAL_STATUS, 4)
        robot = RobotStatus()
        if (
            robot_status_data is not None
            and len(robot_status_data) >= 5
            and robot_command_data is not None
            and len(robot_command_data) >= 7
        ):
            status_word = robot_status_data[0]
            command_word = robot_command_data[0]
            robot_values = {
                "read_ok": True,
                "status_word": status_word,
                "read_complete": robot_status_data[1],
                "error_code": robot_status_data[2],
                "action_complete": robot_status_data[3],
                "index": robot_status_data[4],
                "command_word": command_word,
                "command_index": robot_command_data[1],
                "action_no": robot_command_data[2],
                "noodle_cabinet_no": robot_command_data[3],
                "cut_no": robot_command_data[4],
                "output_cabinet_no": robot_command_data[5],
                "noodle_type_no": robot_command_data[6],
            }
            robot_values.update({
                name: bool(status_word & (1 << bit))
                for name, bit in ROBOT_STATUS_BITS.items()
            })
            robot_values.update({
                name: bool(command_word & (1 << bit))
                for name, bit in ROBOT_COMMAND_BITS.items()
            })
            robot = RobotStatus(**robot_values)
        robot_manual = RobotManualStatus()
        if robot_manual_data is not None and len(robot_manual_data) >= 4:
            robot_manual = RobotManualStatus(
                read_ok=True,
                status=_signed_word(robot_manual_data[0]),
                ack_index=robot_manual_data[1],
                result_code=_signed_word(robot_manual_data[2]),
                alarm_code=_signed_word(robot_manual_data[3]),
            )

        return HMIStatusResult(
            ok=True,
            ack_index=data[0],
            response_code=data[1],
            conveyor_status=data[2],
            hmi_comm_status=data[3],
            plc_status_code=data[4],
            message="OK",
            sensors=sensors,
            robot=robot,
            robot_manual=robot_manual,
        )
